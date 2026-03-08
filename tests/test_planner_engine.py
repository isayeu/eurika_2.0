"""Tests for PlannerEngine (ROADMAP §4.5 MVP: generate_candidates, run_patch_plan)."""

from pathlib import Path

from eurika.analysis.graph import ProjectGraph
from eurika.reasoning.planner.engine import (
    collect_facts,
    generate_candidates,
    run_patch_plan,
)
from eurika.smells.models import ArchSmell


def test_generate_candidates_returns_list(tmp_path: Path) -> None:
    """Unit: generate_candidates (CandidateGenerator) returns list of operations or empty."""
    facts = collect_facts(
        project_root=str(tmp_path),
        summary={"risks": []},
        smells=[],
        history_info={"trends": {}, "regressions": []},
        priorities=[],
    )
    ops = generate_candidates(facts)
    assert isinstance(ops, list)


def test_generate_candidates_with_smell_returns_operations(tmp_path: Path) -> None:
    """Unit: generate_candidates with god_module smell produces operations."""
    (tmp_path / ".eurika").mkdir(exist_ok=True)
    smell = ArchSmell(type="god_module", nodes=["big.py"], severity=5.0, description="")
    facts = collect_facts(
        project_root=str(tmp_path),
        summary={"risks": ["god_module"]},
        smells=[smell],
        history_info={"trends": {}, "regressions": []},
        priorities=[{"name": "big.py", "reasons": ["god_module"]}],
    )
    ops = generate_candidates(facts)
    assert isinstance(ops, list)
    # May be empty due to filters (e.g. no self_map), but must not crash
    for op in ops:
        assert hasattr(op, "kind") or isinstance(op, dict)
        if isinstance(op, dict):
            assert "kind" in op


def test_run_patch_plan_integration(tmp_path: Path) -> None:
    """Integration: run_patch_plan returns PatchPlan with operations (or empty)."""
    (tmp_path / ".eurika").mkdir(exist_ok=True)
    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": []})
    smells = [ArchSmell(type="god_module", nodes=["a.py"], severity=4.0, description="")]
    plan = run_patch_plan(
        project_root=str(tmp_path),
        summary={"risks": []},
        smells=smells,
        history_info={"trends": {}, "regressions": []},
        priorities=[{"name": "a.py", "reasons": ["god_module"]}],
        graph=g,
    )
    assert hasattr(plan, "operations")
    assert hasattr(plan, "project_root")
    assert plan.project_root == str(tmp_path)
    assert isinstance(plan.operations, list)
