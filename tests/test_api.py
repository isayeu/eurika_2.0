"""Tests for eurika.api (JSON API for future UI)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.api import get_summary, get_history, get_diff, get_patch_plan, get_code_smell_operations


def test_get_summary_returns_json_serializable(tmp_path: Path) -> None:
    """get_summary returns a dict that can be json.dumps'd."""
    # No self_map -> error payload
    data = get_summary(tmp_path)
    assert "error" in data
    assert "path" in data
    s = json.dumps(data)
    assert "self_map" in s or "path" in s


def test_get_summary_with_self_map(tmp_path: Path) -> Path:
    """With a minimal self_map, get_summary returns system/central_modules/risks/maturity."""
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py","lines":10,"functions":[],"classes":[]},'
        '{"path":"b.py","lines":10,"functions":[],"classes":[]}],'
        '"dependencies":{"a.py":["b"]},"summary":{"files":2,"total_lines":20}}',
        encoding="utf-8",
    )
    data = get_summary(tmp_path)
    assert "error" not in data
    assert "system" in data
    assert "modules" in data["system"]
    assert "maturity" in data
    json.dumps(data)


def test_get_history_returns_json_serializable(tmp_path: Path) -> None:
    """get_history returns dict with trends, regressions, evolution_report, points."""
    data = get_history(tmp_path, window=5)
    assert "trends" in data
    assert "regressions" in data
    assert "evolution_report" in data
    assert "points" in data
    json.dumps(data)


def test_get_diff_returns_json_serializable(tmp_path: Path) -> None:
    """get_diff with same path returns structures/centrality_shifts/... all JSON-serializable."""
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py","lines":10,"functions":[],"classes":[]}],'
        '"dependencies":{},"summary":{"files":1,"total_lines":10}}',
        encoding="utf-8",
    )
    data = get_diff(self_map, self_map)
    assert "structures" in data
    assert "centrality_shifts" in data
    assert "maturity" in data
    out = json.dumps(data)
    assert "modules_common" in out or "modules_added" in out


def test_get_patch_plan_returns_none_without_self_map(tmp_path: Path) -> None:
    """get_patch_plan returns None when self_map.json is missing."""
    assert get_patch_plan(tmp_path) is None


def test_get_patch_plan_returns_dict_with_self_map(tmp_path: Path) -> None:
    """get_patch_plan returns dict with operations when self_map exists."""
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py","lines":10,"functions":[],"classes":[]}],'
        '"dependencies":{},"summary":{"files":1,"total_lines":10}}',
        encoding="utf-8",
    )
    data = get_patch_plan(tmp_path)
    assert data is not None
    assert "operations" in data
    assert isinstance(data["operations"], list)
    json.dumps(data)


def test_get_code_smell_operations_returns_ops_for_long_function(tmp_path: Path) -> None:
    """get_code_smell_operations returns refactor_code_smell ops when file has long function (51+ lines)."""
    long_func = "def long_foo():\n" + "    x = 1\n" * 50 + "    return x\n"
    (tmp_path / "big.py").write_text(long_func, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    long_ops = [o for o in ops if o.get("kind") == "refactor_code_smell" and o.get("target_file") == "big.py"]
    assert len(long_ops) >= 1
    assert any(o.get("smell_type") == "long_function" and o.get("params", {}).get("location") == "long_foo" for o in long_ops)
