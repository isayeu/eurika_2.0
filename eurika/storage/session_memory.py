"""Session memory for hybrid approval decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def operation_key(op: dict[str, Any]) -> str:
    """Stable key for storing approval/rejection decisions across runs."""
    target = str(op.get("target_file") or "")
    kind = str(op.get("kind") or "")
    location = str((op.get("params") or {}).get("location") or "")
    return f"{target}|{kind}|{location}"


@dataclass(slots=True)
class SessionMemory:
    """Persistent store for per-session operation decisions."""

    project_root: Path
    path: Path | None = None

    def __post_init__(self) -> None:
        root = Path(self.project_root).resolve()
        self.project_root = root
        self.path = root / ".eurika" / "session_memory.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"sessions": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"sessions": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def rejected_keys(self, session_id: str) -> set[str]:
        data = self._load()
        session = (data.get("sessions") or {}).get(session_id) or {}
        rejected = session.get("rejected_keys") or []
        return {str(x) for x in rejected}

    def record(
        self,
        session_id: str,
        *,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> None:
        data = self._load()
        sessions = data.setdefault("sessions", {})
        session = sessions.setdefault(session_id, {"approved_keys": [], "rejected_keys": []})
        approved_keys = set(str(x) for x in session.get("approved_keys", []))
        rejected_keys = set(str(x) for x in session.get("rejected_keys", []))
        approved_keys |= {operation_key(op) for op in approved}
        rejected_keys |= {operation_key(op) for op in rejected}
        session["approved_keys"] = sorted(approved_keys)
        session["rejected_keys"] = sorted(rejected_keys)
        self._save(data)
