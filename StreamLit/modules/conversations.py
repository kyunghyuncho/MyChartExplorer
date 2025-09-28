import json
import os
import time
from typing import List, Dict, Any
from cryptography.fernet import Fernet
import base64
from .paths import get_conversations_dir

def _slugify(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".", " ") else "-" for c in name).strip()
    safe = "-".join(safe.split())
    return safe[:100] or f"session-{int(time.time())}"

def list_conversations(username: str, key: str) -> List[Dict[str, Any]]:
    conv_dir = get_user_conversations_dir(username)
    items = []
    for fname in sorted(os.listdir(conv_dir)):
        if fname.endswith(".enc"):
            path = os.path.join(conv_dir, fname)
            try:
                conv_id = fname[:-4]
                conv = load_conversation(conv_id, username, key)
                if conv:
                    items.append({
                        "id": conv_id,
                        "title": conv.get("title") or conv_id,
                        "created_at": conv.get("created_at"),
                        "updated_at": conv.get("updated_at"),
                    })
            except Exception:
                continue
    # Newest first
    items.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    return items

def save_conversation(messages: List[Dict[str, str]], username: str, key: str, title: str | None = None, conv_id: str | None = None) -> str:
    conv_dir = get_user_conversations_dir(username)
    fernet = _get_fernet(key)
    now = int(time.time())
    
    if not conv_id:
        base = _slugify(title or (messages[0]["content"][:50] if messages else f"session-{now}"))
        conv_id = f"{base}-{now}"
    
    path = os.path.join(conv_dir, f"{conv_id}.enc")
    
    data = {
        "id": conv_id,
        "title": title or (messages[0]["content"][:80] if messages else conv_id),
        "created_at": now,
        "updated_at": now,
        "messages": messages,
    }
    
    encrypted_data = fernet.encrypt(json.dumps(data).encode('utf-8'))
    
    with open(path, "wb") as f:
        f.write(encrypted_data)
    try:
        import os as _os
        _os.chmod(path, 0o600)
    except Exception:
        pass
        
    return conv_id

def load_conversation(conv_id: str, username: str, key: str) -> Dict[str, Any] | None:
    conv_dir = get_user_conversations_dir(username)
    path = os.path.join(conv_dir, f"{conv_id}.enc")
    
    if not os.path.exists(path):
        return None
        
    fernet = _get_fernet(key)
    
    with open(path, "rb") as f:
        encrypted_data = f.read()
        
    try:
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception:
        return None

def delete_conversation(conv_id: str, username: str) -> None:
    conv_dir = get_user_conversations_dir(username)
    path = os.path.join(conv_dir, f"{conv_id}.enc")
    if os.path.exists(path):
        os.remove(path)

def _get_fernet(key: str) -> Fernet:
    """Derive a valid Fernet key from the user's key."""
    # Fernet keys must be 32 bytes and URL-safe base64 encoded.
    # We'll use the first 32 bytes of the provided key and encode it.
    if len(key) < 32:
        # Pad the key if it's too short
        key = key.ljust(32, '0')
    key_bytes = key[:32].encode('utf-8')
    safe_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(safe_key)

def get_user_conversations_dir(username: str) -> str:
    """Get the path to the user's conversations directory."""
    return get_conversations_dir(username)
