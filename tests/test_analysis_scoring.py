"""Tests for eurika.analysis.scoring (ROADMAP v3.0 Stage 2)."""

from __future__ import annotations

import pytest

from eurika.analysis.graph import ProjectGraph
from eurika.analysis.scoring import compute_architecture_scores


def test_compute_architecture_scores_empty_graph() -> None:
    g = ProjectGraph([], {})
    s = compute_architecture_scores(g, [])
    assert 0 <= s["cohesion"] <= 1
    assert 0 <= s["coupling"] <= 1
    assert 0 <= s["complexity"] <= 1
    assert 0 <= s["modularity"] <= 1


def test_compute_architecture_scores_simple_graph() -> None:
    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    s = compute_architecture_scores(g, [])
    assert "cohesion" in s
    assert "coupling" in s
    assert "complexity" in s
    assert "modularity" in s


def test_compute_architecture_scores_with_smells() -> None:
    class FakeSmell:
        type = "god_module"
        nodes = ["a.py"]
        severity = 5.0

    g = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py", "c.py"]})
    s = compute_architecture_scores(g, [FakeSmell()])
    assert s["cohesion"] < 1.0  # god_module penalty
