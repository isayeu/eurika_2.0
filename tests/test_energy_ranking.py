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


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops targeting high-instability modules get penalized (rank lower)."""
    # a.py imports b.py: a has I=1 (unstable), b has I=0 (stable)
    graph = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": []})
    smells = []
    op_unstable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="a.py"
    )
    op_stable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="b.py"
    )
    ranked = rank_operations_by_energy([op_unstable, op_stable], graph, smells)
    assert len(ranked) == 2
    # Stable target (b.py) should rank higher
    assert ranked[0].target_file == "b.py"


def test_rank_stability_penalty_rv9() -> None:
    """RV9: ops targeting unstable modules (high I) get lower rank."""
    # a.py imports b.py: a has fi=0,fo=1 (unstable I=1); b has fi=1,fo=0 (stable I=0)
    graph = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    smells = []
    op_unstable = SimpleNamespace(
        smell_type="god_module",
        kind="split_module",
        target_file="a.py",
    )
    op_stable = SimpleNamespace(
        smell_type="god_module",
        kind="split_module",
        target_file="b.py",
    )
    ranked = rank_operations_by_energy([op_unstable, op_stable], graph, smells)
    assert len(ranked) == 2
    # Stable target (b.py) should rank first due to lower stability_penalty
    assert ranked[0].target_file == "b.py"


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops targeting high-instability modules get penalty, rank lower."""
    # stable.py: fi=2, fo=0 -> I=0; unstable.py: fi=0, fo=2 -> I=1
    graph = ProjectGraph(
        ["stable.py", "unstable.py", "a.py", "b.py"],
        {"a.py": ["stable.py"], "b.py": ["stable.py"], "unstable.py": ["a.py", "b.py"]},
    )
    smells = []
    op_stable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="stable.py"
    )
    op_unstable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="unstable.py"
    )
    ranked = rank_operations_by_energy([op_stable, op_unstable], graph, smells)
    assert len(ranked) == 2
    # stable.py (I=0) should rank higher than unstable.py (I=1) due to stability_penalty
    assert ranked[0].target_file == "stable.py"


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops targeting high-instability modules get penalty, ranked lower."""
    # stable.py: fi=2, fo=0 -> I=0; unstable.py: fi=0, fo=2 -> I=1
    graph = ProjectGraph(
        ["stable.py", "unstable.py", "a.py", "b.py"],
        {"a.py": ["stable.py"], "b.py": ["stable.py"], "unstable.py": ["a.py", "b.py"]},
    )
    smells = []
    op_stable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="stable.py"
    )
    op_unstable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="unstable.py"
    )
    ops = [op_unstable, op_stable]
    ranked = rank_operations_by_energy(ops, graph, smells)
    assert len(ranked) == 2
    # Same base score; stable target gets lower penalty -> ranks first
    assert ranked[0].target_file == "stable.py"


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops targeting high-instability modules (Martin's I) rank lower."""
    # stable: b.py has fi=2, fo=0 -> I=0. unstable: a.py has fi=0, fo=2 -> I=1
    graph = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py", "c.py"], "b.py": [], "c.py": []})
    smells = []
    op_stable = SimpleNamespace(smell_type="god_module", kind="split_module", target_file="b.py")
    op_unstable = SimpleNamespace(smell_type="god_module", kind="split_module", target_file="a.py")
    ranked = rank_operations_by_energy([op_unstable, op_stable], graph, smells)
    assert len(ranked) == 2
    # Same base score; op targeting stable b.py should rank higher
    assert ranked[0].target_file == "b.py"


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops on high-instability (high fan_out) targets get stability_penalty."""
    # center imports a,b,c -> center has high I; a,b,c are stable (I=0)
    graph = ProjectGraph(
        ["center.py", "a.py", "b.py", "c.py"],
        {"center.py": ["a.py", "b.py", "c.py"], "a.py": [], "b.py": [], "c.py": []},
    )
    smells = []
    op_unstable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="center.py"
    )
    op_stable = SimpleNamespace(
        smell_type="god_module", kind="split_module", target_file="a.py"
    )
    ranked = rank_operations_by_energy([op_unstable, op_stable], graph, smells)
    assert len(ranked) == 2
    # Stable target (a.py) should rank higher
    assert ranked[0].target_file == "a.py"


def test_rank_operations_stability_penalty_rv9() -> None:
    """RV9: ops on high-instability modules (Martin's I) get penalty, rank lower."""
    # hub: a.py imports b,c,d → high fan-out, I=fo/(fi+fo) high for a.py
    graph = ProjectGraph(
        ["a.py", "b.py", "c.py", "d.py"],
        {"a.py": ["b.py", "c.py", "d.py"], "b.py": [], "c.py": [], "d.py": []},
    )
    smells = []
    op_stable = SimpleNamespace(
        smell_type="bottleneck", kind="introduce_facade",
        target_file="b.py",  # b has fi=1, fo=0 → I=0 (stable)
    )
    op_unstable = SimpleNamespace(
        smell_type="hub", kind="split_module",
        target_file="a.py",  # a has fi=0, fo=3 → I=1 (unstable)
    )
    # Same base score would rank intro_facade slightly lower (risk 0.25 vs split 0.3)
    # But a.py gets stability_penalty → op_unstable ranks lower
    ranked = rank_operations_by_energy([op_stable, op_unstable], graph, smells)
    assert len(ranked) == 2
    # Stable target (b.py) should rank before unstable (a.py)
    assert ranked[0].target_file == "b.py"
