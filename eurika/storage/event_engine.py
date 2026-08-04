"""
Event Engine (ROADMAP этап 4 / review.md).

Единая точка входа для всего журнала событий: Event { type, input, action, result, timestamp }.
Хранение в project_root/.eurika/events.json (ROADMAP 3.2.1).

Использование:
    from eurika.storage.event_engine import event_engine, Event, EventStore
    store = event_engine(project_root)
    store.append_event("scan", {"path": str(path)}, {"files": 10}, result=True)
    for e in store.by_type("patch"):
        ...
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .events import Event, EventStore
from .paths import storage_path

if TYPE_CHECKING:
    pass

__all__ = ["Event", "EventStore", "event_engine"]


def event_engine(project_root: Path) -> EventStore:
    """Единая точка входа: хранилище событий. Файл: .eurika/events.json."""
    root = Path(project_root).resolve()
    return EventStore(storage_path=storage_path(root, "events"))
