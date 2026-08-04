"""
Memory — alias над eurika.storage (TARGET_V3_STRUCTURE §4, R6).

Re-exports EventLog, LearningStore, ExperienceStore, weight persistence.
Импорт: from eurika.memory import record_outcome, ProjectMemory, save_checkpoint
"""

from __future__ import annotations

from eurika.storage import (
    ProjectMemory,
    event_engine,
    get_recent_failures,
    get_recent_failures_enriched,
    get_statistics,
    has_checkpoint,
    load_checkpoint,
    record_outcome,
    save_checkpoint,
    snapshot_from_checkpoint,
)
from eurika.storage.event_engine import Event, EventStore
from eurika.storage.experience_store import ExperienceStore

__all__ = [
    "Event",
    "EventStore",
    "ExperienceStore",
    "ProjectMemory",
    "event_engine",
    "get_recent_failures",
    "get_recent_failures_enriched",
    "get_statistics",
    "has_checkpoint",
    "load_checkpoint",
    "record_outcome",
    "save_checkpoint",
    "snapshot_from_checkpoint",
]
