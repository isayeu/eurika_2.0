"""
Architecture Learning v0.1 (draft)

Stores outcomes of self-refactoring runs (patch-apply + tests) and
aggregates simple statistics about which action kinds work better.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_LEARNING_FILE = "architecture_learning.json"


def _resolve_learning_outcome(op: Dict[str, Any], verify_success: Optional[bool]) -> str:
    """Resolve per-operation learning outcome for aggregation."""
    outcome = str(op.get("execution_outcome") or "").strip()
    if outcome in {"not_applied", "verify_success", "verify_fail"}:
        return outcome
    if op.get("applied") is False:
        return "not_applied"
    if verify_success is True:
        return "verify_success"
    if verify_success is False:
        return "verify_fail"
    return "not_applied"


@dataclass
class LearningRecord:
    """
    Single learning datapoint from a self-refactoring run.

    For now we keep it intentionally simple and coarse-grained.
    """

    timestamp: float
    project_root: str
    modules: List[str]
    operations: List[Dict[str, Any]]
    risks: List[str]
    verify_success: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LearningRecord":
        return LearningRecord(
            timestamp=d.get("timestamp", time.time()),
            project_root=d.get("project_root", ""),
            modules=list(d.get("modules", [])),
            operations=list(d.get("operations", [])),
            risks=list(d.get("risks", [])),
            verify_success=d.get("verify_success"),
        )


class LearningStore:
    """
    Append-only storage for learning records.

    v0.1: used for analysis + simple action-kind statistics.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path or Path(DEFAULT_LEARNING_FILE)
        self._records: List[LearningRecord] = []
        self._load()

    # Internal persistence --------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._records = [
                LearningRecord.from_dict(item) for item in raw.get("learning", [])
            ]
        except (json.JSONDecodeError, OSError):
            self._records = []

    def _save(self) -> None:
        data = {"learning": [r.to_dict() for r in self._records]}
        try:
            self.storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            # Learning is non-critical; ignore save failures.
            pass

    # Public API ------------------------------------------------------
    def append(
        self,
        project_root: Path,
        modules: List[str],
        operations: List[Dict[str, Any]],
        risks: List[str],
        verify_success: Optional[bool],
    ) -> None:
        """Append a new learning record and persist it."""
        record = LearningRecord(
            timestamp=time.time(),
            project_root=str(project_root),
            modules=list(modules),
            operations=list(operations),
            risks=list(risks),
            verify_success=verify_success,
        )
        self._records.append(record)
        self._save()

    def all(self) -> List[LearningRecord]:
        """Return a snapshot of all learning records."""
        return list(self._records)

    def aggregate_by_action_kind(self) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate success statistics per operation.kind.

        Returns:
            {
              "refactor_module": {"total": N, "success": M, "fail": K},
              ...
            }
        """
        stats: Dict[str, Dict[str, Any]] = {}
        for r in self._records:
            for op in r.operations:
                kind = op.get("kind", "unknown")
                by_kind = stats.setdefault(
                    kind,
                    {
                        "total": 0,
                        "success": 0,
                        "fail": 0,
                        "verify_success": 0,
                        "verify_fail": 0,
                        "not_applied": 0,
                    },
                )
                by_kind["total"] += 1
                outcome = _resolve_learning_outcome(op, r.verify_success)
                if outcome == "verify_success":
                    by_kind["verify_success"] += 1
                    if _is_strong_refactor_code_smell_success(op):
                        by_kind["success"] += 1
                elif outcome == "verify_fail":
                    by_kind["verify_fail"] += 1
                    by_kind["fail"] += 1
                else:
                    by_kind["not_applied"] += 1
        return stats

    def aggregate_by_smell_action(self) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate success statistics per (smell_type, action_kind) pair.

        Returns:
            {
              "god_module|refactor_module": {"total": N, "success": M, "fail": K},
              "bottleneck|introduce_facade": {...},
              ...
            }
        """
        sep = "|"
        stats: Dict[str, Dict[str, Any]] = {}
        for r in self._records:
            for op in r.operations:
                kind = op.get("kind", "unknown")
                smell = op.get("smell_type") or "unknown"
                key = f"{smell}{sep}{kind}"
                by_key = stats.setdefault(
                    key,
                    {
                        "total": 0,
                        "success": 0,
                        "fail": 0,
                        "verify_success": 0,
                        "verify_fail": 0,
                        "not_applied": 0,
                    },
                )
                by_key["total"] += 1
                outcome = _resolve_learning_outcome(op, r.verify_success)
                if outcome == "verify_success":
                    by_key["verify_success"] += 1
                    if _is_strong_refactor_code_smell_success(op):
                        by_key["success"] += 1
                elif outcome == "verify_fail":
                    by_key["verify_fail"] += 1
                    by_key["fail"] += 1
                else:
                    by_key["not_applied"] += 1
        return stats


def _is_strong_refactor_code_smell_success(op: Dict[str, Any]) -> bool:
    """Do not treat TODO-marker smell ops as strong success."""
    if (op.get("kind") or "") != "refactor_code_smell":
        return True
    diff = str(op.get("diff") or "")
    if "# TODO (eurika): refactor " in diff:
        return False
    return True

