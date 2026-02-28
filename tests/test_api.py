"""Tests for eurika.api (JSON API for future UI)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.api import (
    get_chat_dialog_state,
    get_diff,
    get_history,
    get_learning_insights,
    get_patch_plan,
    get_pending_plan,
    preview_operation,
    get_risk_prediction,
    get_self_guard,
    get_smells_with_plugins,
    get_summary,
    get_code_smell_operations,
    get_clean_imports_operations,
    save_approvals,
)


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


def test_get_summary_with_plugins(tmp_path: Path) -> None:
    """get_summary(include_plugins=True) can merge plugin smells and adds _plugin_counts."""
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py","lines":10},{"path":"b.py","lines":10}],'
        '"dependencies":{"a.py":["b"]},"summary":{}}',
        encoding="utf-8",
    )
    data = get_summary(tmp_path, include_plugins=True)
    assert "error" not in data
    assert "system" in data
    assert "_plugin_counts" in data


def test_get_self_guard_returns_dict(tmp_path: Path) -> None:
    """get_self_guard returns dict with violations and alarms."""
    data = get_self_guard(tmp_path)
    assert "forbidden_count" in data
    assert "layer_viol_count" in data
    assert "must_split_count" in data
    assert "pass" in data
    assert "trend_alarms" in data
    assert "complexity_budget_alarms" in data
    json.dumps(data)


def test_get_risk_prediction_returns_dict(tmp_path: Path) -> None:
    """get_risk_prediction returns dict with predictions list."""
    data = get_risk_prediction(tmp_path, top_n=5)
    assert "predictions" in data
    assert isinstance(data["predictions"], list)
    json.dumps(data)


def test_get_smells_with_plugins_returns_dict(tmp_path: Path) -> None:
    """get_smells_with_plugins returns eurika_smells, plugin_smells, merged."""
    data = get_smells_with_plugins(tmp_path)
    assert "eurika_smells" in data
    assert "plugin_smells" in data
    assert "merged" in data
    assert isinstance(data["eurika_smells"], list)
    assert isinstance(data["merged"], list)
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


def test_preview_operation_remove_unused_import(tmp_path: Path) -> None:
    """preview_operation returns unified_diff for remove_unused_import when file has unused imports."""
    (tmp_path / "mod.py").write_text("import json\nimport os\nfrom pathlib import Path\ndef f(): return Path('.')\n")
    op = {"target_file": "mod.py", "kind": "remove_unused_import", "params": {}}
    result = preview_operation(tmp_path, op)
    assert "error" not in result
    assert "unified_diff" in result
    assert "import json" in result.get("old_content", "")
    assert "import json" not in result.get("new_content", "")
    assert "-import json" in result["unified_diff"] or "-import os" in result["unified_diff"]


def test_preview_operation_unsupported_kind(tmp_path: Path) -> None:
    """preview_operation returns error for unsupported kind."""
    (tmp_path / "a.py").write_text("x = 1\n")
    result = preview_operation(tmp_path, {"target_file": "a.py", "kind": "split_module", "params": {}})
    assert "error" in result
    assert "not supported" in result["error"].lower()


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
    assert "context_sources" in data
    assert isinstance(data["context_sources"], dict)
    json.dumps(data)


def test_get_pending_plan_returns_error_when_schema_invalid(tmp_path: Path) -> None:
    """get_pending_plan returns invalid-payload error for malformed operations schema."""
    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps({"operations": ["bad"]}), encoding="utf-8")
    data = get_pending_plan(tmp_path)
    assert data.get("error") == "invalid pending plan"
    assert "pending_plan.json" in (data.get("hint") or "")


def test_save_approvals_count_mismatch_returns_error(tmp_path: Path) -> None:
    """save_approvals should return error payload on operations count mismatch."""
    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps(
            {
                "operations": [
                    {"target_file": "a.py", "kind": "split", "team_decision": "pending", "approved_by": None},
                    {"target_file": "b.py", "kind": "clean", "team_decision": "pending", "approved_by": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = save_approvals(tmp_path, [{"team_decision": "approve", "approved_by": "ui"}])
    assert "count mismatch" in (out.get("error") or "")
    assert "team-mode" in (out.get("hint") or "")


def test_save_approvals_invalid_pending_shape_returns_error(tmp_path: Path) -> None:
    """save_approvals should return stable error for malformed pending operations."""
    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps({"operations": ["bad"]}), encoding="utf-8")
    out = save_approvals(tmp_path, [{"team_decision": "approve", "approved_by": "ui"}])
    assert "invalid pending plan" in (out.get("error") or "")
    assert "team-mode" in (out.get("hint") or "")


def test_save_approvals_invalid_payload_type_returns_error(tmp_path: Path) -> None:
    """save_approvals should reject non-list payload deterministically."""
    out = save_approvals(tmp_path, {"team_decision": "approve"})  # type: ignore[arg-type]
    assert out.get("error") == "invalid operations payload"
    assert "list" in (out.get("hint") or "")


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


def test_get_code_smell_operations_does_not_block_on_not_applied_outcome(tmp_path: Path) -> None:
    """not_applied history should not block extract_nested attempts."""
    lines = "\n".join(("    x = 1" for _ in range(48)))
    content = (
        "def long_foo():\n"
        "    y = 2\n"
        "    def helper():\n"
        "        total = x + y\n"
        "        result = total + 1\n"
        "        return result\n"
        f"{lines}\n"
        "    return helper()\n"
    )
    (tmp_path / "big.py").write_text(content, encoding="utf-8")

    from eurika.storage import ProjectMemory

    memory = ProjectMemory(tmp_path)
    memory.learning.append(
        project_root=tmp_path,
        modules=["big.py"],
        operations=[
            {
                "kind": "extract_nested_function",
                "smell_type": "long_function",
                "execution_outcome": "not_applied",
                "applied": False,
            }
        ],
        risks=[],
        verify_success=True,
    )

    ops = get_code_smell_operations(tmp_path)
    assert any(o.get("kind") == "extract_nested_function" for o in ops)


def test_get_code_smell_operations_skips_internal_extract_helpers_for_extract_function(tmp_path: Path) -> None:
    """Planner should not propose known internal helper extractions for extract_function module."""
    target = tmp_path / "eurika" / "refactor"
    target.mkdir(parents=True, exist_ok=True)
    code = (
        "def suggest_extract_nested_function():\n"
        + ("    x = 1\n" * 48)
        + (
        "    def _has_nonlocal_or_global(node):\n"
        "        return False\n"
        "    return _has_nonlocal_or_global(None)\n"
        )
    )
    (target / "extract_function.py").write_text(code, encoding="utf-8")
    ops = get_code_smell_operations(tmp_path)
    assert not any(
        o.get("kind") == "extract_nested_function"
        and o.get("target_file") == "eurika/refactor/extract_function.py"
        and (o.get("params") or {}).get("nested_function_name") == "_has_nonlocal_or_global"
        for o in ops
    )


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


def test_get_clean_imports_operations_skips_reexport_modules(tmp_path: Path) -> None:
    """REMOVE_UNUSED_IMPORT_SKIP: tool_contract.py (re-export layer) not proposed."""
    agent_dir = tmp_path / "eurika" / "agent"
    agent_dir.mkdir(parents=True)
    # Re-export style: import not used in file body but re-exported
    (agent_dir / "tool_contract.py").write_text(
        "from .other import DefaultToolContract\nx = 1\n",
        encoding="utf-8",
    )
    (agent_dir / "other.py").write_text("class DefaultToolContract: pass\n", encoding="utf-8")
    ops = get_clean_imports_operations(tmp_path)
    assert not any(
        o.get("kind") == "remove_unused_import" and "tool_contract" in str(o.get("target_file", ""))
        for o in ops
    )


def test_get_clean_imports_operations_skips_test_files(tmp_path: Path) -> None:
    """Do not propose remove_unused_import for tests/ (policy denies; apply-rate)."""
    (tmp_path / "src.py").write_text("import os\nimport sys\nx = os.path\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("import unused\nassert True\n", encoding="utf-8")
    ops = get_clean_imports_operations(tmp_path)
    assert not any(
        o.get("kind") == "remove_unused_import" and str(o.get("target_file", "")).startswith("tests/")
        for o in ops
    )


def test_get_learning_insights_returns_target_stats_and_recommendations(tmp_path: Path) -> None:
    """Learning insights should expose what-worked and recommendation blocks."""
    from eurika.storage import ProjectMemory

    memory = ProjectMemory(tmp_path)
    op = {
        "kind": "extract_block_to_helper",
        "smell_type": "deep_nesting",
        "target_file": "core.py",
    }
    memory.learning.append(
        project_root=tmp_path,
        modules=["core.py"],
        operations=[op],
        risks=[],
        verify_success=True,
    )
    memory.learning.append(
        project_root=tmp_path,
        modules=["core.py"],
        operations=[op],
        risks=[],
        verify_success=True,
    )

    out = get_learning_insights(tmp_path, top_n=3)
    what_worked = out.get("what_worked") or []
    assert what_worked
    assert what_worked[0].get("target_file") == "core.py"
    assert float(what_worked[0].get("verify_success_rate")) >= 1.0
    recs = out.get("recommendations") or {}
    assert isinstance(recs.get("whitelist_candidates"), list)


def test_get_learning_insights_includes_chat_learning_hints(tmp_path: Path) -> None:
    """Chat history should contribute review-only hints for policy/whitelist."""
    chat_dir = tmp_path / ".eurika" / "chat_history"
    chat_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {"role": "user", "content": "сохрани в src/new_a.py", "ts": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "```python\nx=1\n```\n\n[Сохранено в src/new_a.py]", "ts": "2026-01-01T00:00:01Z"},
        {"role": "user", "content": "save to src/new_a.py", "ts": "2026-01-01T00:00:02Z"},
        {"role": "assistant", "content": "```python\nx=2\n```\n\n[Сохранено в src/new_a.py]", "ts": "2026-01-01T00:00:03Z"},
        {"role": "user", "content": "удали src/missing.py", "ts": "2026-01-01T00:00:04Z"},
        {"role": "assistant", "content": "Не удалось удалить: not a file or does not exist", "ts": "2026-01-01T00:00:05Z"},
        {"role": "user", "content": "удали src/missing.py", "ts": "2026-01-01T00:00:06Z"},
        {"role": "assistant", "content": "Не удалось удалить: not a file or does not exist", "ts": "2026-01-01T00:00:07Z"},
    ]
    payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n"
    (chat_dir / "chat.jsonl").write_text(payload, encoding="utf-8")

    out = get_learning_insights(tmp_path, top_n=5)
    recs = out.get("recommendations") or {}
    chat_white = recs.get("chat_whitelist_hints") or []
    chat_review = recs.get("chat_policy_review_hints") or []
    assert any(
        item.get("intent") == "save" and item.get("target") == "src/new_a.py"
        for item in chat_white
    )
    assert any(
        item.get("intent") == "delete" and item.get("target") == "src/missing.py"
        for item in chat_review
    )


def test_get_chat_dialog_state_returns_active_and_pending(tmp_path: Path) -> None:
    """Dialog state endpoint should return normalized active/pending blocks."""
    out_empty = get_chat_dialog_state(tmp_path)
    assert out_empty.get("active_goal") == {}
    assert out_empty.get("pending_clarification") == {}
    assert out_empty.get("pending_plan") == {}
    assert out_empty.get("last_execution") == {}

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "active_goal": {"intent": "refactor", "target": "src/a.py", "source": "interpreter"},
                "pending_clarification": {"original": "сделай как лучше"},
                "pending_plan": {"intent": "refactor", "token": "abc123", "status": "pending_confirmation"},
                "last_execution": {"ok": True, "summary": "done"},
                "noise": "ignored",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = get_chat_dialog_state(tmp_path)
    assert out.get("active_goal", {}).get("intent") == "refactor"
    assert out.get("pending_clarification", {}).get("original") == "сделай как лучше"
    assert out.get("pending_plan", {}).get("token") == "abc123"
    assert out.get("last_execution", {}).get("ok") is True
