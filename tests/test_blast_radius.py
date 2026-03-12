"""Tests for RV1 Blast Radius, RV2 Dependency Density."""

from pathlib import Path

import pytest

from eurika.analysis.graph import ProjectGraph
from eurika.analysis.metrics import (
    blast_radius_for_project,
    dependency_density,
    top_blast_radius,
)


def test_blast_radius_direct_only() -> None:
    """Single-level: A->B, C->B => blast_radius(B)=2."""
    nodes = ["a.py", "b.py", "c.py"]
    edges = {"a.py": ["b.py"], "c.py": ["b.py"], "b.py": []}
    graph = ProjectGraph(nodes, edges)
    assert graph.blast_radius("b.py") == 2
    assert graph.blast_radius("a.py") == 0
    assert graph.blast_radius("c.py") == 0


def test_blast_radius_transitive() -> None:
    """Chain: A->B->C => blast_radius(C)=2 (A and B depend on C)."""
    nodes = ["a.py", "b.py", "c.py"]
    edges = {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": []}
    graph = ProjectGraph(nodes, edges)
    assert graph.blast_radius("c.py") == 2
    assert graph.blast_radius("b.py") == 1
    assert graph.blast_radius("a.py") == 0


def test_blast_radius_unknown_module() -> None:
    """Unknown module returns 0."""
    graph = ProjectGraph(["a.py"], {"a.py": []})
    assert graph.blast_radius("x.py") == 0


def test_top_blast_radius() -> None:
    """Top N sorted by blast radius descending."""
    nodes = ["a.py", "b.py", "c.py", "d.py"]
    edges = {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": [], "d.py": ["c.py"]}
    graph = ProjectGraph(nodes, edges)
    top = top_blast_radius(graph, n=3)
    assert len(top) == 3
    assert top[0][1] >= top[1][1] >= top[2][1]
    assert top[0][0] == "c.py"
    assert top[0][1] == 3


def test_blast_radius_for_project_missing_self_map(tmp_path: Path) -> None:
    """No self_map.json returns empty list."""
    assert blast_radius_for_project(tmp_path) == []


def test_blast_radius_for_project(tmp_path: Path) -> None:
    """Load self_map, return top blast radius."""
    data = {
        "modules": [
            {"path": "foo/a.py"},
            {"path": "foo/b.py"},
            {"path": "foo/c.py"},
        ],
        "dependencies": {"a.py": ["b"], "b.py": ["c"], "c.py": []},
    }
    import json

    (tmp_path / "self_map.json").write_text(json.dumps(data), encoding="utf-8")
    top = blast_radius_for_project(tmp_path)
    assert len(top) >= 1
    assert all(isinstance(p, tuple) and len(p) == 2 for p in top)


def test_dependency_density_empty() -> None:
    """n<2 returns 0."""
    graph = ProjectGraph(["a.py"], {"a.py": []})
    assert dependency_density(graph) == 0.0


def test_dependency_density_sparse() -> None:
    """2 nodes, 1 edge => 1/(2*1)=0.5."""
    graph = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": []})
    assert dependency_density(graph) == 0.5


def test_dependency_density_three_nodes() -> None:
    """3 nodes, 2 edges => 2/(3*2)=0.3333."""
    graph = ProjectGraph(
        ["a.py", "b.py", "c.py"],
        {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": []},
    )
    assert dependency_density(graph) == pytest.approx(0.3333, abs=0.0001)
