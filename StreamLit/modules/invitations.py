"""Invitation management for invitation-only registration.

Stores invitations in a JSON file under data root (invitations.json).
Each invitation:
{
  "email": "user@example.com",
  "code": "ABCDEFGH1234",
  "created_at": "2025-09-30T12:34:56Z",
  "expires_at": "2025-11-29T12:34:56Z",  # 60 days later
  "used": false,
  "used_at": null
}

Functions cover creating, listing, deleting, validating, and marking used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import secrets
import re
import requests

from .paths import get_invitations_json_path
from .admin import _load_config  # reuse config.yaml loading to check existing users


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_store() -> List[Dict[str, Any]]:
    path = Path(get_invitations_json_path())
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f) or []
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _write_store(items: List[Dict[str, Any]]) -> None:
    path = Path(get_invitations_json_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(items or [], f, indent=2)
    except Exception:
        pass


def _email_registered(email: str) -> bool:
    email = (email or "").strip().lower()
    cfg = _load_config() or {}
    users = ((cfg.get("credentials") or {}).get("usernames") or {})
    for uname, info in (users or {}).items():
        if (info or {}).get("email", "").strip().lower() == email:
            return True
    return False


def _username_exists(username: str) -> bool:
    username = (username or "").strip()
    cfg = _load_config() or {}
    users = ((cfg.get("credentials") or {}).get("usernames") or {})
    return username in users


def create_invitation(email: str) -> Dict[str, Any]:
    """Create a new invitation for email if not registered.

    Returns the created record. If an unexpired pending invite already exists for the
    same email, returns that one instead (idempotent behavior).
    """
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    if _email_registered(email):
        raise ValueError("Email is already registered")

    items = _read_store()
    now = _now_utc()
    # Check for existing pending, not expired
    for it in items:
        if it.get("email", "").lower() == email and not bool(it.get("used")):
            exp = it.get("expires_at")
            try:
                exp_dt = datetime.strptime(exp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if exp_dt > now:
                    return it
            except Exception:
                pass

    # Create new
    code = secrets.token_urlsafe(10)  # ~16 chars URL-safe
    record = {
        "email": email,
        "code": code,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(days=60)),
        "used": False,
        "used_at": None,
    }
    items.append(record)
    _write_store(items)
    return record


def list_invitations(pending_only: bool = False, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
    """Return (subset, total_count) for invitations sorted by created_at desc.

    If pending_only=True, filters to not used and not expired.
    """
    items = _read_store()
    now = _now_utc()
    def _key(it):
        try:
            return datetime.strptime(it.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return datetime.min
    items.sort(key=_key, reverse=True)

    if pending_only:
        filtered = []
        for it in items:
            if bool(it.get("used")):
                continue
            try:
                exp_dt = datetime.strptime(it.get("expires_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if exp_dt <= now:
                    continue
            except Exception:
                continue
            filtered.append(it)
        items = filtered

    total = len(items)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return items[start:end], total


def delete_invitation(code: str) -> bool:
    """Delete an invitation by code. Returns True if removed."""
    code = (code or "").strip()
    items = _read_store()
    new_items = [it for it in items if it.get("code") != code]
    if len(new_items) != len(items):
        _write_store(new_items)
        return True
    return False


def validate_invitation(email: str, code: str) -> bool:
    """Check that email+code matches a pending, unexpired invitation and email not registered."""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    if not EMAIL_RE.match(email) or not code:
        return False
    if _email_registered(email):
        return False
    now = _now_utc()
    for it in _read_store():
        if it.get("email", "").lower() == email and it.get("code") == code and not bool(it.get("used")):
            try:
                exp_dt = datetime.strptime(it.get("expires_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                return exp_dt > now
            except Exception:
                return False
    return False


def mark_invitation_used(email: str, code: str) -> None:
    email = (email or "").strip().lower()
    code = (code or "").strip()
    items = _read_store()
    changed = False
    now = _now_utc()
    for it in items:
        if it.get("email", "").lower() == email and it.get("code") == code:
            it["used"] = True
            it["used_at"] = _iso(now)
            changed = True
            break
    if changed:
        _write_store(items)


def get_sendgrid_api_key() -> str:
    from .config import _read_json
    from .paths import get_global_config_json_path
    data = _read_json(get_global_config_json_path())
    return (data or {}).get("sendgrid_api_key", "")


def set_sendgrid_api_key(value: str) -> None:
    from .config import _read_json, _write_json
    from .paths import get_global_config_json_path
    path = get_global_config_json_path()
    data = _read_json(path)
    data["sendgrid_api_key"] = value or ""
    _write_json(path, data)


def send_invitation_email(email: str, code: str, inviter_name: str | None = None, app_url: str | None = None) -> Tuple[bool, str]:
    """Send an invitation via SendGrid API.

    Requires that admin has set a SendGrid API key in global config.
    Returns (ok, message).
    """
    key = get_sendgrid_api_key().strip()
    if not key:
        return False, "SendGrid API key is not set."
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        return False, "Invalid email"

    subject = "You're invited to MyChart Explorer"
    inviter = inviter_name or "Admin"
    canonical_url = "https://www.mychartexplorer.com/"
    if app_url:
        register_instructions = (
            f"Open <a href=\"{app_url}\">{app_url}</a> (or <a href=\"{canonical_url}\">{canonical_url}</a>) and go to the Register page."
        )
    else:
        register_instructions = (
            f"Open <a href=\"{canonical_url}\">{canonical_url}</a> and go to the Register page."
        )
    content_html = f"""
    <p>Hello,</p>
    <p>{inviter} has invited you to join <strong>MyChart Explorer</strong>.</p>
    <p>Your invitation code is: <strong>{code}</strong></p>
    <p>This code is valid for 60 days and only for this email: <strong>{email}</strong>.</p>
    <p>{register_instructions}</p>
    <p>Thank you.</p>
    """

    payload = {
        "personalizations": [
            {"to": [{"email": email}], "subject": subject}
        ],
        "from": {"email": "no-reply@mychartexplorer.com"},
        "content": [{"type": "text/html", "value": content_html}],
    }
    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            return True, "Invitation email sent."
        else:
            return False, f"SendGrid error: {resp.status_code} {resp.text[:200]}"
    except Exception as e:
        return False, f"Failed to send email: {e}"


def invite_user(email: str, inviter_name: str | None = None, app_url: str | None = None) -> Tuple[Dict[str, Any], str]:
    """Create an invitation and send email via SendGrid.

    Returns (record, message). Raises ValueError for invalid email or already registered.
    """
    record = create_invitation(email)
    ok, msg = send_invitation_email(record["email"], record["code"], inviter_name=inviter_name, app_url=app_url)
    return record, msg
