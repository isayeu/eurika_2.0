"""Tests for eurika.knowledge.code_graph (R10, KNOWLEDGE_GRAPH_DESIGN)."""

from eurika.knowledge import CodeGraph, build_code_graph


def test_build_code_graph_empty() -> None:
    """Empty self_map yields empty graph."""
    cg = build_code_graph({})
    assert cg.nodes == set()
    assert cg.edges == {}
    assert cg.import_edges() == []


def test_build_code_graph_from_self_map() -> None:
    """Modules and dependencies become nodes and edges."""
    self_map = {
        "modules": [
            {"path": "a/foo.py", "name": "foo"},
            {"path": "a/bar.py", "name": "bar"},
        ],
        "dependencies": {"a/foo.py": ["bar"]},
    }
    cg = build_code_graph(self_map)
    assert "a/foo.py" in cg.nodes
    assert "a/bar.py" in cg.nodes
    assert cg.edges.get("a/foo.py") == ["a/bar.py"]
    assert ("a/foo.py", "a/bar.py") in cg.import_edges()
