"""
Unified memory facade (Memory + Events + Decisions).

Single entry point for project-scoped persistence:
- events: unified event log (eurika_events.json) — type, input, output, result, timestamp
- feedback: manual feedback on proposals (architecture_feedback.json)
- learning: outcomes of patch-apply + verify (architecture_learning.json)
- observations: scan observations (eurika_observations.json)
- history: architecture evolution snapshots (architecture_history.json)

Callers use ProjectMemory(project_root) and access .feedback, .learning,
.observations, .history instead of constructing stores and paths manually.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from architecture_feedback import FeedbackStore
    from architecture_learning import LearningStore
    from observation_memory import ObservationMemory
    from eurika.storage.events import EventStore

# Lazy imports to avoid pulling flat modules at eurika.storage import time
# when only history is needed (e.g. from eurika.api).
def _feedback_store(path: Path):
    from architecture_feedback import FeedbackStore
    return FeedbackStore(storage_path=path / "architecture_feedback.json")

def _learning_store(path: Path):
    from architecture_learning import LearningStore
    return LearningStore(storage_path=path / "architecture_learning.json")

def _observation_memory(path: Path):
    from observation_memory import ObservationMemory
    return ObservationMemory(storage_path=path / "eurika_observations.json")

def _architecture_history(path: Path):
    from eurika.evolution.history import ArchitectureHistory
    return ArchitectureHistory(storage_path=path / "architecture_history.json")

def _event_store(path: Path):
    from eurika.storage.events import EventStore
    return EventStore(storage_path=path / "eurika_events.json")


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
        """Unified event log. File: eurika_events.json."""
        if not hasattr(self, "_events"):
            self._events = _event_store(self.project_root)
        return self._events

    @property
    def feedback(self) -> "FeedbackStore":
        """Manual feedback on proposals. File: architecture_feedback.json."""
        if not hasattr(self, "_feedback"):
            self._feedback = _feedback_store(self.project_root)
        return self._feedback

    @property
    def learning(self) -> "LearningStore":
        """Outcomes of patch-apply + verify. File: architecture_learning.json."""
        if not hasattr(self, "_learning"):
            self._learning = _learning_store(self.project_root)
        return self._learning

    @property
    def observations(self) -> "ObservationMemory":
        """Scan observations. File: eurika_observations.json."""
        if not hasattr(self, "_observations"):
            self._observations = _observation_memory(self.project_root)
        return self._observations

    @property
    def history(self):
        """Architecture evolution snapshots. File: architecture_history.json."""
        if not hasattr(self, "_history"):
            self._history = _architecture_history(self.project_root)
        return self._history
