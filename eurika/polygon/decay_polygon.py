"""
Полигон для калибровки decay (Review III шаги 1–4).

Контролируемые провалы и успехи для проверки:
- падение effective_priority при провалах
- archive после N провалов
- восстановление после успеха (Step 3)
- forgetting (Step 4) — decay failure_penalty со временем
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from eurika.reasoning.priority_decay import apply_decay


def inject_failures(
    project_root: Path,
    target_file: str,
    kind: str,
    count: int,
    *,
    failure_reason: str = "verify_failed",
) -> None:
    """Добавить count провалов в failure_log для (target_file, kind)."""
    from eurika.storage.failure_log import append_failures

    for i in range(count):
        append_failures(project_root, [(target_file, kind, failure_reason)])
        if i < count - 1:
            time.sleep(0.001)


def run_decay_observation(
    project_root: Path,
    scores: Dict[str, float],
    reasons: Dict[str, list],
    node_to_kind: Callable[[str], str],
) -> Dict[str, float]:
    """Применить decay и вернуть scores после (in-place модифицирует копию)."""
    import copy

    s = copy.deepcopy(scores)
    apply_decay(s, reasons, node_to_kind, project_root)
    return s


def inject_success(
    project_root: Path,
    target_file: str,
    kind: str,
    count: int = 1,
) -> None:
    """Добавить count успехов через record_outcome (Step 3 recovery)."""
    from eurika.storage import record_outcome

    for _ in range(count):
        record_outcome(
            Path(project_root),
            modules=[target_file],
            operations=[{"target_file": target_file, "kind": kind}],
            risks=[],
            verify_success=True,
        )


def scenario_controlled_failures(
    project_root: Path,
    targets: List[Tuple[str, str, int]],
) -> None:
    """
    Создать контролируемый сценарий: список (target_file, kind, failure_count).

    Пример: [("a.py", "split_module", 2), ("b.py", "extract_class", 5)]
    """
    for tf, kind, n in targets:
        if n > 0:
            inject_failures(project_root, tf, kind, n)


__all__ = ["inject_failures", "inject_success", "run_decay_observation", "scenario_controlled_failures"]
