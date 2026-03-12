"""
Event as primary entity — Learning and Feedback as views over EventStore (ROADMAP 3.2.2).

learning/feedback.append() writes to EventStore with type "learn" / "feedback".
learning.all(), feedback.all() and aggregate_* derive from events.by_type(...).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .event_engine import EventStore


from eurika.storage.learning_store import LearningRecord
from eurika.storage.feedback_store import FeedbackRecord


def _learning_record_from_event(e: Any) -> "LearningRecord":
    return LearningRecord(
        timestamp=e.timestamp,
        project_root=e.input.get("project_root", ""),
        modules=list(e.input.get("modules", [])),
        operations=list(e.input.get("operations", [])),
        risks=list(e.input.get("risks", [])),
        verify_success=e.result,
    )


def _feedback_record_from_event(e: Any) -> "FeedbackRecord":
    outcome = e.output.get("outcome") or (e.result if isinstance(e.result, str) else "")
    return FeedbackRecord(
        timestamp=e.timestamp,
        project_root=e.input.get("project_root", ""),
        action=e.input.get("action", ""),
        outcome=outcome or "",
        target=e.input.get("target"),
        comment=e.input.get("comment"),
    )


def _is_strong_refactor_code_smell_success(op: Dict[str, Any]) -> bool:
    """
    Return True only for non-marker refactor_code_smell operations.

    Marker-only TODO operations should not inflate success statistics.
    """
    if (op.get("kind") or "") != "refactor_code_smell":
        return True
    diff = str(op.get("diff") or "")
    if "# TODO (eurika): refactor " in diff:
        return False
    return True


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


def _migrate_legacy_to_events(
    events: "EventStore",
    storage_path: Path,
    event_type: str,
    record_to_event_input: Any,
) -> None:
    """One-time: load legacy JSON, append each record as event, remove file."""
    if not storage_path.exists():
        return
    try:
        raw = json.loads(storage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    key = "learning" if event_type == "learn" else "feedback"
    items = raw.get(key, [])
    for item in items:
        inp, out, res = record_to_event_input(item)
        events.append_event(type=event_type, input=inp, output=out, result=res)
    try:
        storage_path.unlink()
    except OSError:
        pass


class LearningView:
    """View over EventStore: learning records as events with type 'learn'."""

    def __init__(self, events: "EventStore", project_root: Path) -> None:
        self._events = events
        self._project_root = Path(project_root)
        self._migrated = False

    def _ensure_migrated(self) -> None:
        if self._migrated:
            return
        from .paths import storage_path
        path = storage_path(self._project_root, "learning")
        if path.exists() and not self._events.by_type("learn"):
            def to_input(rec: Dict) -> tuple:
                return (
                    {
                        "project_root": rec.get("project_root", ""),
                        "modules": list(rec.get("modules", [])),
                        "operations": list(rec.get("operations", [])),
                        "risks": list(rec.get("risks", [])),
                    },
                    {},
                    rec.get("verify_success"),
                )
            _migrate_legacy_to_events(self._events, path, "learn", lambda r: to_input(r))
        self._migrated = True

    def append(
        self,
        project_root: Path,
        modules: List[str],
        operations: List[Dict[str, Any]],
        risks: List[str],
        verify_success: Optional[bool],
        *,
        delta_energy: Optional[float] = None,
        failure_reason: Optional[str] = None,
        goal_id: Optional[str] = None,
        plan_hash: Optional[str] = None,
        confidence: Optional[float] = None,
        project_size: Optional[int] = None,
        module_size: Optional[int] = None,
        context: Optional[str] = None,
    ) -> None:
        """S5: project_size, module_size, context — avoid 'свалка без контекста'."""
        self._ensure_migrated()
        output: Dict[str, Any] = {}
        if delta_energy is not None:
            output["delta_energy"] = delta_energy
        if failure_reason is not None:
            output["failure_reason"] = failure_reason
        if goal_id is not None:
            output["goal_id"] = goal_id
        if plan_hash is not None:
            output["plan_hash"] = plan_hash
        if confidence is not None:
            output["confidence"] = confidence
        inp: Dict[str, Any] = {
            "project_root": str(project_root),
            "modules": list(modules),
            "operations": list(operations),
            "risks": list(risks),
        }
        if project_size is not None:
            inp["project_size"] = project_size
        if module_size is not None:
            inp["module_size"] = module_size
        if context is not None:
            inp["context"] = context
        self._events.append_event(
            type="learn",
            input=inp,
            output=output,
            result=verify_success,
        )

    def all(self) -> List["LearningRecord"]:
        self._ensure_migrated()
        return [_learning_record_from_event(e) for e in self._events.by_type("learn")]

    def aggregate_by_action_kind(self) -> Dict[str, Dict[str, Any]]:
        records = self.all()
        stats: Dict[str, Dict[str, Any]] = {}
        for r in records:
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
                        "last_ts": 0.0,
                    },
                )
                by_kind["total"] += 1
                by_kind["last_ts"] = max(by_kind.get("last_ts", 0.0), r.timestamp)
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
        records = self.all()
        sep = "|"
        stats: Dict[str, Dict[str, Any]] = {}
        for r in records:
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
                        "last_ts": 0.0,
                    },
                )
                by_key["total"] += 1
                by_key["last_ts"] = max(by_key.get("last_ts", 0.0), r.timestamp)
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

    def get_experience_with_delta_energy(self, limit: int = 50) -> List[tuple[List[Dict[str, Any]], float]]:
        """
        Return (operations, delta_energy) for recent learn events that have delta_energy.
        R9/P6: для adapt_weights W -= lr * delta_energy (delta = after - before; negative = improvement).
        """
        self._ensure_migrated()
        events = self._events.by_type("learn")[-limit:]
        out: List[tuple[List[Dict[str, Any]], float]] = []
        for e in events:
            output = getattr(e, "output", None) or {}
            delta = output.get("delta_energy")
            if delta is not None and isinstance(delta, (int, float)):
                inp = getattr(e, "input", None) or {}
                ops = list(inp.get("operations", []))
                if ops:
                    out.append((ops, float(delta)))
        return out


class FeedbackView:
    """View over EventStore: feedback records as events with type 'feedback'."""

    def __init__(self, events: "EventStore", project_root: Path) -> None:
        self._events = events
        self._project_root = Path(project_root)
        self._migrated = False

    def _ensure_migrated(self) -> None:
        if self._migrated:
            return
        from .paths import storage_path
        path = storage_path(self._project_root, "feedback")
        if path.exists() and not self._events.by_type("feedback"):
            def to_input(rec: Dict) -> tuple:
                return (
                    {
                        "project_root": rec.get("project_root", ""),
                        "action": rec.get("action", ""),
                        "target": rec.get("target"),
                        "comment": rec.get("comment"),
                    },
                    {"outcome": rec.get("outcome", "")},
                    rec.get("outcome"),
                )
            _migrate_legacy_to_events(self._events, path, "feedback", lambda r: to_input(r))
        self._migrated = True

    def append(
        self,
        project_root: Path,
        action: str,
        outcome: str,
        target: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> None:
        self._ensure_migrated()
        self._events.append_event(
            type="feedback",
            input={
                "project_root": str(project_root),
                "action": action,
                "target": target,
                "comment": comment,
            },
            output={"outcome": outcome},
            result=outcome,
        )

    def all(self) -> List["FeedbackRecord"]:
        self._ensure_migrated()
        return [_feedback_record_from_event(e) for e in self._events.by_type("feedback")]

    def aggregate_by_action(self) -> Dict[str, Dict[str, int]]:
        records = self.all()
        stats: Dict[str, Dict[str, int]] = {}
        for r in records:
            by_action = stats.setdefault(r.action, {})
            by_action[r.outcome] = by_action.get(r.outcome, 0) + 1
        return stats
