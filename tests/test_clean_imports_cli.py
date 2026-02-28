"""Tests for eurika clean-imports CLI command."""
from pathlib import Path


def test_polygon_module_loads() -> None:
    """Polygon (OPERABILITY D) — module loads after potential remove_unused_import."""
    from eurika.polygon import polygon_imports_ok

    assert polygon_imports_ok() == Path(".")


def test_clean_imports_dry_run(tmp_path: Path) -> None:
    """clean-imports (no --apply) reports files that would be modified."""
    (tmp_path / 'a.py').write_text('import unused_mod\nx = 1\n')
    (tmp_path / 'b.py').write_text('import used\nprint(used)\n')
    from cli.core_handlers import handle_clean_imports
    from types import SimpleNamespace
    args = SimpleNamespace(path=tmp_path, apply=False)
    assert handle_clean_imports(args) == 0
    assert (tmp_path / 'a.py').read_text() == 'import unused_mod\nx = 1\n'

def test_clean_imports_skips_api_facades(tmp_path: Path) -> None:
    """*_api.py files (re-export facades) are skipped, like __init__.py."""
    facade_content = "from foo import Bar, Baz\n__all__ = ['Bar', 'Baz']\n"
    (tmp_path / 'my_api.py').write_text(facade_content)
    (tmp_path / 'foo.py').write_text('class Bar: pass\nclass Baz: pass\n')
    (tmp_path / 'other.py').write_text('import unused_xyz\nx = 1\n')
    from cli.core_handlers import handle_clean_imports
    from types import SimpleNamespace
    args = SimpleNamespace(path=tmp_path, apply=True)
    handle_clean_imports(args)
    assert (tmp_path / 'my_api.py').read_text() == facade_content

def test_clean_imports_apply(tmp_path: Path) -> None:
    """clean-imports --apply modifies files."""
    from types import SimpleNamespace
    (tmp_path / 'foo.py').write_text('import os\nimport sys\nx = os.path\n')
    args = SimpleNamespace(path=tmp_path, apply=True)
    from cli.core_handlers import handle_clean_imports
    handle_clean_imports(args)
    content = (tmp_path / 'foo.py').read_text()
    assert 'import sys' not in content
    assert 'import os' in content