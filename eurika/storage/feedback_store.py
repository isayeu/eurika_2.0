"""
FeedbackStore — append-only storage for manual feedback (R2 consolidation).

Moved from architecture_feedback.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_FEEDBACK_FILE = "architecture_feedback.json"

__all__ = ["FeedbackRecord", "FeedbackStore", "DEFAULT_FEEDBACK_FILE"]


@dataclass
class FeedbackRecord:
    """Single feedback item for a DecisionProposal."""

    timestamp: float
    project_root: str
    action: str
    outcome: str
    target: Optional[str] = None
    comment: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "FeedbackRecord":
        return FeedbackRecord(
            timestamp=d.get("timestamp", time.time()),
            project_root=d.get("project_root", ""),
            action=d.get("action", ""),
            outcome=d.get("outcome", ""),
            target=d.get("target"),
            comment=d.get("comment"),
        )


class FeedbackStore:
    """Append-only feedback storage."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or Path(DEFAULT_FEEDBACK_FILE)
        self._records: List[FeedbackRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._records = [
                FeedbackRecord.from_dict(item) for item in raw.get("feedback", [])
            ]
        except (json.JSONDecodeError, OSError):
            self._records = []

    def _save(self) -> None:
        data = {"feedback": [r.to_dict() for r in self._records]}
        try:
            self.storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def append(
        self,
        project_root: Path,
        action: str,
        outcome: str,
        target: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> None:
        """Append feedback item and persist to disk."""
        record = FeedbackRecord(
            timestamp=time.time(),
            project_root=str(project_root),
            action=action,
            outcome=outcome,
            target=target,
            comment=comment,
        )
        self._records.append(record)
        self._save()

    def all(self) -> List[FeedbackRecord]:
        """Return a read-only snapshot of all feedback records."""
        return list(self._records)

    def aggregate_by_action(self) -> Dict[str, Dict[str, int]]:
        """Aggregate feedback by action and outcome."""
        stats: Dict[str, Dict[str, int]] = {}
        for r in self._records:
            by_action = stats.setdefault(r.action, {})
            by_action[r.outcome] = by_action.get(r.outcome, 0) + 1
        return stats
