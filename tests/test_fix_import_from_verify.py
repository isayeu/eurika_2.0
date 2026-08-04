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
