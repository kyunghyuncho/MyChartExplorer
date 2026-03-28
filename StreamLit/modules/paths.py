"""Centralized path helpers for the Streamlit app.

Resolves data locations based on the DATADIR environment variable.

If DATADIR is set, we store/read these under that directory:
- config.yaml
- config.json (global, when not logged in)
- user_data/<username> (per-user data: db, config.json, conversations)

If DATADIR is not set, we fall back to the repository's StreamLit folder
as the data root, matching the current behavior.
"""

from __future__ import annotations

import os
from pathlib import Path


def _streamlit_root() -> Path:
    # modules/paths.py -> modules -> StreamLit
    return Path(__file__).resolve().parent.parent


def get_data_root() -> Path:
    env = os.environ.get("DATADIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _streamlit_root()


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    # Best-effort: restrict to user-only access
    try:
        import os as _os
        _os.chmod(p, 0o700)
    except Exception:
        pass
    return p


def get_config_yaml_path() -> str:
    return (get_data_root() / "config.yaml").as_posix()


def get_global_config_json_path() -> str:
    # Used when no user is logged in
    return (get_data_root() / "config.json").as_posix()


def get_user_data_base() -> Path:
    return _ensure_dir(get_data_root() / "user_data")


def get_user_dir(username: str) -> Path:
    return _ensure_dir(get_user_data_base() / username)


def get_user_db_path(username: str) -> str:
    return (get_user_dir(username) / "mychart.db").as_posix()


def get_user_config_json_path(username: str) -> str:
    return (get_user_dir(username) / "config.json").as_posix()


def get_conversations_dir(username: str) -> str:
    return _ensure_dir(get_user_dir(username) / "conversations").as_posix()


def get_invitations_json_path() -> str:
    """Return the path to the invitations store JSON under the data root.

    This file holds pending/used invitation codes for registration.
    """
    return (get_data_root() / "invitations.json").as_posix()


# -------- Audit logging paths --------
def get_logs_dir() -> Path:
    return _ensure_dir(get_data_root() / "logs")


def get_audit_log_path() -> str:
    return (get_logs_dir() / "app_audit.log").as_posix()
