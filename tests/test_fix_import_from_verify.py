"""Tests for fix_import_from_verify (parse verify output, suggest fix, create stub)."""
from pathlib import Path

from eurika.refactor.fix_import_from_verify import (
    parse_verify_import_error,
    suggest_fix_import_operations,
)


def test_parse_module_not_found():
    """parse_verify_import_error extracts ModuleNotFoundError."""
    stdout = """
ERROR collecting test_internal_goals.py
ImportError while importing test module '/tmp/eurika/test_internal_goals.py'.
test_internal_goals.py:1: in <module>
    from internal_goals import load_internal_goals
E   ModuleNotFoundError: No module named 'internal_goals'
"""
    parsed = parse_verify_import_error(stdout, "")
    assert parsed is not None
    assert parsed["error_type"] == "ModuleNotFoundError"
    assert parsed["missing_module"] == "internal_goals"
    assert parsed["requested_symbols"] == ["load_internal_goals"]
    assert parsed["failing_file"] == "test_internal_goals.py"


def test_parse_import_error():
    """parse_verify_import_error extracts ImportError."""
    text = """
ImportError: cannot import name 'foo' from 'bar'
"""
    parsed = parse_verify_import_error(text, "")
    assert parsed is not None
    assert parsed["error_type"] == "ImportError"
    assert parsed["missing_module"] == "bar"
    assert parsed["requested_symbols"] == ["foo"]


def test_parse_name_error():
    """parse_verify_import_error extracts NameError."""
    text = """
goals_goalsystemextracted.py:10: in _load_data
    return safe_json_read(GOALS_FILE, ...)
E   NameError: name 'GOALS_FILE' is not defined
"""
    parsed = parse_verify_import_error(text, "")
    assert parsed is not None
    assert parsed["error_type"] == "NameError"
    assert parsed["missing_name"] == "GOALS_FILE"
    assert parsed["failing_file"] == "goals_goalsystemextracted.py"


def test_suggest_create_stub(tmp_path: Path):
    """suggest_fix_import_operations creates stub when module missing and symbol not elsewhere."""
    (tmp_path / "test_internal_goals.py").write_text(
        "from internal_goals import load_internal_goals\n",
        encoding="utf-8",
    )
    parsed = {
        "missing_module": "internal_goals",
        "requested_symbols": ["load_internal_goals"],
        "failing_file": "test_internal_goals.py",
    }
    ops = suggest_fix_import_operations(tmp_path, parsed)
    assert len(ops) == 1
    assert ops[0]["kind"] == "create_module_stub"
    assert ops[0]["target_file"] == "internal_goals.py"
    assert "INTERNAL_GOALS_FILE" in ops[0]["content"]
    assert "def load_internal_goals" in ops[0]["content"]


def test_suggest_fix_name_error_adds_constant(tmp_path: Path) -> None:
    """suggest_fix_import_operations adds missing constant from sibling module for NameError."""
    (tmp_path / "goals.py").write_text(
        "from pathlib import Path\n\nGOALS_FILE = Path('goals.json')\n\nclass G: pass\n",
        encoding="utf-8",
    )
    (tmp_path / "goals_goalsystemextracted.py").write_text(
        "def _load_data():\n    return open(GOALS_FILE).read()\n",
        encoding="utf-8",
    )
    parsed = {
        "error_type": "NameError",
        "missing_name": "GOALS_FILE",
        "requested_symbols": ["GOALS_FILE"],
        "failing_file": "goals_goalsystemextracted.py",
    }
    ops = suggest_fix_import_operations(tmp_path, parsed)
    assert len(ops) == 1
    assert ops[0]["kind"] == "fix_import"
    assert "GOALS_FILE = Path('goals.json')" in ops[0]["diff"]
    assert "from pathlib import Path" in ops[0]["diff"]


def test_redirect_private_symbol_after_extract(tmp_path: Path) -> None:
    """Extract leftovers: ``from old import _helper`` must retarget the new module."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "old_mod.py").write_text("def leftover():\n    return 1\n", encoding="utf-8")
    (pkg / "new_mod.py").write_text("def _helper():\n    return 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    failing = tmp_path / "tests" / "test_helper.py"
    failing.write_text("from pkg.old_mod import _helper\n", encoding="utf-8")
    log = (
        "tests/test_helper.py:1: in <module>\n"
        "    from pkg.old_mod import _helper\n"
        "E   ImportError: cannot import name '_helper' from 'pkg.old_mod'\n"
    )
    from eurika.refactor.fix_import_from_verify import (
        parse_all_verify_import_errors,
        suggest_fixes_from_verify_log,
    )

    parsed = parse_all_verify_import_errors(log)
    assert parsed and parsed[0]["requested_symbols"] == ["_helper"]
    ops = suggest_fixes_from_verify_log(tmp_path, log)
    assert len(ops) == 1
    assert "from pkg.new_mod import _helper" in ops[0]["params"]["new_content"]
    assert failing.read_text(encoding="utf-8") == "from pkg.old_mod import _helper\n"


def test_redirect_attribute_error_after_extract(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "handlers.py").write_text("def other():\n    return 0\n", encoding="utf-8")
    (pkg / "pending.py").write_text("def confirm():\n    return True\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    failing = tmp_path / "tests" / "test_attr.py"
    failing.write_text(
        "from pkg import handlers\n\nassert handlers.confirm() is True\n",
        encoding="utf-8",
    )
    log = (
        "tests/test_attr.py:3: in test_x\n"
        "    assert handlers.confirm() is True\n"
        "E   AttributeError: module 'pkg.handlers' has no attribute 'confirm'\n"
    )
    from eurika.refactor.fix_import_from_verify import suggest_fixes_from_verify_log

    ops = suggest_fixes_from_verify_log(tmp_path, log)
    assert ops
    text = ops[0]["params"]["new_content"]
    assert "from pkg import pending" in text
    assert "pending.confirm" in text
    assert "handlers.confirm" not in text


def test_apply_stub_fixes_verify(tmp_path: Path):
    """Create stub + verify passes."""
    (tmp_path / "test_internal_goals.py").write_text(
        '''import json
from pathlib import Path
from internal_goals import load_internal_goals


def test_load_internal_goals_empty(tmp_path, monkeypatch):
    tmp_file = tmp_path / "internal_goals.json"
    tmp_file.write_text("")
    monkeypatch.setattr("internal_goals.INTERNAL_GOALS_FILE", tmp_file)
    data = load_internal_goals()
    assert data == {}
''',
        encoding="utf-8",
    )
    parsed = {
        "missing_module": "internal_goals",
        "requested_symbols": ["load_internal_goals"],
        "failing_file": "test_internal_goals.py",
    }
    ops = suggest_fix_import_operations(tmp_path, parsed)
    assert ops
    from patch_apply import apply_patch_plan
    report = apply_patch_plan(tmp_path, {"operations": ops}, dry_run=False, backup=False)
    assert "internal_goals.py" in report["modified"]
    assert (tmp_path / "internal_goals.py").exists()
    from patch_engine import verify_patch
    v = verify_patch(tmp_path, timeout=10)
    assert v["success"] is True
