"""Learning API routes: operational metrics, chat state, learning insights (R1 public API facade)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def get_operational_metrics(project_root: Path, window: int = 10) -> Dict[str, Any]:
    """Aggregate apply-rate, rollback-rate, median verify time from patch events (ROADMAP 2.7.8)."""
    from eurika.storage import aggregate_operational_metrics

    root = Path(project_root).resolve()
    metrics = aggregate_operational_metrics(root, window=window)
    return metrics if metrics else {"error": "no patch events", "hint": "run eurika fix . at least once"}


def get_chat_dialog_state(project_root: Path) -> Dict[str, Any]:
    """Read lightweight chat dialog state for UI transparency."""
    root = Path(project_root).resolve()
    path = root / ".eurika" / "chat_history" / "dialog_state.json"
    if not path.exists():
        return {"active_goal": {}, "pending_clarification": {}, "pending_plan": {}, "last_execution": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"active_goal": {}, "pending_clarification": {}, "pending_plan": {}, "last_execution": {}}
        active = raw.get("active_goal")
        pending = raw.get("pending_clarification")
        pending_plan = raw.get("pending_plan")
        last_execution = raw.get("last_execution")
        return {
            "active_goal": active if isinstance(active, dict) else {},
            "pending_clarification": pending if isinstance(pending, dict) else {},
            "pending_plan": pending_plan if isinstance(pending_plan, dict) else {},
            "last_execution": last_execution if isinstance(last_execution, dict) else {},
        }
    except (json.JSONDecodeError, OSError):
        return {"active_goal": {}, "pending_clarification": {}, "pending_plan": {}, "last_execution": {}}


def _chat_intent_outcome_from_text(text: str) -> str | None:
    """Resolve chat intent outcome from assistant text: success | fail | None."""
    content = str(text or "").strip()
    if not content:
        return None
    low = content.lower()
    if "[error]" in low or "[request failed]" in low or "не удалось" in low:
        return "fail"
    success_markers = (
        "[сохранено в ",
        "создан пустой файл ",
        "удалён файл ",
        "запустил `eurika fix .`",
        "запустил eurika fix",
    )
    if any((marker in low for marker in success_markers)):
        return "success"
    return None


def _chat_learning_recommendations(project_root: Path, top_n: int) -> Dict[str, List[Dict[str, Any]]]:
    """Derive conservative policy/whitelist hints from chat intent outcomes."""
    from .chat_intent import detect_intent

    root = Path(project_root).resolve()
    path = root / ".eurika" / "chat_history" / "chat.jsonl"
    if not path.exists():
        return {"chat_whitelist_hints": [], "chat_policy_review_hints": []}
    by_key: Dict[str, Dict[str, Any]] = {}
    last_user: str | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = str(rec.get("role") or "").strip().lower()
            content = str(rec.get("content") or "")
            if role == "user":
                last_user = content
                continue
            if role != "assistant" or last_user is None:
                continue
            intent, target = detect_intent(last_user)
            last_user = None
            if intent not in {"save", "create", "delete", "refactor"}:
                continue
            outcome = _chat_intent_outcome_from_text(content)
            if outcome is None:
                continue
            target_str = str(target or ".")
            key = f"{intent}|{target_str}"
            bucket = by_key.setdefault(
                key, {"intent": intent, "target": target_str, "total": 0, "success": 0, "fail": 0}
            )
            bucket["total"] += 1
            bucket[outcome] += 1
    except OSError:
        return {"chat_whitelist_hints": [], "chat_policy_review_hints": []}
    rows: list[Dict[str, Any]] = []
    for row in by_key.values():
        total = max(int(row.get("total", 0)), 1)
        row["success_rate"] = round(float(row.get("success", 0)) / total, 4)
        if row.get("intent") in {"save", "create", "delete"}:
            row["suggestion"] = "consider allowlist review for this chat intent target"
        else:
            row["suggestion"] = "consider safer canned flow for frequent refactor intent"
        rows.append(row)
    rows.sort(
        key=lambda item: (
            float(item.get("success_rate", 0.0)),
            int(item.get("success", 0)),
            -int(item.get("fail", 0)),
        ),
        reverse=True,
    )
    whitelist_hints = [
        r
        for r in rows
        if int(r.get("total", 0)) >= 2 and int(r.get("fail", 0)) == 0 and (float(r.get("success_rate", 0.0)) >= 0.7)
    ][:top_n]
    policy_review_hints = [
        r
        for r in rows
        if int(r.get("total", 0)) >= 2 and int(r.get("fail", 0)) >= 1 and (float(r.get("success_rate", 0.0)) < 0.4)
    ][:top_n]
    return {"chat_whitelist_hints": whitelist_hints, "chat_policy_review_hints": policy_review_hints}


def get_learning_insights(
    project_root: Path, top_n: int = 5, *, polygon_only: bool = False
) -> Dict[str, Any]:
    """Learning insights for UI: what worked and policy/whitelist hints.
    polygon_only: filter to eurika/polygon/ targets only (drill view).
    """
    from eurika.storage import ProjectMemory

    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    by_action_kind = memory.learning.aggregate_by_action_kind()
    by_smell_action = memory.learning.aggregate_by_smell_action()
    records = memory.learning.all()
    by_target: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        for op in rec.operations:
            target = str(op.get("target_file") or "").strip()
            if not target:
                continue
            if polygon_only and not target.startswith("eurika/polygon/"):
                continue
            kind = str(op.get("kind") or "unknown")
            smell = str(op.get("smell_type") or "unknown")
            key = f"{smell}|{kind}|{target}"
            bucket = by_target.setdefault(
                key,
                {
                    "smell_type": smell,
                    "action_kind": kind,
                    "target_file": target,
                    "total": 0,
                    "verify_success": 0,
                    "verify_fail": 0,
                    "not_applied": 0,
                },
            )
            bucket["total"] += 1
            outcome = str(op.get("execution_outcome") or "")
            if outcome == "verify_success" or (not outcome and rec.verify_success is True):
                bucket["verify_success"] += 1
            elif outcome == "verify_fail" or (not outcome and rec.verify_success is False):
                bucket["verify_fail"] += 1
            else:
                bucket["not_applied"] += 1
    for stats in by_target.values():
        total = max(int(stats.get("total", 0)), 1)
        stats["verify_success_rate"] = round(float(stats.get("verify_success", 0)) / total, 4)
    ordered_targets = sorted(
        by_target.values(),
        key=lambda item: (
            float(item.get("verify_success_rate", 0.0)),
            int(item.get("verify_success", 0)),
            -int(item.get("verify_fail", 0)),
        ),
        reverse=True,
    )
    whitelist_candidates = [
        item
        for item in ordered_targets
        if int(item.get("total", 0)) >= 2 and float(item.get("verify_success_rate", 0.0)) >= 0.6
    ][:top_n]
    deny_candidates = [
        item
        for item in ordered_targets
        if int(item.get("total", 0)) >= 3 and float(item.get("verify_success_rate", 0.0)) < 0.25
    ][:top_n]
    chat_recs = _chat_learning_recommendations(root, top_n=top_n)
    if polygon_only:
        by_smell_action = {}
        for item in ordered_targets:
            k = f"{item.get('smell_type', '?')}|{item.get('action_kind', '?')}"
            if k not in by_smell_action:
                by_smell_action[k] = {"total": 0, "verify_success": 0, "verify_fail": 0}
            by_smell_action[k]["total"] += int(item.get("total", 0))
            by_smell_action[k]["verify_success"] += int(item.get("verify_success", 0))
            by_smell_action[k]["verify_fail"] += int(item.get("verify_fail", 0))
    else:
        by_smell_action = memory.learning.aggregate_by_smell_action()
    prioritized_smell_actions: list[Dict[str, Any]] = []
    for k, v in (by_smell_action or {}).items():
        total = int(v.get("total") or 0)
        if total < 2:
            continue
        rate = float(v.get("verify_success", 0) or 0) / total
        if rate >= 0.3:
            parts = k.split("|", 2)
            prioritized_smell_actions.append(
                {
                    "smell_type": parts[0] if len(parts) > 0 else "?",
                    "action_kind": parts[1] if len(parts) > 1 else "?",
                    "verify_success_rate": round(rate, 4),
                    "total": total,
                }
            )
    prioritized_smell_actions.sort(
        key=lambda x: (float(x.get("verify_success_rate", 0)), int(x.get("total", 0))),
        reverse=True,
    )
    return {
        "by_action_kind": by_action_kind,
        "by_smell_action": by_smell_action,
        "prioritized_smell_actions": prioritized_smell_actions[:10],
        "by_target": ordered_targets[: max(top_n, 1) * 2],
        "what_worked": ordered_targets[:top_n],
        "recommendations": {
            "whitelist_candidates": whitelist_candidates,
            "policy_deny_candidates": deny_candidates,
            "chat_whitelist_hints": chat_recs.get("chat_whitelist_hints", []),
            "chat_policy_review_hints": chat_recs.get("chat_policy_review_hints", []),
        },
    }
