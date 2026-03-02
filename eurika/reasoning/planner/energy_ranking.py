"""
Energy-based ranking for patch operations (ROADMAP §5.7, review 2026 II).

Planner ранжирует по Score = estimated_delta - risk.
Heuristic estimated_delta until full SimulationEngine returns ArchitectureSnapshot.
WeightStore (§5.7 этап 7) — адаптивные веса per (smell_type, kind).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from eurika.analysis.energy_model import EnergyModel
from eurika.analysis.metric_vector import compute_metric_vector

# (smell_type, action_kind) -> estimated ΔEnergy (positive = improvement) — defaults
ESTIMATED_DELTA: dict[tuple[str, str], float] = {
    ("god_module", "split_module"): 0.15,
    ("god_module", "refactor_module"): 0.10,
    ("bottleneck", "introduce_facade"): 0.12,
    ("hub", "split_module"): 0.14,
    ("hub", "refactor_module"): 0.10,
    ("cyclic_dependency", "refactor_dependencies"): 0.18,
    ("cyclic_dependency", "remove_cyclic_import"): 0.20,
    ("long_function", "extract_nested_function"): 0.08,
    ("long_function", "extract_block_to_helper"): 0.07,
    ("long_function", "refactor_code_smell"): 0.05,
    ("deep_nesting", "extract_block_to_helper"): 0.09,
    ("deep_nesting", "refactor_code_smell"): 0.05,
}

# action_kind -> risk (0..1). Default 0.2 for unknown.
RISK_BY_KIND: dict[str, float] = {
    "split_module": 0.30,
    "extract_class": 0.40,
    "introduce_facade": 0.25,
    "remove_cyclic_import": 0.20,
    "refactor_module": 0.25,
    "refactor_dependencies": 0.25,
    "remove_unused_import": 0.05,
    "extract_nested_function": 0.15,
    "extract_block_to_helper": 0.15,
    "refactor_code_smell": 0.20,
}


def _estimated_delta(
    smell_type: str,
    action_kind: str,
    project_root: Optional[Path] = None,
) -> float:
    if project_root is not None:
        from eurika.analysis.weight_store import get_estimated_delta as _get

        return _get(project_root, smell_type or "", action_kind or "")
    key = (smell_type or "", action_kind or "")
    return ESTIMATED_DELTA.get(key, 0.05)


def _risk_for_kind(kind: str) -> float:
    return RISK_BY_KIND.get(kind, 0.20)


def _score_for_op(
    smell_type: Optional[str],
    kind: str,
    project_root: Optional[Path] = None,
) -> float:
    """Score = estimated_delta - risk. Higher = better candidate."""
    delta = _estimated_delta(smell_type or "", kind, project_root)
    risk = _risk_for_kind(kind)
    return delta - risk


def rank_operations_by_energy(
    operations: List[Any],
    graph: Any,
    smells: List[Any],
    *,
    project_root: Optional[Path] = None,
    _energy_model: Optional[EnergyModel] = None,  # for future full simulation
) -> List[Any]:
    """
    Sort operations by Score = estimated_delta - risk (ROADMAP §5.7).

    Uses heuristic estimated_delta per (smell_type, kind) until full
    SimulationEngine returns ArchitectureSnapshot.
    """
    if not operations:
        return operations
    # Validate baseline (for future full simulation: delta = E_after - E_before)
    compute_metric_vector(graph, smells)

    def key(op: Any) -> float:
        st = getattr(op, "smell_type", None)
        k = getattr(op, "kind", "")
        return -_score_for_op(st, k, project_root)  # negate: sort ascending, so best = most negative key

    return sorted(operations, key=key)
