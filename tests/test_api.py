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


def test_get_code_smell_operations_skips_long_function_when_no_real_fix(tmp_path: Path) -> None:
    """By default, skip (no ops) when long_function has no extractable nested (ROADMAP: не эмитить при отсутствии реального фикса)."""
    long_func = "def long_foo():\n" + "    x = 1\n" * 50 + "    return x\n"
    (tmp_path / "big.py").write_text(long_func, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    long_ops = [o for o in ops if o.get("target_file") == "big.py"]
    assert len(long_ops) == 0


def test_get_code_smell_operations_emits_todo_when_env_set(tmp_path: Path) -> None:
    """With EURIKA_EMIT_CODE_SMELL_TODO=1, emit refactor_code_smell for long_function without extractable nested."""
    import os
    long_func = "def long_foo():\n" + "    x = 1\n" * 50 + "    return x\n"
    (tmp_path / "big.py").write_text(long_func, encoding="utf-8")
    os.environ["EURIKA_EMIT_CODE_SMELL_TODO"] = "1"
    try:
        ops = get_code_smell_operations(tmp_path)
        long_ops = [o for o in ops if o.get("kind") == "refactor_code_smell" and o.get("target_file") == "big.py"]
        assert len(long_ops) >= 1
        assert any(o.get("smell_type") == "long_function" and o.get("params", {}).get("location") == "long_foo" for o in long_ops)
    finally:
        os.environ.pop("EURIKA_EMIT_CODE_SMELL_TODO", None)


def test_get_code_smell_operations_skips_extract_nested_on_failed_learning(tmp_path: Path) -> None:
    """When long_function|extract_nested_function history is 0-success, skip extract_nested and skip refactor_code_smell (no real fix)."""
    lines = "\n".join(("    x = 1" for _ in range(48)))
    content = (
        "def long_foo():\n"
        "    def helper():\n"
        "        return 42\n"
        f"{lines}\n"
        "    return helper() + x\n"
    )
    (tmp_path / "big.py").write_text(content, encoding="utf-8")

    # Prime learning store with 0/1 for long_function|extract_nested_function.
    from eurika.storage import ProjectMemory

    memory = ProjectMemory(tmp_path)
    memory.learning.append(
        project_root=tmp_path,
        modules=["big.py"],
        operations=[{"kind": "extract_nested_function", "smell_type": "long_function"}],
        risks=[],
        verify_success=False,
    )

    ops = get_code_smell_operations(tmp_path)
    assert not any(o.get("kind") == "extract_nested_function" for o in ops)
    assert not any(o.get("kind") == "refactor_code_smell" and o.get("target_file") == "big.py" for o in ops)


def test_get_code_smell_operations_skips_when_architectural_todo_exists(tmp_path: Path) -> None:
    """Do not add code-smell TODO when module already has architectural TODO marker."""
    long_func = (
        "def long_foo():\n"
        + "    x = 1\n" * 50
        + "    return x\n"
        + "\n# TODO: Refactor big.py (god_module -> split_module)\n"
    )
    (tmp_path / "big.py").write_text(long_func, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    assert not any(
        o.get("kind") == "refactor_code_smell" and o.get("target_file") == "big.py"
        for o in ops
    )


def test_get_code_smell_operations_long_function_extract_block_fallback(tmp_path: Path) -> None:
    """long_function without nested def: fallback to extract_block when if/for block is extractable."""
    # 50+ lines, no nested def, but has extractable if block (5+ lines, no break/return)
    code = (
        "def long_foo(x):\n"
        "    result = 0\n"
        "    if x > 0:\n"
        "        a = x + 1\n"
        "        b = a * 2\n"
        "        c = b + x\n"
        "        d = c * 2\n"
        "        e = d + 1\n"
        "        result = e\n"
        + "    result += 1\n" * 45
        + "    return result\n"
    )
    (tmp_path / "flat.py").write_text(code, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    block_ops = [o for o in ops if o.get("kind") == "extract_block_to_helper" and o.get("target_file") == "flat.py"]
    assert len(block_ops) >= 1, "long_function with extractable block should get extract_block_to_helper"
    assert block_ops[0].get("smell_type") == "long_function"


def test_get_code_smell_operations_returns_extract_block_for_deep_nesting(tmp_path: Path) -> None:
    """With hybrid mode (default), deep_nesting gets extract_block_to_helper when block is extractable."""
    # Need depth > 4 for CodeAwareness to flag deep_nesting; 5 nested ifs
    code = """
def deep_foo(x):
    if x > 0:
        if x < 10:
            if x > 1:
                if x < 9:
                    if True:
                        a = x + 1
                        b = a * 2
                        c = b + x
                        d = c * 2
                        result = d
    return 0
"""
    (tmp_path / "nested.py").write_text(code, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    block_ops = [o for o in ops if o.get("kind") == "extract_block_to_helper" and o.get("target_file") == "nested.py"]
    assert len(block_ops) >= 1
    op = block_ops[0]
    assert op.get("smell_type") == "deep_nesting"
    assert "helper_name" in op.get("params", {})
    assert "block_start_line" in op.get("params", {})


def test_get_code_smell_operations_skips_test_files(tmp_path: Path) -> None:
    """Do not emit refactor_code_smell TODOs for tests/* files."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    long_func = "def long_test_fn():\n" + "    x = 1\n" * 50 + "    return x\n"
    (tests_dir / "test_big.py").write_text(long_func, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    assert not any(
        o.get("kind") == "refactor_code_smell" and o.get("target_file", "").startswith("tests/")
        for o in ops
    )


def test_get_code_smell_operations_skips_second_todo_same_smell_type(tmp_path: Path) -> None:
    """Do not stack multiple long_function TODO markers in the same file."""
    long_func = (
        "def long_foo():\n"
        + "    x = 1\n" * 50
        + "    return x\n"
        + "\n# TODO (eurika): refactor long_function 'old_fn' — consider extracting helper\n"
    )
    (tmp_path / "big.py").write_text(long_func, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    assert not any(
        o.get("kind") == "refactor_code_smell"
        and o.get("smell_type") == "long_function"
        and o.get("target_file") == "big.py"
        for o in ops
    )
