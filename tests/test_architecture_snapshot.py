"""Tests for ArchitectureSnapshot, ExecutionContext (ROADMAP §5.7)."""

from __future__ import annotations

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
