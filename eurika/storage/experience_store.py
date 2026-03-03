"""
ExperienceStore — фасад для записи outcome без изменения весов (ROADMAP §5.7 этап 6).

Тонкий слой над memory.learning и global_memory. Никакой архитектурной логики.
record_outcome — только запись, без обновления EnergyModel весов.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def record_outcome(
    project_root: Path,
    modules: List[str],
    operations: List[Dict[str, Any]],
    risks: List[str],
    verify_success: Optional[bool],
    *,
    delta_energy: Optional[float] = None,
    failure_reason: Optional[str] = None,
) -> None:
    """
    Записать outcome patch-apply + verify в локальный и глобальный store.

    Не меняет веса EnergyModel. delta_energy — для этапа 7 (weight adaptation).
    failure_reason — при verify_success=False для самокоррекции (Review III).
    """
    if not operations:
        return
    from .memory import ProjectMemory
    from .global_memory import append_learn_to_global

    memory = ProjectMemory(project_root)
    memory.learning.append(
        project_root=project_root,
        modules=list(modules),
        operations=operations,
        risks=list(risks),
        verify_success=verify_success,
        delta_energy=delta_energy,
        failure_reason=failure_reason,
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
    Return (target_file, kind, failure_reason) from recent failed learn events (Review III самокоррекция).
    """
    from .memory import ProjectMemory

    memory = ProjectMemory(project_root)
    events = memory.events.recent_events(limit=limit, types=("learn",))
    out: List[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in events:
        if e.result is not False:
            continue
        fail = (e.output or {}).get("failure_reason") if hasattr(e, "output") else None
        if not fail:
            continue
        for op in (e.input or {}).get("operations", []):
            tf = str(op.get("target_file") or "")
            k = str(op.get("kind") or "")
            if tf or k:
                key = (tf, k, fail)
                if key not in seen:
                    seen.add(key)
                    out.append(key)
    return out[:20]


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
    ) -> None:
        record_outcome(
            self.project_root,
            modules,
            operations,
            risks,
            verify_success,
            delta_energy=delta_energy,
            failure_reason=failure_reason,
        )

    def get_statistics(
        self,
        action_type: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return get_statistics(self.project_root, action_type=action_type)
