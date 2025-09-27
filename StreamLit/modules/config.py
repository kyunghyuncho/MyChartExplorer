"""Configuration utilities for Streamlit app.

Provides persistent settings across reruns by reading/writing a JSON file
and syncing with Streamlit's session_state.
"""

from __future__ import annotations

import json
from pathlib import Path
import streamlit as st


# Where to store settings on disk (project-local)
CONFIG_PATH = (Path(__file__).resolve().parent.parent / "config.json").as_posix()


def _default_config() -> dict:
    return {
        "llm_provider": "ollama",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "llama3",
        "gemini_api_key": "",
        "gemini_model": "gemini-1.5-flash",
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
    path = Path(CONFIG_PATH)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        # On any parse error, fall back to defaults without crashing the UI
        return {}


def _write_file_config(cfg: dict) -> None:
    path = Path(CONFIG_PATH)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
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
    file_cfg = _read_file_config()
    # session values take precedence during this run if already set
    session_overlay = {k: st.session_state.get(k) for k in defaults.keys() if k in st.session_state}
    cfg = _merge(defaults, _merge(file_cfg, session_overlay))

    # Sync into session_state for consistent access across pages
    for k, v in cfg.items():
        st.session_state[k] = v
    return cfg


def save_configuration(config: dict) -> None:
    """Save config to disk and update session_state.

    Note: This stores values in plain text JSON inside the project directory.
    For secrets, consider environment variables or Streamlit's secrets for read-only.
    """
    # Merge with existing on disk to avoid dropping unknown keys
    current = _merge(_default_config(), _read_file_config())
    new_cfg = _merge(current, config or {})
    _write_file_config(new_cfg)

    # Reflect into session_state immediately
    for k, v in new_cfg.items():
        st.session_state[k] = v
