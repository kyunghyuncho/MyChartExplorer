"""Configuration utilities for Streamlit app.

Provides persistent settings across reruns by reading/writing a JSON file
and syncing with Streamlit's session_state.
"""

from __future__ import annotations

import json
from pathlib import Path
import streamlit as st
from .paths import get_global_config_json_path


# Default config path (project-local); can be overridden per-user via session_state['config_path']
DEFAULT_CONFIG_PATH = get_global_config_json_path()


def _get_active_config_path() -> str:
    """Return the config.json path to use.

    If st.session_state['config_path'] is set (by authenticated Home page), use that
    so each user gets an isolated config. Otherwise fall back to the default path.
    """
    try:
        path = st.session_state.get("config_path")
        if isinstance(path, str) and path.strip():
            return path
    except Exception:
        pass
    return DEFAULT_CONFIG_PATH


def _default_config() -> dict:
    return {
    "llm_provider": "gemini",
    "ollama_url": "",
        "ollama_model": "gpt-oss:20b",
        "gemini_api_key": "",
    "gemini_model": "gemini-2.5-pro",
    # Automatically run consultation after retrieval completes
    "auto_consult": True,
    # Max allowed size for the user's SQLite DB in megabytes
    "db_size_limit_mb": 100,
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_user": "",
        "ssh_password": "",
    "ssh_private_key": "",
    "ssh_passphrase": "",
        "remote_ollama_url": "http://localhost:11434",
    "local_tunnel_port": 11435,
    }


def _read_file_config() -> dict:
    path = Path(_get_active_config_path())
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        # On any parse error, fall back to defaults without crashing the UI
        return {}


def _write_file_config(cfg: dict) -> None:
    path = Path(_get_active_config_path())
    # Ensure parent directory exists (for per-user paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        # Restrict permissions to user read/write only
        try:
            import os as _os
            _os.chmod(path, 0o600)
        except Exception:
            pass
    except Exception:
        # If writing fails, still keep session_state updated
        pass


def _merge(base: dict, override: dict) -> dict:
    merged = {**base}
    merged.update({k: v for k, v in (override or {}).items() if v is not None})
    return merged


def load_configuration() -> dict:
    """Load config from disk, then overlay session_state, and return result.

    Also syncs the loaded values back into session_state so other pages see them.
    """
    defaults = _default_config()
    allowed_keys = set(defaults.keys())
    file_cfg_raw = _read_file_config()
    # Only allow known config keys from disk
    file_cfg = {k: v for k, v in (file_cfg_raw or {}).items() if k in allowed_keys}
    # Session values take precedence during this run if already set (only known keys)
    session_overlay = {k: st.session_state.get(k) for k in allowed_keys if k in st.session_state}
    cfg = _merge(defaults, _merge(file_cfg, session_overlay))

    # Sync into session_state for consistent access across pages
    for k, v in cfg.items():
        st.session_state[k] = v
    return cfg


def save_configuration(config: dict) -> None:
    """Save config to disk.

    Note: This stores values in plain text JSON inside the project directory.
    For secrets, consider environment variables or Streamlit's secrets for read-only.
    This function intentionally does NOT mutate session_state to avoid widget
    value conflicts. Callers should update session_state explicitly before
    invoking this function.
    """
    # Merge with existing on disk to avoid dropping unknown keys
    defaults = _default_config()
    allowed_keys = set(defaults.keys())
    current_raw = _merge(defaults, _read_file_config())
    current = {k: v for k, v in current_raw.items() if k in allowed_keys}
    # Only persist known keys
    filtered = {k: v for k, v in (config or {}).items() if k in allowed_keys}
    new_cfg = _merge(current, filtered)
    _write_file_config(new_cfg)


# -------- Admin/global settings helpers --------
def _read_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with p.open("w", encoding="utf-8") as f:
            json.dump(data or {}, f, indent=2)
    except Exception:
        pass


def get_db_size_limit_mb() -> int:
    """Return the global DB size limit (MB), defaulting to 100 if unset.

    This reads from the global config.json path, ignoring per-user overrides.
    """
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    try:
        val = int((data or {}).get("db_size_limit_mb", 100))
        return max(1, val)
    except Exception:
        return 100


def set_db_size_limit_mb(mb: int) -> None:
    """Persist the global DB size limit (MB) into the global config.json."""
    mb = int(mb)
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    data["db_size_limit_mb"] = max(1, mb)
    _write_json(global_path, data)


# -------- Global LLM preview limits (admin-only) --------
def get_preview_limits_global() -> tuple[int, int, int]:
    """Return (max_rows_per_set, char_budget_per_set, max_sets) from global config with defaults.

    Defaults: rows=20, char_budget=3000, sets=8
    """
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    def _get_int(name: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int((data or {}).get(name, default))
            return max(lo, min(hi, v))
        except Exception:
            return default
    rows = _get_int("preview_max_rows_per_set", 20, 1, 100)
    budget = _get_int("preview_char_budget_per_set", 3000, 500, 20000)
    sets = _get_int("preview_max_sets", 8, 1, 16)
    return rows, budget, sets


def set_preview_limits_global(max_rows_per_set: int, char_budget_per_set: int, max_sets: int) -> None:
    """Persist preview limits into the global config.json (admin-only)."""
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    def _clamp(v, lo, hi):
        try:
            v = int(v)
        except Exception:
            return lo
        return max(lo, min(hi, v))
    data["preview_max_rows_per_set"] = _clamp(max_rows_per_set, 1, 100)
    data["preview_char_budget_per_set"] = _clamp(char_budget_per_set, 500, 20000)
    data["preview_max_sets"] = _clamp(max_sets, 1, 16)
    _write_json(global_path, data)


# -------- Notes preview/summarization settings (admin-only) --------
def get_notes_snippet_max_chars() -> int:
    """Return the max characters to include for note content/snippets in previews.

    Default: 2000
    """
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    try:
        v = int((data or {}).get("notes_snippet_max_chars", 2000))
        return max(100, min(100000, v))
    except Exception:
        return 2000


def set_notes_snippet_max_chars(n: int) -> None:
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    try:
        n = int(n)
    except Exception:
        n = 2000
    data["notes_snippet_max_chars"] = max(100, min(100000, n))
    _write_json(global_path, data)


def get_notes_summarization_enabled() -> bool:
    """Return whether to summarize long notes in previews (admin toggle)."""
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    return bool((data or {}).get("notes_summarization_enabled", False))


def set_notes_summarization_enabled(enabled: bool) -> None:
    global_path = get_global_config_json_path()
    data = _read_json(global_path)
    data["notes_summarization_enabled"] = bool(enabled)
    _write_json(global_path, data)
