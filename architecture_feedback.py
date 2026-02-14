"""
Architecture Feedback v0.2 (draft)

Stores manual feedback about AgentCore proposals (read-only evaluation).

Scope:
- append-only JSON file in project root (architecture_feedback.json);
- no influence on AgentCore behaviour yet (analysis-only).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_FEEDBACK_FILE = "architecture_feedback.json"


@dataclass
class FeedbackRecord:
    """Single feedback item for a DecisionProposal."""

    timestamp: float
    project_root: str
    action: str         # e.g. "explain_risk", "summarize_evolution"
    outcome: str        # e.g. "accepted", "rejected", "ignored"
    target: Optional[str] = None  # file/module or smell id
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
    """
    Append-only feedback storage.

    v0.2: analysis-only, no behavioural changes based on feedback.
    """

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
            # On any failure, start with empty feedback.
            self._records = []

    def _save(self) -> None:
        data = {"feedback": [r.to_dict() for r in self._records]}
        try:
            self.storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            # Feedback is non-critical; ignore save failures.
            pass

    # Public API -----------------------------------------------------
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
        """
        Aggregate feedback by action and outcome.

        Returns:
            {
              "explain_risk": {"accepted": N1, "rejected": N2, ...},
              "summarize_evolution": {"accepted": ..., ...},
            }
        """
        stats: Dict[str, Dict[str, int]] = {}
        for r in self._records:
            by_action = stats.setdefault(r.action, {})
            by_action[r.outcome] = by_action.get(r.outcome, 0) + 1
        return stats

