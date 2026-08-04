"""Tests for eurika.knowledge.knowledge_graph (R10, build_test_links)."""

from pathlib import Path

from eurika.knowledge import CodeGraph, build_code_graph, build_test_links


def test_build_test_links_empty(tmp_path: Path) -> None:
    """Empty code graph yields no links."""
    cg = CodeGraph(nodes=set(), edges={})
    assert build_test_links(tmp_path, cg) == []


def test_build_test_links_by_import(tmp_path: Path) -> None:
    """Test file importing project module yields link."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text('from myapp.bar import func\ndef test_x(): pass')
    (tmp_path / "myapp").mkdir()
    (tmp_path / "myapp" / "__init__.py").write_text("")
    (tmp_path / "myapp" / "bar.py").write_text("def func(): pass")

    self_map = {
        "modules": [
            {"path": "myapp/__init__.py", "name": "myapp"},
            {"path": "myapp/bar.py", "name": "bar"},
        ],
        "dependencies": {"myapp/bar.py": ["myapp"]},
    }
    cg = build_code_graph(self_map)
    links = build_test_links(tmp_path, cg)
    assert ("tests/test_foo.py", "myapp/bar.py") in links


def test_build_test_links_skips_external(tmp_path: Path) -> None:
    """External imports (sys, pathlib) are not linked."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_misc.py").write_text("import sys\nfrom pathlib import Path\nfrom foo import x")

    (tmp_path / "foo.py").write_text("x = 1")
    self_map = {"modules": [{"path": "foo.py", "name": "foo"}], "dependencies": {}}
    cg = build_code_graph(self_map)
    links = build_test_links(tmp_path, cg)
    assert links == [("tests/test_misc.py", "foo.py")]
