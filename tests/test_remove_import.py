"""Tests for eurika.refactor.remove_import."""

import tempfile
from pathlib import Path

from eurika.refactor.remove_import import remove_import_from_file


def test_remove_import_simple(tmp_path: Path) -> None:
    """Remove `import foo` from file."""
    f = tmp_path / "test.py"
    f.write_text("import foo\nimport bar\nx = 1\n")
    result = remove_import_from_file(f, "foo")
    assert result is not None
    assert "import foo" not in result
    assert "import bar" in result
    assert "x = 1" in result


def test_remove_import_from_import(tmp_path: Path) -> None:
    """Remove `from foo import X` from file."""
    f = tmp_path / "test.py"
    f.write_text("from foo import bar, baz\nx = 1\n")
    result = remove_import_from_file(f, "foo")
    assert result is not None
    assert "from foo" not in result
    assert "x = 1" in result


def test_remove_import_first_part_match(tmp_path: Path) -> None:
    """Match by first part: eurika.storage -> eurika."""
    f = tmp_path / "test.py"
    f.write_text("from eurika.storage import memory\nx = 1\n")
    result = remove_import_from_file(f, "eurika")
    assert result is not None
    assert "eurika" not in result or "from eurika" not in result


def test_remove_import_not_found(tmp_path: Path) -> None:
    """Return None when target not in file."""
    f = tmp_path / "test.py"
    f.write_text("import bar\nx = 1\n")
    result = remove_import_from_file(f, "foo")
    assert result is None


def test_remove_import_multi_import_line(tmp_path: Path) -> None:
    """Remove one alias from `import a, b, c`."""
    f = tmp_path / "test.py"
    f.write_text("import a, b, c\nx = 1\n")
    result = remove_import_from_file(f, "b")
    assert result is not None
    assert "import b" not in result
    assert "import a" in result or "import a," in result
    assert "import c" in result or ", c" in result
