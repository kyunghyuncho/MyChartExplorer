"""Transient OAuth state storage for PKCE verifiers.

Stores (state -> verifier) mappings under the user's data directory so that
the verifier can be recovered after external redirects or session resets.

Entries are short-lived and removed after use or on cleanup.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .paths import get_user_dir


def _store_path(username: str) -> Path:
    return Path(get_user_dir(username)) / "oauth_pkce.json"


def _read_store(username: str) -> dict:
    p = _store_path(username)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_store(username: str, data: dict) -> None:
    p = _store_path(username)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(data or {}, f, indent=2)
    except Exception:
        pass


def save_verifier(username: str, state: str, verifier: str) -> None:
    data = _read_store(username)
    data[state] = {"verifier": verifier, "ts": int(time.time())}
    _write_store(username, data)


def pop_verifier(username: str, state: str, max_age_seconds: int = 900) -> Optional[str]:
    """Return and remove the verifier for a given state if present and fresh.

    Default max age is 15 minutes.
    """
    data = _read_store(username)
    now = int(time.time())
    entry = (data or {}).get(state)
    verifier: Optional[str] = None
    if isinstance(entry, dict):
        ts = int(entry.get("ts", 0))
        if now - ts <= max_age_seconds:
            verifier = entry.get("verifier")
        # Remove the entry regardless (single-use)
        data.pop(state, None)
        _write_store(username, data)
    # Opportunistic cleanup of old entries
    try:
        dirty = False
        for k, v in list((data or {}).items()):
            if not isinstance(v, dict) or now - int(v.get("ts", 0)) > max_age_seconds:
                data.pop(k, None)
                dirty = True
        if dirty:
            _write_store(username, data)
    except Exception:
        pass
    return verifier
