import json
import os
import time
from typing import List, Dict, Any

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "conversations")
BASE_DIR = os.path.abspath(BASE_DIR)

def _ensure_dir() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)

def _slugify(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".", " ") else "-" for c in name).strip()
    safe = "-".join(safe.split())
    return safe[:100] or f"session-{int(time.time())}"

def list_conversations() -> List[Dict[str, Any]]:
    _ensure_dir()
    items = []
    for fname in sorted(os.listdir(BASE_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(BASE_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                items.append({
                    "id": fname[:-5],
                    "title": meta.get("title") or fname[:-5],
                    "created_at": meta.get("created_at"),
                    "updated_at": meta.get("updated_at"),
                })
            except Exception:
                continue
    # Newest first
    items.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    return items

def save_conversation(messages: List[Dict[str, str]], title: str | None = None, conv_id: str | None = None) -> str:
    _ensure_dir()
    now = int(time.time())
    if not conv_id:
        base = _slugify(title or (messages[0]["content"][:50] if messages else f"session-{now}"))
        conv_id = f"{base}-{now}"
    path = os.path.join(BASE_DIR, f"{conv_id}.json")
    data = {
        "id": conv_id,
        "title": title or messages[0]["content"][:80] if messages else conv_id,
        "created_at": now,
        "updated_at": now,
        "messages": messages,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return conv_id

def load_conversation(conv_id: str) -> Dict[str, Any] | None:
    _ensure_dir()
    path = os.path.join(BASE_DIR, f"{conv_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def delete_conversation(conv_id: str) -> None:
    _ensure_dir()
    path = os.path.join(BASE_DIR, f"{conv_id}.json")
    if os.path.exists(path):
        os.remove(path)
