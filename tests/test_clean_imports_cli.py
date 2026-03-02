"""Tests for eurika clean-imports CLI command."""
from pathlib import Path


def test_polygon_module_loads() -> None:
    """Polygon (OPERABILITY D) — module loads after potential remove_unused_import."""
    from eurika.polygon import polygon_imports_ok

    assert polygon_imports_ok() == Path(".")


def test_polygon_extractable_block_semantics() -> None:
    """DRILL_EXTRACTABLE_BLOCK — extract_block_to_helper must preserve semantics."""
    from eurika.polygon import polygon_extractable_block

    assert polygon_extractable_block(5) == 34


def test_polygon_long_function_semantics() -> None:
    """DRILL_LONG_FUNCTION — extract_nested_function must preserve semantics."""
    from eurika.polygon import polygon_long_function

    assert polygon_long_function() == 55


def test_polygon_deep_nesting_extractable_semantics() -> None:
    """DRILL_DEEP_NESTING — extract_block_to_helper must preserve semantics."""
    from eurika.polygon import polygon_deep_nesting_extractable

    assert polygon_deep_nesting_extractable(5) == 34


def test_polygon_long_function_extractable_block_semantics() -> None:
    """DRILL_LONG_FUNCTION_EXTRACTABLE — long_function + extract_block_to_helper preserves semantics."""
    from eurika.polygon import polygon_long_function_extractable_block

    assert polygon_long_function_extractable_block(5) == 45


def test_polygon_refactor_code_smell_drill_semantics() -> None:
    """DRILL_REFACTOR_CODE_SMELL — long_function без extractable; целевой для LLM-powered extract."""
    from eurika.polygon import polygon_refactor_code_smell_drill

    # seed=1: a=2,b=4,c=5,d=10,e=12,f=24,g=28,h=56,i=61,j=122,_1=1
    assert polygon_refactor_code_smell_drill(1) == 2 + 4 + 5 + 10 + 12 + 24 + 28 + 56 + 61 + 122 + 1


def test_polygon_split_demo_semantics() -> None:
    """DRILL_SPLIT (CR-E3) — split_demo validators + formatters preserve semantics."""
    from eurika.polygon import polygon_split_demo

    assert polygon_split_demo("hi", 50, 12) == "[HI:0012]"
    assert polygon_split_demo("", 0, 1) == ""
    assert polygon_split_demo("x", -1, 5) == ""


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