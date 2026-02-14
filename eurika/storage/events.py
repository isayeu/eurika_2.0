"""
Unified Event model (ROADMAP 2.1 / review.md).

Single event type for all memory/logging:
  Event { type, input, output, result, timestamp }

Types: "scan", "diagnose", "plan", "patch", "verify", "learn".
Persisted to project_root/eurika_events.json (append-only).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


EVENTS_FILE = "eurika_events.json"
MAX_EVENTS = 500


@dataclass
class Event:
    """Single event in the unified log."""

    type: str  # "scan" | "diagnose" | "plan" | "patch" | "verify" | "learn"
    input: Dict[str, Any]  # JSON-serializable
    output: Dict[str, Any]  # JSON-serializable
    result: Optional[Any] = None  # bool, str, or None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Event":
        return Event(
            type=d.get("type", ""),
            input=d.get("input", {}),
            output=d.get("output", {}),
            result=d.get("result"),
            timestamp=float(d.get("timestamp", time.time())),
        )


def _json_safe(obj: Any) -> Any:
    """Reduce to JSON-serializable (truncate long strings, drop non-serializable)."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        if isinstance(obj, str) and len(obj) > 2000:
            return obj[:2000] + "..."
        return obj
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)[:500]


class EventStore:
    """Append-only store for unified events. File: eurika_events.json."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or Path(EVENTS_FILE)
        self._events: List[Event] = []
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._events = [Event.from_dict(item) for item in raw.get("events", [])]
        except (json.JSONDecodeError, OSError):
            self._events = []

    def _save(self) -> None:
        data = {"events": [e.to_dict() for e in self._events[-MAX_EVENTS:]]}
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def append_event(
        self,
        type: str,
        input: Dict[str, Any],
        output: Dict[str, Any],
        result: Optional[Any] = None,
    ) -> None:
        """Append one event and persist. input/output are normalized to JSON-safe."""
        event = Event(
            type=type,
            input=_json_safe(input),
            output=_json_safe(output),
            result=result,
        )
        self._events.append(event)
        self._save()

    def all(self) -> List[Event]:
        """Return read-only snapshot of events (last MAX_EVENTS)."""
        return list(self._events[-MAX_EVENTS:])

    def by_type(self, type: str) -> List[Event]:
        """Return events of given type."""
        return [e for e in self._events if e.type == type]
