"""Persistent, workspace-scoped conversation history for agent clients."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionHistory:
    """Store recent user/assistant messages in the shared Eurika chat log."""

    def __init__(self, workspace_root: Path) -> None:
        self.path = workspace_root / ".eurika" / "chat_history" / "chat.jsonl"

    def load(self, limit: int = 80) -> list[dict[str, str]]:
        if limit <= 0 or not self.path.is_file():
            return []
        recent: deque[dict[str, str]] = deque(maxlen=min(limit, 200))
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        record: Any = json.loads(line)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    role = str(record.get("role") or "").strip().lower()
                    content = str(record.get("content") or "").strip()
                    if role in {"user", "assistant"} and content:
                        recent.append({"role": role, "content": content})
        except OSError:
            return []
        return list(recent)

    def append(self, role: str, content: str) -> None:
        normalized_role = role.strip().lower()
        normalized_content = content.strip()
        if normalized_role not in {"user", "assistant"} or not normalized_content:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "role": normalized_role,
            "content": normalized_content[:10000],
            "context_snapshot": None,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # History must never break an agent turn.
            return

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            return
