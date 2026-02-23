"""
Unified memory facade (Memory + Events + Decisions).

Single entry point for project-scoped persistence.
All artifacts live under project_root/.eurika/ (ROADMAP 3.2.1).
Event as primary (ROADMAP 3.2.2): learning and feedback are views over EventStore.

- events: unified event log (events.json) — primary store
- learning: view over events (type=learn)
- feedback: view over events (type=feedback)
- observations: scan observations (observations.json)
- history: architecture evolution snapshots (history.json)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .paths import ensure_storage_dir, migrate_if_needed, storage_path

if TYPE_CHECKING:
    from .event_views import FeedbackView, LearningView
    from observation_memory import ObservationMemory
    from eurika.evolution.history import ArchitectureHistory
    from eurika.storage.event_engine import EventStore

# Lazy: feedback and learning are views over EventStore (ROADMAP 3.2.2)
def _feedback_view(events: "EventStore", path: Path) -> "FeedbackView":
    migrate_if_needed(path, "feedback")
    ensure_storage_dir(path)
    from .event_views import FeedbackView
    return FeedbackView(events, path)

def _learning_view(events: "EventStore", path: Path) -> "LearningView":
    migrate_if_needed(path, "learning")
    ensure_storage_dir(path)
    from .event_views import LearningView
    return LearningView(events, path)

def _observation_memory(path: Path) -> "ObservationMemory":
    migrate_if_needed(path, "observations")
    ensure_storage_dir(path)
    from observation_memory import ObservationMemory
    return ObservationMemory(storage_path=storage_path(path, "observations"))

def _architecture_history(path: Path) -> "ArchitectureHistory":
    migrate_if_needed(path, "history")
    ensure_storage_dir(path)
    from eurika.evolution.history import ArchitectureHistory
    return ArchitectureHistory(storage_path=storage_path(path, "history"))

def _event_store(path: Path) -> "EventStore":
    migrate_if_needed(path, "events")
    ensure_storage_dir(path)
    from eurika.storage.event_engine import event_engine
    return event_engine(path)


class ProjectMemory:
    """
    One contract, one entry point for all project-scoped memory.

    Events: observations (scan), history (evolution snapshots).
    Decisions / outcomes: feedback (user), learning (patch-apply + verify).
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    @property
    def events(self) -> "EventStore":
        """Unified event log. File: .eurika/events.json."""
        if not hasattr(self, "_events"):
            self._events = _event_store(self.project_root)
        return self._events

    @property
    def feedback(self) -> "FeedbackView":
        """Manual feedback — view over events (type=feedback)."""
        if not hasattr(self, "_feedback"):
            self._feedback = _feedback_view(self.events, self.project_root)
        return self._feedback

    @property
    def learning(self) -> "LearningView":
        """Outcomes of patch-apply + verify — view over events (type=learn)."""
        if not hasattr(self, "_learning"):
            self._learning = _learning_view(self.events, self.project_root)
        return self._learning

    @property
    def observations(self) -> "ObservationMemory":
        """Scan observations. File: .eurika/observations.json."""
        if not hasattr(self, "_observations"):
            self._observations = _observation_memory(self.project_root)
        return self._observations

    @property
    def history(self):
        """Architecture evolution snapshots. File: .eurika/history.json."""
        if not hasattr(self, "_history"):
            self._history = _architecture_history(self.project_root)
        return self._history

    def record_scan(self, observation: dict) -> None:
        """
        Record scan observation and append scan event.
        Extracted from runtime_scan to reduce god_module (ROADMAP 3.1).
        """
        try:
            self.observations.record_observation("scan", observation)
            summary = (observation.get("summary", {}) or {}) if isinstance(observation, dict) else {}
            self.events.append_event(
                type="scan",
                input={"path": str(self.project_root)},
                output={
                    "files": summary.get("files", 0),
                    "total_lines": summary.get("total_lines", 0),
                    "smells_count": summary.get("smells_count", 0),
                },
                result=True,
            )
        except Exception:
            pass
