"""Tests for eurika.storage.ProjectMemory facade."""

from pathlib import Path

import pytest

from eurika.storage import ProjectMemory


def test_project_memory_feedback(tmp_path: Path) -> None:
    """ProjectMemory(path).feedback is appendable and readable."""
    memory = ProjectMemory(tmp_path)
    memory.feedback.append(
        project_root=tmp_path,
        action="explain_risk",
        outcome="accepted",
        target="foo.py",
    )
    records = memory.feedback.all()
    assert len(records) == 1
    assert records[0].action == "explain_risk"
    assert records[0].outcome == "accepted"
    assert (tmp_path / "architecture_feedback.json").exists()


def test_project_memory_learning(tmp_path: Path) -> None:
    """ProjectMemory(path).learning is appendable and aggregatable."""
    memory = ProjectMemory(tmp_path)
    memory.learning.append(
        project_root=tmp_path,
        modules=["a.py"],
        operations=[{"kind": "refactor_module", "smell_type": "god_module"}],
        risks=[],
        verify_success=True,
    )
    by_kind = memory.learning.aggregate_by_action_kind()
    assert "refactor_module" in by_kind
    assert (tmp_path / "architecture_learning.json").exists()


def test_project_memory_observations(tmp_path: Path) -> None:
    """ProjectMemory(path).observations records and snapshots."""
    memory = ProjectMemory(tmp_path)
    memory.observations.record_observation("scan", {"modules": 5})
    snap = memory.observations.snapshot()
    assert len(snap) == 1
    assert snap[0].trigger == "scan"
    assert (tmp_path / "eurika_observations.json").exists()


def test_project_memory_history(tmp_path: Path) -> None:
    """ProjectMemory(path).history exposes ArchitectureHistory API."""
    memory = ProjectMemory(tmp_path)
    # Empty history: trend and evolution_report still work
    trend = memory.history.trend(window=5)
    assert isinstance(trend, dict)
    report = memory.history.evolution_report(window=5)
    assert isinstance(report, str)
