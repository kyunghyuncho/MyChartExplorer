"""Text-based audit logging for admin and sensitive actions.

- Appends line-oriented JSON records to a single rotating file under DATADIR/logs/app_audit.log
- Provides simple text search and retrieval for Admin UI.
- Avoids logging secrets (API keys, passwords). Store only minimal metadata.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .paths import get_audit_log_path, get_logs_dir

# Max log size before rotation (about 10 MB)
_MAX_LOG_BYTES = 10 * 1024 * 1024
_MAX_BACKUPS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_rotate(path: str) -> None:
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_LOG_BYTES:
            # Rotate: app_audit.log -> app_audit.log.1 ... up to _MAX_BACKUPS-1
            for i in reversed(range(1, _MAX_BACKUPS)):
                src = f"{path}.{i}"
                dst = f"{path}.{i+1}"
                if os.path.exists(src):
                    try:
                        os.replace(src, dst)
                    except Exception:
                        pass
            try:
                os.replace(path, f"{path}.1")
            except Exception:
                pass
    except Exception:
        pass


def log_event(actor: str, action: str, subject: Optional[str] = None, outcome: str = "success", meta: Optional[Dict[str, Any]] = None) -> None:
    """Append a single audit event as JSON to the log.

    actor: who initiated (e.g., admin username)
    action: what happened (e.g., 'issue_key', 'replace_key', 'delete_user', 'reset_password')
    subject: target entity (e.g., username or resource id)
    outcome: 'success' | 'error'
    meta: small dict of non-sensitive details
    """
    path = get_audit_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _ensure_rotate(path)
    rec = {
        "ts": _now_iso(),
        "actor": actor,
        "action": action,
        "subject": subject,
        "outcome": outcome,
        "meta": meta or {},
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # best-effort; do not crash app on logging failure
        pass


def read_log_lines(limit: int = 2000) -> List[str]:
    """Return up to 'limit' most recent lines from the audit log (and first rotated file if needed)."""
    path = get_audit_log_path()
    lines: List[str] = []
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        # Consider also first rotated file if current has few lines
        if len(lines) < limit and os.path.exists(f"{path}.1"):
            with open(f"{path}.1", "r", encoding="utf-8") as f:
                extra = f.readlines()
                take = min(limit - len(lines), len(extra))
                lines = extra[-take:] + lines
    except Exception:
        pass
    return [ln.rstrip("\n") for ln in lines]


def search_logs(query: str, limit: int = 1000) -> List[str]:
    """Simple case-insensitive substring search across recent log lines."""
    q = (query or "").lower()
    if not q:
        return read_log_lines(limit)
    return [ln for ln in read_log_lines(limit * 5) if q in ln.lower()][:limit]


def get_log_file_bytes() -> bytes:
    """Return the current audit log file content (not rotated files)."""
    path = get_audit_log_path()
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return b""
