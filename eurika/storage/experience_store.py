"""
ExperienceStore — фасад для записи outcome без изменения весов (ROADMAP §5.7 этап 6).

Тонкий слой над memory.learning и global_memory. Никакой архитектурной логики.
record_outcome — только запись, без обновления EnergyModel весов.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


def _plan_hash_from_operations(operations: List[Dict[str, Any]]) -> str:
    """Deterministic hash of plan (target_file, kind) for strategy-level deprioritization."""
    keys = sorted(
        (str(o.get("target_file") or ""), str(o.get("kind") or ""))
        for o in operations
        if o.get("target_file") or o.get("kind")
    )
    raw = "|".join(f"{tf}:{k}" for tf, k in keys)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def plan_hash_from_ops(ops: List[Any]) -> str:
    """Plan hash from operations (dicts or objects with target_file, kind). For planner."""
    dict_ops = []
    for o in ops:
        if hasattr(o, "target_file"):
            dict_ops.append({"target_file": getattr(o, "target_file"), "kind": getattr(o, "kind", "")})
        elif isinstance(o, dict):
            dict_ops.append(o)
    return _plan_hash_from_operations(dict_ops)


def _goal_id_from_operations(operations: List[Dict[str, Any]]) -> str:
    """Primary goal: first op's target|kind for causal analysis."""
    for op in operations:
        tf = str(op.get("target_file") or "")
        k = str(op.get("kind") or "")
        if tf or k:
            return f"{tf}|{k}"
    return "unknown"


def record_outcome(
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
    """
    Записать outcome patch-apply + verify в локальный и глобальный store.

    Не меняет веса EnergyModel. delta_energy — для этапа 7 (weight adaptation).
    failure_reason — при verify_success=False для самокоррекции (Review III).
    goal_id, plan_hash, confidence — привязка к стратегии (ARCHITECTURE_MEMORY_REVIEW §2).
    S5: project_size, module_size, context — контекст для outcome (avoid свалка без контекста).
    """
    if not operations:
        return
    from .global_memory import append_learn_to_global
    from .memory import ProjectMemory

    if goal_id is None:
        goal_id = _goal_id_from_operations(operations)
    if plan_hash is None and verify_success is False:
        plan_hash = _plan_hash_from_operations(operations)

    memory = ProjectMemory(project_root)
    memory.learning.append(
        project_root=project_root,
        modules=list(modules),
        operations=operations,
        risks=list(risks),
        verify_success=verify_success,
        delta_energy=delta_energy,
        failure_reason=failure_reason,
        goal_id=goal_id,
        plan_hash=plan_hash,
        confidence=confidence,
        project_size=project_size,
        module_size=module_size,
        context=context,
    )
    append_learn_to_global(
        project_root,
        list(modules),
        operations,
        list(risks),
        verify_success,
    )


def get_recent_failures(
    project_root: Path,
    limit: int = 5,
) -> List[tuple[str, str, str]]:
    """
    Return (target_file, kind, failure_reason) — bounded view over EventLog (Review III).

    Single source of truth: learn events with result=False.
    """
    enriched = get_recent_failures_enriched(project_root, limit=limit)
    return [(e["target_file"], e["kind"], e["failure_reason"]) for e in enriched]


def get_recent_failures_enriched(
    project_root: Path,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return enriched failures: target_file, kind, failure_reason, goal_id, plan_hash, confidence.

    For strategy-level deprioritization (ARCHITECTURE_MEMORY_REVIEW §2).
    """
    from .memory import ProjectMemory

    memory = ProjectMemory(project_root)
    events = memory.events.recent_events(limit=min(100, limit * 10), types=("learn",))
    out: list[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in events:
        if e.result is not False:
            continue
        o = e.output or {}
        fail = o.get("failure_reason", "verify_failed")
        goal_id = o.get("goal_id")
        plan_hash = o.get("plan_hash")
        confidence = o.get("confidence")
        for op in (e.input or {}).get("operations", []):
            tf = str(op.get("target_file") or "")
            k = str(op.get("kind") or "")
            if tf or k:
                key = (tf, k, fail)
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "target_file": tf,
                        "kind": k,
                        "failure_reason": fail,
                        "goal_id": goal_id,
                        "plan_hash": plan_hash,
                        "confidence": confidence,
                    })
        if len(out) >= limit:
            break
    return out[:limit]


def get_recent_failed_plan_hashes(project_root: Path, limit: int = 10) -> frozenset[str]:
    """Plan hashes that failed recently — for strategy deprioritization."""
    enriched = get_recent_failures_enriched(project_root, limit=limit)
    return frozenset(
        h for e in enriched
        for h in (e.get("plan_hash") or "",)
        if h
    )


def get_recent_failed_kind_plan_pairs(project_root: Path, limit: int = 15) -> frozenset[tuple[str, str]]:
    """(kind, plan_hash) pairs that failed — deprioritize by action_kind + plan_hash."""
    enriched = get_recent_failures_enriched(project_root, limit=limit)
    return frozenset(
        (e.get("kind") or "", e.get("plan_hash") or "")
        for e in enriched
        if (e.get("plan_hash") or "") and (e.get("kind") or "")
    )


def get_plan_hash_failure_counts(project_root: Path, limit: int = 20) -> dict[str, int]:
    """plan_hash -> count of failures. For frequency-based deprioritization."""
    from collections import Counter

    enriched = get_recent_failures_enriched(project_root, limit=limit)
    ph_list = [e.get("plan_hash") or "" for e in enriched if e.get("plan_hash")]
    return dict(Counter(ph_list))


def get_kind_plan_failure_counts(project_root: Path, limit: int = 20) -> dict[tuple[str, str], int]:
    """(kind, plan_hash) -> count of failures. From raw events (no dedup) for frequency."""
    from collections import Counter

    from .memory import ProjectMemory

    memory = ProjectMemory(project_root)
    events = memory.events.recent_events(limit=min(200, limit * 10), types=("learn",))
    pairs: list[tuple[str, str]] = []
    for e in events:
        if e.result is not False:
            continue
        ph = (e.output or {}).get("plan_hash") or ""
        if not ph:
            continue
        for op in (e.input or {}).get("operations", []):
            k = str(op.get("kind") or "")
            if k:
                pairs.append((k, ph))
    return dict(Counter(pairs))


def get_learn_events_with_delta_energy(
    project_root: Path,
    limit: int = 50,
) -> List[tuple[List[Dict[str, Any]], float]]:
    """
    Return (operations, delta_energy) for recent learn events that have delta_energy.
    R9/P6: для adapt_weights delta_energy-based update.
    """
    from .memory import ProjectMemory

    memory = ProjectMemory(project_root)
    return memory.learning.get_experience_with_delta_energy(limit=limit)


def get_statistics(
    project_root: Path,
    action_type: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Вернуть агрегированную статистику по smell|action (локально + глобально).

    action_type: если задан, фильтр по kind операции (например "refactor_module").
    """
    from .global_memory import get_merged_learning_stats

    stats = get_merged_learning_stats(project_root)
    if action_type:
        sep = "|"
        stats = {k: v for k, v in stats.items() if k.split(sep)[-1] == action_type}
    return stats


class ExperienceStore:
    """
    Фасад над learning append + get_merged_learning_stats.

    record_outcome / get_statistics — делегируют в существующий storage.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def record_outcome(
        self,
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
        record_outcome(
            self.project_root,
            modules,
            operations,
            risks,
            verify_success,
            delta_energy=delta_energy,
            failure_reason=failure_reason,
            goal_id=goal_id,
            plan_hash=plan_hash,
            confidence=confidence,
            project_size=project_size,
            module_size=module_size,
            context=context,
        )

    def get_statistics(
        self,
        action_type: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return get_statistics(self.project_root, action_type=action_type)
