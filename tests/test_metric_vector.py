"""Tests for eurika.analysis.metric_vector (ROADMAP §5.7, review 2026 II)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from eurika.analysis.graph import ProjectGraph
from eurika.analysis.metric_vector import MetricVector, compute_metric_vector


def test_metric_vector_empty_graph() -> None:
    g = ProjectGraph([], {})
    mv = compute_metric_vector(g, [])
    assert 0 <= mv.complexity <= 1
    assert 0 <= mv.coupling <= 1
    assert 0 <= mv.cohesion <= 1
    assert 0 <= mv.instability <= 1
    assert 0 <= mv.layering_violations <= 1
    assert 0 <= mv.entropy <= 1


def test_metric_vector_to_array() -> None:
    mv = MetricVector(
        complexity=0.1,
        coupling=0.2,
        cohesion=0.8,
        instability=0.3,
        layering_violations=0.0,
        entropy=0.1,
    )
    arr = mv.to_array()
    assert len(arr) == 6
    assert arr == (0.1, 0.2, 0.8, 0.3, 0.0, 0.1)


def test_metric_vector_frozen() -> None:
    mv = MetricVector(0.0, 0.0, 0.5, 0.5, 0.0, 0.0)
    with pytest.raises(FrozenInstanceError):
        mv.complexity = 1.0  # type: ignore[misc]


def test_compute_metric_vector_simple_graph() -> None:
    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"]})
    mv = compute_metric_vector(g, [])
    assert isinstance(mv, MetricVector)
    assert "cohesion" in dir(mv)


def test_compute_metric_vector_with_smells() -> None:
    class FakeSmell:
        type = "god_module"
        nodes = ["a.py"]
        severity = 5.0

    g = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py", "c.py"]})
    mv = compute_metric_vector(g, [FakeSmell()])
    assert mv.cohesion < 1.0


def test_compute_metric_vector_cycle_increases_violations() -> None:
    # Linear: a->b->c
    g_linear = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py"], "b.py": ["c.py"]})
    mv_linear = compute_metric_vector(g_linear, [])

    # Cycle: a->b->c->a
    g_cycle = ProjectGraph(
        ["a.py", "b.py", "c.py"],
        {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": ["a.py"]},
    )
    mv_cycle = compute_metric_vector(g_cycle, [])

    assert mv_cycle.complexity >= mv_linear.complexity
    assert mv_cycle.layering_violations >= mv_linear.layering_violations
