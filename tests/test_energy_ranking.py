"""Tests for eurika.reasoning.planner.energy_ranking (ROADMAP §5.7)."""

from __future__ import annotations

from types import SimpleNamespace

from eurika.analysis.graph import ProjectGraph
from eurika.reasoning.planner.energy_ranking import (
    _estimated_delta,
    _risk_for_kind,
    _score_for_op,
    rank_operations_by_energy,
)


def test_estimated_delta_known_pair() -> None:
    assert _estimated_delta("god_module", "split_module") == 0.15
    assert _estimated_delta("cyclic_dependency", "remove_cyclic_import") == 0.20


def test_estimated_delta_unknown_pair() -> None:
    assert _estimated_delta("unknown", "unknown") == 0.05


def test_risk_for_kind() -> None:
    assert _risk_for_kind("remove_unused_import") == 0.05
    assert _risk_for_kind("extract_class") == 0.40
    assert _risk_for_kind("unknown") == 0.20


def test_score_for_op() -> None:
    # remove_cyclic_import: delta 0.2, risk 0.2 -> score 0
    # split_module god: delta 0.15, risk 0.3 -> score -0.15
    # remove_unused_import: delta 0.05 (default), risk 0.05 -> score 0
    s1 = _score_for_op("cyclic_dependency", "remove_cyclic_import")
    s2 = _score_for_op("god_module", "split_module")
    assert s1 > s2


def test_rank_operations_by_energy() -> None:
    graph = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    smells = []

    op_low = SimpleNamespace(smell_type="god_module", kind="split_module")
    op_high = SimpleNamespace(smell_type="cyclic_dependency", kind="remove_cyclic_import")
    ops = [op_low, op_high]

    ranked = rank_operations_by_energy(ops, graph, smells)
    assert len(ranked) == 2
    # remove_cyclic_import should rank higher (better score)
    assert ranked[0].kind == "remove_cyclic_import"


def test_rank_operations_empty() -> None:
    graph = ProjectGraph(["a.py"], {})
    ranked = rank_operations_by_energy([], graph, [])
    assert ranked == []


def test_rank_operations_uses_weights_snapshot_rv8() -> None:
    """RV8: when weights_snapshot provided, use it instead of live load_weights."""
    graph = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    smells = []
    op_a = SimpleNamespace(smell_type="god_module", kind="split_module")
    op_b = SimpleNamespace(smell_type="cyclic_dependency", kind="remove_cyclic_import")
    # Custom snapshot: swap deltas so op_a gets higher score
    snap = {
        ("god_module", "split_module"): 0.25,
        ("cyclic_dependency", "remove_cyclic_import"): 0.10,
    }
    ranked = rank_operations_by_energy([op_a, op_b], graph, smells, weights_snapshot=snap)
    assert len(ranked) == 2
    # With snapshot, god_module|split_module (0.25) beats cyclic|remove_cyclic (0.10)
    assert ranked[0].kind == "split_module"
