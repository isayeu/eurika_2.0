"""Tests for ArchitectureSnapshot, ExecutionContext (ROADMAP §5.7, review §3)."""

from __future__ import annotations

from pathlib import Path

from eurika.analysis.graph import ProjectGraph
from eurika.reasoning.execution_context import ExecutionContext
from eurika.reasoning.planner.models import ArchitectureSnapshot


def test_architecture_snapshot_from_graph_and_smells() -> None:
    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    smells = []
    snap = ArchitectureSnapshot.from_graph_and_smells(g, smells)
    assert snap.graph is g
    assert snap.metrics is not None
    assert len(snap.smells) == 0


def test_architecture_snapshot_with_smells() -> None:
    class FakeSmell:
        type = "god_module"
        nodes = ["a.py"]
        severity = 5.0
        description = "test"

    g = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py", "c.py"]})
    snap = ArchitectureSnapshot.from_graph_and_smells(g, [FakeSmell()])
    assert len(snap.smells) == 1
    assert snap.smells[0].type == "god_module"
    assert snap.metrics.cohesion < 1.0


def test_execution_context_defaults() -> None:
    ctx = ExecutionContext()
    assert ctx.snapshot_before is None
    assert ctx.candidates is None
    assert ctx.delta_score is None


def test_execution_context_with_snapshot() -> None:
    g = ProjectGraph(["a.py"], {})
    snap = ArchitectureSnapshot.from_graph_and_smells(g, [])
    ctx = ExecutionContext(snapshot_before=snap, delta_score=0.1)
    assert ctx.snapshot_before is not None
    assert ctx.delta_score == 0.1


def test_architecture_snapshot_from_graph_and_smells_with_root_summary() -> None:
    """from_graph_and_smells accepts optional root, summary, history, diff."""
    g = ProjectGraph(["a.py"], {})
    snap = ArchitectureSnapshot.from_graph_and_smells(
        g, [], root=Path("/proj"), summary={"risks": []}, history={"trends": {}}
    )
    assert snap.root == Path("/proj")
    assert snap.summary == {"risks": []}
    assert snap.history == {"trends": {}}


def test_update_execution_context_after_rescan() -> None:
    """_update_execution_context_after_rescan fills delta_score and snapshot_after (EXECUTION_MODEL_PLAN §C)."""
    from eurika.orchestration.apply_stage import _update_execution_context_after_rescan

    ctx = ExecutionContext()
    result = type("R", (), {"output": {"execution_context": ctx}})()
    report: dict = {
        "verify": {"success": True},
        "verify_metrics": {"before_score": 0.5, "after_score": 0.7},
    }
    _update_execution_context_after_rescan(result, report, Path("/nonexistent"), lambda _: None)
    assert ctx.delta_score == 0.2
    assert report["delta_score"] == 0.2


def test_simulation_result_in_context(tmp_path: Path) -> None:
    """execute_fix_apply_stage fills context.simulation_result (EXECUTION_MODEL_PLAN §D)."""
    from eurika.orchestration.apply_stage import execute_fix_apply_stage

    (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")
    ops = [{"target_file": "foo.py", "kind": "remove_unused_import"}]
    plan = {"operations": ops}
    ctx = type("ExecutionContext", (), {"simulation_result": None, "snapshot_before": None})()
    result = type("R", (), {"output": {"execution_context": ctx, "policy_decisions": []}})()
    report, _, _ = execute_fix_apply_stage(
        tmp_path,
        plan,
        ops,
        session_id=None,
        quiet=True,
        verify_cmd=None,
        verify_timeout=None,
        backup_dir=".eurika_backups",
        apply_and_verify=lambda *a, **k: {"modified": [], "verify": {"success": True}},
        run_scan=lambda *a: 0,
        build_snapshot_from_self_map=lambda *a: {},
        diff_architecture_snapshots=lambda *a: {},
        metrics_from_graph=lambda *a: {},
        rollback_patch=lambda *a: {},
        result=result,
    )
    assert ctx.simulation_result is not None
    assert hasattr(ctx.simulation_result, "errors")
    assert hasattr(ctx.simulation_result, "would_modify")


def test_update_execution_context_skips_without_context() -> None:
    """_update_execution_context_after_rescan no-ops when result has no execution_context."""
    from eurika.orchestration.apply_stage import _update_execution_context_after_rescan

    result = type("R", (), {"output": {}})()
    report = {"verify": {"success": True}, "verify_metrics": {"before_score": 0.5, "after_score": 0.7}}
    _update_execution_context_after_rescan(result, report, Path("/x"), lambda _: None)
    assert "delta_score" not in report


def test_architecture_snapshot_from_core_snapshot() -> None:
    """from_core_snapshot builds unified snapshot from pipeline output (review §3)."""
    class CoreSnapshot:
        root = Path("/proj")
        graph = None
        smells = []
        summary = {"risks": []}
        history = {"trends": {}}
        diff = None

    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})

    class FakeSmell:
        type = "hub"
        nodes = ["a.py"]
        severity = 4.0
        description = "Hub"

    core = CoreSnapshot()
    core.graph = g
    core.smells = [FakeSmell()]

    snap = ArchitectureSnapshot.from_core_snapshot(core)
    assert snap.graph is g
    assert snap.metrics is not None
    assert len(snap.smells) == 1
    assert snap.smells[0].type == "hub"
    assert snap.root == Path("/proj")
    assert snap.summary == {"risks": []}
