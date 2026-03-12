"""
DeltaEvaluator — сравнение snapshot before/after (ROADMAP §5.7, review §3).

Чистая функция: только чтение и сравнение. Без записи, без мутации.
"""

from __future__ import annotations

from typing import Any, Callable


def compute_delta(
    old_snap: Any,
    new_snap: Any,
    metrics_from_graph: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare before/after snapshots and return verify_metrics dict.

    Used by apply_stage rescan to compute delta_score and decide rollback.
    """
    trends: dict[str, Any] = {}
    metrics_before = metrics_from_graph(old_snap.graph, old_snap.smells, trends)
    metrics_after = metrics_from_graph(new_snap.graph, new_snap.smells, trends)
    before_score = metrics_before.get("score", 0)
    after_score = metrics_after.get("score", 0)
    energy_used = "energy" in metrics_before and "energy" in metrics_after
    return {
        "success": after_score >= before_score,
        "before_score": before_score,
        "after_score": after_score,
        "energy_used": energy_used,
    }
