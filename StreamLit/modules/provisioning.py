"""OpenRouter Provisioning client and admin helpers.

This module encapsulates calls to OpenRouter's Provisioning API to create, get,
update, and delete API keys for end users. It also provides a small façade that
applies the project rules: default $5 limit, replacement policy only when
remaining < $0.01, and storage of the secret per-user in config.yaml via
modules.admin helpers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import requests
from datetime import datetime, timezone

from .config import (
    get_openrouter_provisioning_key,
    get_openrouter_provisioning_default_limit,
    get_openrouter_provisioning_limit_reset,
)
from .admin import (
    get_user_provisioned_openrouter,
    set_user_provisioned_openrouter,
)

BASE_URL = "https://openrouter.ai/api/v1"


class ProvisioningError(Exception):
    pass


def _auth_header() -> Dict[str, str]:
    token = (get_openrouter_provisioning_key() or "").strip()
    if not token:
        raise ProvisioningError("Provisioning API key is not configured.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_user_key(name: str, limit_usd: Optional[float] = None, limit_reset: Optional[str] = None,
                    include_byok_in_limit: bool = True) -> Tuple[Dict[str, Any], str]:
    """Create a new API key using Provisioning API.

    Returns (data, key_string). 'data' contains fields like hash, limit, remaining.
    """
    url = f"{BASE_URL}/keys"
    headers = _auth_header()
    payload: Dict[str, Any] = {"name": name}
    if limit_usd is None:
        limit_usd = get_openrouter_provisioning_default_limit()
    if limit_usd is not None:
        payload["limit"] = float(limit_usd)
    if limit_reset is None:
        limit_reset = get_openrouter_provisioning_limit_reset()
    if limit_reset:
        payload["limit_reset"] = limit_reset
    payload["include_byok_in_limit"] = bool(include_byok_in_limit)

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise ProvisioningError(f"Failed to create key: {resp.status_code} {resp.text}")
    data = resp.json() or {}
    # Response example: { "data": {..., "hash": "...", ...}, "key": "sk-or-..." }
    key_str = data.get("key") or data.get("data", {}).get("key")
    if not key_str:
        # Some SDKs return key at top-level; docs show top-level 'key'
        raise ProvisioningError("Provisioned key was not returned by API.")
    return data.get("data", {}), str(key_str)


def get_key(hash_value: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/keys/{hash_value}"
    headers = _auth_header()
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise ProvisioningError(f"Failed to get key: {resp.status_code} {resp.text}")
    data = resp.json() or {}
    return data.get("data", {})


def delete_key(hash_value: str) -> bool:
    url = f"{BASE_URL}/keys/{hash_value}"
    headers = _auth_header()
    resp = requests.delete(url, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise ProvisioningError(f"Failed to delete key: {resp.status_code} {resp.text}")
    try:
        # A 204 No Content response is also a success.
        if resp.status_code == 204:
            return True
        data = resp.json() or {}
        # Default to False if 'success' key is missing.
        return bool(data.get("data", {}).get("success", False))
    except Exception:
        # If JSON decoding fails, it's not a successful deletion.
        return False


def update_key(hash_value: str, name: Optional[str] = None, disabled: Optional[bool] = None,
               limit: Optional[float] = None, limit_reset: Optional[str | None] = None,
               include_byok_in_limit: Optional[bool] = None) -> Dict[str, Any]:
    """PATCH update to an API key. Returns updated data."""
    url = f"{BASE_URL}/keys/{hash_value}"
    headers = _auth_header()
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if disabled is not None:
        payload["disabled"] = bool(disabled)
    # limit can be float or null
    if limit is not None:
        payload["limit"] = float(limit)
    if limit_reset is not None:
        if limit_reset in ("daily", "weekly", "monthly"):
            payload["limit_reset"] = limit_reset
        else:
            payload["limit_reset"] = None
    if include_byok_in_limit is not None:
        payload["include_byok_in_limit"] = bool(include_byok_in_limit)
    resp = requests.patch(url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise ProvisioningError(f"Failed to update key: {resp.status_code} {resp.text}")
    return (resp.json() or {}).get("data", {})


def disable_key(hash_value: str, disabled: bool = True) -> Dict[str, Any]:
    return update_key(hash_value, disabled=disabled)


def remove_user_key(username: str) -> bool:
    """Delete user's provisioned key at OpenRouter (if known) and remove local record."""
    rec = get_user_provisioned_openrouter(username)
    if not rec:
        return True
    ok = True
    if rec.get("hash"):
        try:
            ok = delete_key(rec.get("hash"))
        except Exception:
            ok = False
    # Remove local record regardless to avoid dangling secret
    set_user_provisioned_openrouter(username, None)
    return ok


def update_user_key(username: str, *, new_limit: Optional[float] = None,
                    new_limit_reset: Optional[str | None] = None,
                    include_byok_in_limit: Optional[bool] = None,
                    disabled: Optional[bool] = None,
                    new_name: Optional[str] = None) -> Dict[str, Any]:
    """Update a user's provisioned key via Provisioning API and refresh stored metadata."""
    rec = get_user_provisioned_openrouter(username)
    if not rec or not rec.get("hash"):
        raise ProvisioningError("No provisioned key found for user.")
    updated = update_key(
        rec.get("hash"),
        name=new_name,
        disabled=disabled,
        limit=new_limit,
        limit_reset=new_limit_reset,
        include_byok_in_limit=include_byok_in_limit,
    )
    # Merge updates into stored record
    current = get_user_provisioned_openrouter(username) or {}
    for k in essential_fields:
        if k in updated:
            current[k] = updated[k]
    set_user_provisioned_openrouter(username, current)
    return {k: v for k, v in current.items() if k != "key"}


# -------- High-level flows --------

essential_fields = [
    "name", "label", "limit", "limit_remaining", "limit_reset", "include_byok_in_limit",
    "usage", "usage_daily", "usage_weekly", "usage_monthly",
    "byok_usage", "byok_usage_daily", "byok_usage_weekly", "byok_usage_monthly",
    "disabled", "created_at", "updated_at", "hash",
]


def issue_key_to_user(username: str, display_name: Optional[str] = None,
                      limit_usd: Optional[float] = None) -> Dict[str, Any]:
    """Create a key and store it under the user. Overwrites any existing stored key record.

    Returns the stored record sans secret by default, but record contains secret internally.
    """
    name = display_name or f"MyChart - {username}"
    data, key_str = create_user_key(name=name, limit_usd=limit_usd)
    now = datetime.now(timezone.utc).isoformat()
    rec = {
        **{k: data.get(k) for k in essential_fields if k in data},
        "key": key_str,
        "issued_at": now,
    }
    set_user_provisioned_openrouter(username, rec)
    # Return a safe copy without exposing the key by default
    safe = {k: v for k, v in rec.items() if k != "key"}
    return safe


def can_replace_user_key(username: str) -> Tuple[bool, Optional[str]]:
    """Business rule: allow replacement only if no key exists or remaining <= $0.01.

    Returns (allowed, reason_if_denied).
    """
    rec = get_user_provisioned_openrouter(username)
    if not rec:
        return True, None
    # Try to refresh from API using hash if available
    hash_val = rec.get("hash")
    try:
        if hash_val:
            fresh = get_key(hash_val)
        else:
            fresh = rec
    except Exception:
        # If API lookup fails, fall back to stored value
        fresh = rec
    remaining = fresh.get("limit_remaining")
    try:
        rem = float(remaining)
    except Exception:
        rem = None
    if rem is None:
        # If unknown, be conservative and deny replacement unless disabled
        if fresh.get("disabled"):
            return True, None
        return False, "Cannot determine remaining amount."
    if rem > 0.01:
        return False, f"Key still has ${rem:.2f} remaining."
    return True, None


def replace_user_key(username: str, display_name: Optional[str] = None,
                     limit_usd: Optional[float] = None) -> Dict[str, Any]:
    """Replace user's provisioned key if allowed by business rule.

    If an existing key hash is known, attempt to delete it on OpenRouter first.
    """
    allowed, reason = can_replace_user_key(username)
    if not allowed:
        raise ProvisioningError(reason or "Replacement not allowed.")
    # Delete prior key if we know the hash
    rec = get_user_provisioned_openrouter(username)
    if rec and rec.get("hash"):
        try:
            delete_key(rec.get("hash"))
        except Exception:
            # Continue even if delete fails
            pass
    return issue_key_to_user(username, display_name=display_name, limit_usd=limit_usd)


def refresh_user_key_status(username: str) -> Dict[str, Any] | None:
    """Refresh stored user's key metadata using the API (does not modify secret)."""
    rec = get_user_provisioned_openrouter(username)
    if not rec:
        return None
    hash_val = rec.get("hash")
    if not hash_val:
        return {k: v for k, v in rec.items() if k != "key"}
    try:
        fresh = get_key(hash_val)
    except Exception:
        return {k: v for k, v in rec.items() if k != "key"}
    # Merge fields
    for k in essential_fields:
        if k in fresh:
            rec[k] = fresh[k]
    rec["updated_at"] = fresh.get("updated_at") or rec.get("updated_at")
    set_user_provisioned_openrouter(username, rec)
    return {k: v for k, v in rec.items() if k != "key"}
