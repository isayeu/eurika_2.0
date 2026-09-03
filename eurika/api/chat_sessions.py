"""Per-workspace chat threads (Cursor-like: folder = workspace, children = chats)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

DEFAULT_CHAT_ID = "default"
DEFAULT_CHAT_TITLE = "чат"
_SESSIONS_NAME = "sessions.json"


def _history_dir(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / ".eurika" / "chat_history"


def load_sessions(project_root: Path) -> dict[str, Any]:
    path = _history_dir(project_root) / _SESSIONS_NAME
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            data = {}
    chats = data.get("chats")
    if not isinstance(chats, list) or not chats:
        chats = [{"id": DEFAULT_CHAT_ID, "title": DEFAULT_CHAT_TITLE}]
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in chats:
        if not isinstance(item, dict):
            continue
        chat_id = str(item.get("id") or "").strip() or DEFAULT_CHAT_ID
        if chat_id in seen:
            continue
        seen.add(chat_id)
        title = str(item.get("title") or "").strip() or DEFAULT_CHAT_TITLE
        cleaned.append({"id": chat_id, "title": title})
    if not cleaned:
        cleaned = [{"id": DEFAULT_CHAT_ID, "title": DEFAULT_CHAT_TITLE}]
    active = str(data.get("active") or DEFAULT_CHAT_ID).strip() or DEFAULT_CHAT_ID
    if active not in {item["id"] for item in cleaned}:
        active = cleaned[0]["id"]
    return {"active": active, "chats": cleaned}


def save_sessions(project_root: Path, payload: dict[str, Any]) -> None:
    folder = _history_dir(project_root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / _SESSIONS_NAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_chats(project_root: Path) -> list[dict[str, str]]:
    chats = load_sessions(project_root)["chats"]
    return [item for item in chats if isinstance(item, dict)]


def active_chat_id(project_root: Path) -> str:
    return str(load_sessions(project_root).get("active") or DEFAULT_CHAT_ID)


def set_active_chat(project_root: Path, chat_id: str) -> None:
    data = load_sessions(project_root)
    wanted = str(chat_id or DEFAULT_CHAT_ID).strip() or DEFAULT_CHAT_ID
    ids = {str(item.get("id")) for item in data["chats"]}
    if wanted not in ids:
        wanted = str(data["chats"][0]["id"])
    data["active"] = wanted
    save_sessions(project_root, data)


def add_chat(project_root: Path, title: str | None = None) -> dict[str, str]:
    data = load_sessions(project_root)
    n = len(data["chats"]) + 1
    chat_id = uuid.uuid4().hex[:10]
    label = (title or "").strip() or f"{DEFAULT_CHAT_TITLE} {n}"
    created = {"id": chat_id, "title": label}
    data["chats"].append(created)
    data["active"] = chat_id
    save_sessions(project_root, data)
    return created


def rename_chat(project_root: Path, chat_id: str, title: str) -> dict[str, str] | None:
    data = load_sessions(project_root)
    wanted = str(chat_id or "").strip()
    label = (title or "").strip()
    if not wanted or not label:
        return None
    for item in data["chats"]:
        if str(item.get("id")) == wanted:
            item["title"] = label
            save_sessions(project_root, data)
            return item
    return None


def remove_chat(project_root: Path, chat_id: str) -> bool:
    data = load_sessions(project_root)
    wanted = str(chat_id or "").strip()
    chats = list(data["chats"])
    if not wanted or len(chats) < 2:
        return False
    remaining = [item for item in chats if str(item.get("id")) != wanted]
    if len(remaining) == len(chats):
        return False
    data["chats"] = remaining
    if str(data.get("active")) == wanted:
        data["active"] = str(remaining[0]["id"])
    save_sessions(project_root, data)
    if wanted != DEFAULT_CHAT_ID:
        extra = _history_dir(project_root) / "chats" / f"{wanted}.jsonl"
        try:
            extra.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def transcript_path(project_root: Path, chat_id: str | None = None) -> Path:
    """Default thread stays at chat.jsonl; extra threads live in chats/{id}.jsonl."""
    folder = _history_dir(project_root)
    cid = str(chat_id or active_chat_id(project_root) or DEFAULT_CHAT_ID).strip() or DEFAULT_CHAT_ID
    if cid == DEFAULT_CHAT_ID:
        return folder / "chat.jsonl"
    return folder / "chats" / f"{cid}.jsonl"
