"""
Meta-Controller — переключение стратегий при деградации (ROADMAP v4.0, review.md §1815).

Отслеживает:
- средний verify_success rate
- количество регрессий подряд

При деградации: понижает learning_rate или пропускает weight adaptation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PolicyDecision:
    """Решение meta-controller по текущей политике адаптации."""

    skip_adaptation: bool
    learning_rate_scale: float  # 1.0 = норма, 0.5 = половинный LR


def evaluate_policy(project_root: Path) -> PolicyDecision:
    """
    Оценить политику по статистике и последним исходам.

    Деградация: overall success_rate < 0.35 или 3+ регрессий подряд.
    При деградации: skip_adaptation=True или learning_rate_scale=0.5.
    """
    from eurika.storage import get_statistics
    from eurika.storage.memory import ProjectMemory

    stats = get_statistics(project_root)
    memory = ProjectMemory(project_root)
    events = memory.events.recent_events(limit=12, types=("patch",))

    overall_rate = _overall_success_rate(stats)
    consecutive_fails = _consecutive_verify_fails(events)
    recent_rate = _recent_success_rate(events)

    degraded = False
    if overall_rate is not None and overall_rate < 0.35:
        degraded = True
    if consecutive_fails >= 3:
        degraded = True
    if recent_rate is not None and len(events) >= 5 and recent_rate < 0.3:
        degraded = True

    if degraded:
        return PolicyDecision(skip_adaptation=True, learning_rate_scale=0.0)
    if recent_rate is not None and recent_rate < 0.5 and len(events) >= 3:
        return PolicyDecision(skip_adaptation=False, learning_rate_scale=0.5)
    return PolicyDecision(skip_adaptation=False, learning_rate_scale=1.0)


def _overall_success_rate(stats: dict) -> float | None:
    """Средний success rate по всем smell|action."""
    if not stats:
        return None
    total_s = 0
    total_n = 0
    for rec in stats.values():
        t = int(rec.get("total", 0) or 0)
        s = int(rec.get("success", 0) or 0)
        if t >= 2:
            total_s += s
            total_n += t
    if total_n == 0:
        return None
    return total_s / total_n


def _consecutive_verify_fails(events: list) -> int:
    """Количество последних подряд неудачных verify (от конца)."""
    count = 0
    for e in reversed(events):
        ok = e.result if hasattr(e, "result") else (e.output or {}).get("verify_success")
        if ok is True:
            break
        if ok is False:
            count += 1
        else:
            break
    return count


def _recent_success_rate(events: list) -> float | None:
    """Success rate по последним patch-событиям."""
    if not events:
        return None
    success = 0
    for e in events:
        ok = e.result if hasattr(e, "result") else (e.output or {}).get("verify_success")
        if ok is True:
            success += 1
        elif ok is False:
            pass
    return success / len(events)
