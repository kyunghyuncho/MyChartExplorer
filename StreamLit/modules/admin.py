import io
import os
import json
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from sqlalchemy import inspect, text

from .paths import (
    get_config_yaml_path,
    get_user_dir,
    get_user_db_path,
    get_conversations_dir,
)
from .database import get_db_engine


def _load_config() -> Dict[str, Any]:
    path = Path(get_config_yaml_path())
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f, Loader=SafeLoader) or {}


def _save_config(cfg: Dict[str, Any]) -> None:
    path = Path(get_config_yaml_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False)


def list_users() -> List[Tuple[str, Dict[str, Any]]]:
    cfg = _load_config()
    users = ((cfg.get("credentials") or {}).get("usernames") or {})
    return sorted(users.items(), key=lambda x: x[0].lower())


def is_superuser(username: str) -> bool:
    for uname, data in list_users():
        if uname == username:
            return bool((data or {}).get("superuser", False))
    return False


def set_superuser(username: str, value: bool) -> None:
    cfg = _load_config()
    users = cfg.setdefault("credentials", {}).setdefault("usernames", {})
    user = users.setdefault(username, {})
    user["superuser"] = bool(value)
    _save_config(cfg)


def reset_password(username: str) -> str:
    """Generate a temporary password and update the stored hash for the user.

    Returns the plain temp password (to be shown once to the admin for delivery).
    """
    cfg = _load_config()
    users = cfg.setdefault("credentials", {}).setdefault("usernames", {})
    if username not in users:
        raise ValueError("User not found")
    temp_password = stauth.Hasher.generate_random_password(length=12)
    hashed = stauth.Hasher([temp_password]).generate()[0]
    users[username]["password"] = hashed
    _save_config(cfg)
    return temp_password


def _get_user_key(username: str) -> str | None:
    cfg = _load_config()
    users = ((cfg.get("credentials") or {}).get("usernames") or {})
    return (users.get(username) or {}).get("db_encryption_key")


def get_user_db_key(username: str) -> str | None:
    """Public helper to retrieve a user's DB/conversation key from config.yaml."""
    return _get_user_key(username)


def _fernet_from_key(key: str):
    from cryptography.fernet import Fernet
    import base64
    if not key:
        return None
    if len(key) < 32:
        key = key.ljust(32, "0")
    key_bytes = key[:32].encode("utf-8")
    safe_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(safe_key)


def export_user_zip(username: str, mode: str = "encrypted", include_key: bool = False) -> bytes:
    """Create an in-memory zip of a user's data.

    mode:
      - "encrypted": zip the on-disk files as-is (default). Optionally include key.txt if include_key is True.
      - "decrypted": export DB tables to JSON and decrypt conversations to JSON.
    """
    user_path = Path(get_user_dir(username))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        if mode == "encrypted":
            if user_path.exists():
                for root, dirs, files in os.walk(user_path):
                    for name in files:
                        full = Path(root) / name
                        arc = str(full.relative_to(user_path.parent))
                        z.write(full, arc)
            if include_key:
                key = _get_user_key(username) or ""
                z.writestr(f"user_data/{username}/key.txt", key)

        # Decrypted export
        # 1) DB dump -> JSON files per table
        db_path = get_user_db_path(username)
        key = _get_user_key(username)
        try:
            engine = get_db_engine(db_path, key=key)
            insp = inspect(engine)
            tables = insp.get_table_names()
            for t in tables:
                rows = []
                with engine.connect() as conn:
                    # Use unparameterized SELECT * for simplicity
                    res = conn.execute(text(f"SELECT * FROM {t}"))
                    cols = res.keys()
                    for r in res.fetchall():
                        rows.append({c: r[i] for i, c in enumerate(cols)})
                z.writestr(f"export/db/{t}.json", json.dumps(rows, ensure_ascii=False, indent=2))
        except Exception as e:
            z.writestr("export/db/ERROR.txt", f"Failed to export DB: {e}")

        # 2) Conversations -> decrypted JSON
        conv_dir = Path(get_conversations_dir(username))
        if conv_dir.exists():
            fernet = _fernet_from_key(key) if key else None
            for fname in os.listdir(conv_dir):
                if not fname.endswith(".enc"):
                    continue
                full = conv_dir / fname
                conv_id = fname[:-4]
                try:
                    data = full.read_bytes()
                    if fernet:
                        from cryptography.fernet import InvalidToken
                        try:
                            dec = fernet.decrypt(data)
                            z.writestr(f"export/conversations/{conv_id}.json", dec)
                        except InvalidToken:
                            # fallback: include encrypted file if key mismatch
                            z.writestr(f"export/conversations/{fname}", data)
                    else:
                        # no key available: include encrypted file
                        z.writestr(f"export/conversations/{fname}", data)
                except Exception as e:
                    z.writestr(f"export/conversations/{conv_id}.ERROR.txt", str(e))

    # Ensure zip is closed before reading
    buf.seek(0)
    return buf.read()


def delete_user_data(username: str) -> None:
    user_path = Path(get_user_dir(username))
    if user_path.exists():
        shutil.rmtree(user_path)
