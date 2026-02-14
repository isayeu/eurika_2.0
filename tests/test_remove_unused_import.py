"""Tests for eurika.refactor.remove_unused_import."""

from pathlib import Path

from eurika.refactor.remove_unused_import import remove_unused_imports


def test_remove_unused_simple(tmp_path: Path) -> None:
    """Remove unused `import foo`."""
    f = tmp_path / "test.py"
    f.write_text("import foo\nx = 1\n")
    result = remove_unused_imports(f)
    assert result is not None
    assert "import foo" not in result
    assert "x = 1" in result


def test_keep_used_import(tmp_path: Path) -> None:
    """Keep import that is used."""
    f = tmp_path / "test.py"
    f.write_text("import bar\nprint(bar)\n")
    result = remove_unused_imports(f)
    assert result is None  # no changes


def test_remove_one_from_multi(tmp_path: Path) -> None:
    """Remove unused from `from x import a, b, c` when b is unused."""
    f = tmp_path / "test.py"
    f.write_text("from x import a, b, c\ny = a + c\n")
    result = remove_unused_imports(f)
    assert result is not None
    assert "from x import" in result
    assert "a" in result
    assert "c" in result
    assert ", b" not in result and "b," not in result


def test_keep_future(tmp_path: Path) -> None:
    """Do not touch __future__ imports."""
    f = tmp_path / "test.py"
    f.write_text("from __future__ import annotations\nx = 1\n")
    result = remove_unused_imports(f)
    assert result is None


def test_keep_star_import(tmp_path: Path) -> None:
    """Do not touch `from x import *`."""
    f = tmp_path / "test.py"
    f.write_text("from os.path import *\nx = join('a', 'b')\n")
    result = remove_unused_imports(f)
    assert result is None


def test_keep_imports_in_all(tmp_path: Path) -> None:
    """Preserve imports that are re-exported via __all__."""
    code = '''from bar import foo

__all__ = ["foo"]
'''
    f = tmp_path / "test.py"
    f.write_text(code)
    result = remove_unused_imports(f)
    assert result is None  # foo must be kept


def test_keep_imports_under_type_checking(tmp_path: Path) -> None:
    """Preserve imports inside `if TYPE_CHECKING:` (used only in type hints)."""
    code = """from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foo import Bar

def f() -> Bar:
    return None
"""
    f = tmp_path / "test.py"
    f.write_text(code)
    result = remove_unused_imports(f)
    assert result is None  # Bar import must be kept
