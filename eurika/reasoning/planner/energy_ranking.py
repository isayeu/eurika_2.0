"""
Energy-based ranking for patch operations (ROADMAP §5.7, review 2026 II).

Planner ранжирует по Score = estimated_delta - risk - λ*stability_penalty (RV9).
Heuristic estimated_delta until full SimulationEngine returns ArchitectureSnapshot.
WeightStore (§5.7 этап 7) — адаптивные веса per (smell_type, kind).

RV9: stability_penalty = Martin's I = fan_out/(fan_in+fan_out) for target module.
High instability → penalty to avoid collateral damage from refactoring fragile modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

from eurika.analysis.energy_model import EnergyModel
from eurika.analysis.metric_vector import compute_metric_vector

# RV9: weight for stability_penalty (multi-objective ranking)
_STABILITY_LAMBDA = float(os.environ.get("EURIKA_STABILITY_PENALTY_LAMBDA", "0.15"))

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
    weights_snapshot: Optional[dict] = None,
) -> float:
    """Use weights_snapshot when provided (RV8: freeze during cycle)."""
    if weights_snapshot is not None:
        key = (smell_type or "", action_kind or "")
        return weights_snapshot.get(key, ESTIMATED_DELTA.get(key, 0.05))
    if project_root is not None:
        from eurika.analysis.weight_store import get_estimated_delta as _get

        return _get(project_root, smell_type or "", action_kind or "")
    key = (smell_type or "", action_kind or "")
    return ESTIMATED_DELTA.get(key, 0.05)


def _risk_for_kind(kind: str) -> float:
    return RISK_BY_KIND.get(kind, 0.20)


def _get_target_from_op(op: Any) -> Optional[str]:
    """Extract target file path from op for stability_penalty (RV9)."""
    t = getattr(op, "target_file", None) or getattr(op, "target", None)
    if t:
        return Path(t).as_posix()
    if isinstance(op, dict):
        t = op.get("target_file") or op.get("target")
        return Path(t).as_posix() if t else None
    return None


def _stability_penalty_for_target(target: Optional[str], graph: Any) -> float:
    """
    RV9: Martin's I = fan_out / (fan_in + fan_out) for target module.

    High instability = fragile module → penalty when refactoring it.
    Returns 0 if target missing or not in graph.
    """
    if not target or not hasattr(graph, "fan_in_out"):
        return 0.0
    fan = graph.fan_in_out()
    if target not in fan:
        return 0.0
    fi, fo = fan.get(target, (0, 0))
    if fi + fo == 0:
        return 0.0
    return fo / (fi + fo)


def estimated_delta_for_op(op: Any, project_root: Optional[Path] = None) -> float:
    """|ΔE| for op (BOUNDED_EVOLUTION §7 energy cap). Uses heuristic until full simulation."""
    st = getattr(op, "smell_type", None) or (op.get("smell_type") if isinstance(op, dict) else None)
    k = getattr(op, "kind", None) or (op.get("kind") if isinstance(op, dict) else "")
    return abs(_estimated_delta(str(st or ""), str(k or ""), project_root))


def _score_for_op(
    smell_type: Optional[str],
    kind: str,
    project_root: Optional[Path] = None,
    weights_snapshot: Optional[dict] = None,
) -> float:
    """Score = estimated_delta - risk. Higher = better candidate."""
    delta = _estimated_delta(smell_type or "", kind, project_root, weights_snapshot=weights_snapshot)
    risk = _risk_for_kind(kind)
    return delta - risk


def rank_operations_by_energy(
    operations: List[Any],
    graph: Any,
    smells: List[Any],
    *,
    project_root: Optional[Path] = None,
    weights_snapshot: Optional[dict] = None,
    _energy_model: Optional[EnergyModel] = None,  # for future full simulation
) -> List[Any]:
    """
    Sort operations by Score = estimated_delta - risk (ROADMAP §5.7).

    When weights_snapshot is provided (RV8), use it instead of live load_weights
    so planner is deterministic during the cycle.
    """
    if not operations:
        return operations
    # Validate baseline (for future full simulation: delta = E_after - E_before)
    compute_metric_vector(graph, smells)

    def key(op: Any) -> float:
        st = getattr(op, "smell_type", None)
        k = getattr(op, "kind", "")
        base = _score_for_op(st, k, project_root, weights_snapshot=weights_snapshot)
        target = _get_target_from_op(op)
        penalty = _stability_penalty_for_target(target, graph)
        return -(base - _STABILITY_LAMBDA * penalty)

    return sorted(operations, key=key)
