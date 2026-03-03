"""Storage / persistence façade."""

from .event_engine import Event, EventStore, event_engine  # noqa: F401
from .experience_store import (  # noqa: F401
    ExperienceStore,
    get_recent_failures,
    get_statistics,
    record_outcome,
)
from .memory import ProjectMemory  # noqa: F401
from .operational_metrics import aggregate_operational_metrics  # noqa: F401
from .session_memory import SessionMemory, operation_key  # noqa: F401
from .state_store import (  # noqa: F401
    has_checkpoint,
    load_checkpoint,
    save_checkpoint,
    snapshot_from_checkpoint,
)

__all__ = [
    "ProjectMemory",
    "Event",
    "EventStore",
    "event_engine",
    "ExperienceStore",
    "record_outcome",
    "get_recent_failures",
    "get_statistics",
    "SessionMemory",
    "operation_key",
    "aggregate_operational_metrics",
    "save_checkpoint",
    "load_checkpoint",
    "has_checkpoint",
    "snapshot_from_checkpoint",
]

