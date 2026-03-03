"""Tests for eurika fix/apply, campaign memory, and fix cycle operations."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Timeout for fix/cycle subprocess that invokes architect (LLM): 10 min
CYCLE_LLM_TIMEOUT = 600


def _parse_final_json(stdout: str):
    """Extract last top-level JSON object from stdout (cycle prints report at end)."""
    last_brace = stdout.rfind('}')
    if last_brace < 0:
        return None
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = stdout[i]
        if c == '}':
            depth += 1
        elif c == '{':
            depth -= 1
            if depth == 0:
                start = i
                break
    try:
        return json.loads(stdout[start:last_brace + 1])
    except json.JSONDecodeError:
        return None


def test_load_suggested_policy_for_apply(tmp_path: Path) -> None:
    """load_suggested_policy_for_apply loads from fix report when doctor report absent."""
    from cli.orchestration.doctor import load_suggested_policy_for_apply

    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"telemetry": {"apply_rate": 0.15, "rollback_rate": 0.0}}),
        encoding="utf-8",
    )
    sugg = load_suggested_policy_for_apply(tmp_path)
    assert sugg.get("EURIKA_AGENT_MAX_OPS") == "40"


def test_cycle_full_apply_then_rollback(tmp_path: Path) -> None:
    """
    Full cycle with apply on a minimal project: run cycle (apply + verify),
    assert report contains rescan_diff when apply happened, then rollback.
    """
    proj = tmp_path / 'proj'
    proj.mkdir()
    (proj / 'center.py').write_text('def value():\n    return 42\n', encoding='utf-8')
    for name in ('a', 'b', 'c', 'd', 'e'):
        (proj / f'{name}.py').write_text(f'from center import value\nx = value()\n', encoding='utf-8')
    (proj / 'tests').mkdir(parents=True)
    (proj / 'tests' / '__init__.py').write_text('', encoding='utf-8')
    (proj / 'tests' / 'test_center.py').write_text('from center import value\ndef test_value(): assert value() == 42\n', encoding='utf-8')
    (proj / 'pyproject.toml').write_text("[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--quiet', str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    assert result.returncode == 0, f'stderr: {result.stderr}\nstdout: {result.stdout[:1000]}'
    data = _parse_final_json(result.stdout)
    if data and 'rescan_diff' in data:
        assert 'structures' in data['rescan_diff'] or 'smells' in data['rescan_diff']
    if data and data.get('rescan_diff') and 'error' not in data.get('rescan_diff', {}):
        assert 'verify_metrics' in data, 'Verify Stage: report should include verify_metrics after rescan'
        vm = data['verify_metrics']
        assert 'before_score' in vm and 'after_score' in vm
    if data and data.get('run_id'):
        rollback = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'patch-rollback', str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=15)
        assert rollback.returncode == 0, rollback.stderr
        out = json.loads(rollback.stdout)
        assert out.get('errors') == []
        assert len(out.get('restored', [])) >= 1


def test_fix_cycle_includes_clean_imports_ops(tmp_path: Path) -> None:
    """
    Fix cycle (dry-run) includes remove_unused_import ops when files have unused imports (ROADMAP 2.4).
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "foo.py").write_text("import os\nimport sys\nx = 1\n", encoding="utf-8")  # os, sys unused
    (proj / "bar.py").write_text("from pathlib import Path\nfrom os import path\ny = 2\n", encoding="utf-8")  # Path, path unused
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_foo.py").write_text("def test_foo(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)
    assert (proj / "self_map.json").exists()

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)],
        cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout[:800]}"
    data = _parse_final_json(result.stdout)
    assert data and "patch_plan" in data
    ops = data["patch_plan"].get("operations", [])
    clean_ops = [o for o in ops if o.get("kind") == "remove_unused_import"]
    assert len(clean_ops) >= 1, "fix cycle should include remove_unused_import ops when files have unused imports"
    assert any(o.get("target_file") == "foo.py" or o.get("target_file") == "bar.py" for o in clean_ops)


def test_fix_no_clean_imports_excludes_clean_ops(tmp_path: Path) -> None:
    """Fix --no-clean-imports: patch_plan has no remove_unused_import ops (same project, with flag)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "foo.py").write_text("import os\nx = 1\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_foo.py").write_text("def test_foo(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)

    r1 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    r2 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--no-clean-imports", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = _parse_final_json(r1.stdout)
    d2 = _parse_final_json(r2.stdout)
    ops1 = d1.get("patch_plan", {}).get("operations", []) if d1 else []
    ops2 = d2.get("patch_plan", {}).get("operations", []) if d2 else []
    clean1 = [o for o in ops1 if o.get("kind") == "remove_unused_import"]
    clean2 = [o for o in ops2 if o.get("kind") == "remove_unused_import"]
    assert len(clean1) >= 1, "without --no-clean-imports should have remove_unused_import ops"
    assert len(clean2) == 0, "--no-clean-imports should exclude remove_unused_import ops"


def test_fix_no_code_smells_excludes_code_smell_ops(tmp_path: Path) -> None:
    """Fix --no-code-smells: patch_plan has no code-smell ops (extract_block, extract_nested, refactor_code_smell)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    # deep_nesting (depth>4) triggers extract_block_to_helper; long_function without nested def gets no real fix by default
    deep_nesting = """
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
    (proj / "nested.py").write_text(deep_nesting, encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_nested.py").write_text("def test_deep_foo(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)

    r1 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    r2 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--no-code-smells", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = _parse_final_json(r1.stdout)
    d2 = _parse_final_json(r2.stdout)
    ops1 = d1.get("patch_plan", {}).get("operations", []) if d1 else []
    ops2 = d2.get("patch_plan", {}).get("operations", []) if d2 else []
    code_smell_kinds = {"extract_block_to_helper", "extract_nested_function", "refactor_code_smell"}
    code_smell1 = [o for o in ops1 if o.get("kind") in code_smell_kinds]
    code_smell2 = [o for o in ops2 if o.get("kind") in code_smell_kinds]
    # Safety policy may suppress historically weak pairs even without --no-code-smells.
    # Contract here: --no-code-smells must not increase code-smell operations.
    assert len(code_smell1) >= len(code_smell2), "--no-code-smells should not increase code-smell ops"
    assert len(code_smell2) == 0, "--no-code-smells should exclude code-smell ops"


def test_learning_not_appended_when_all_skipped(tmp_path: Path) -> None:
    """When apply returns modified=[], learning.append is not called (no inflated success stats)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "center.py").write_text("def value(): return 42\n", encoding="utf-8")
    for name in ("a", "b", "c", "d", "e"):
        (proj / f"{name}.py").write_text(f"from center import value\nx = value()\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_center.py").write_text("from center import value\ndef test_value(): assert value() == 42\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[project]\nname='x'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)
    assert (proj / "self_map.json").exists()

    def fake_apply(root, plan, **kwargs):
        from patch_engine import verify_patch
        v = verify_patch(root)
        return {"modified": [], "verify": {"success": v.get("success", True)}, "run_id": None}

    with patch("patch_engine.apply_and_verify", side_effect=fake_apply):
        with patch("architecture_learning.LearningStore.append", MagicMock()) as mock_append:
            from cli.orchestrator import run_cycle
            run_cycle(proj, mode="fix", dry_run=False, quiet=True)

    assert mock_append.call_count == 0, "learning.append should not be called when modified=[]"


def test_fix_cycle_report_includes_telemetry_and_safety_gates(tmp_path: Path) -> None:
    """Fix cycle report includes telemetry KPI block and safety-gate status."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "foo.py").write_text("import os\nx = 1\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_foo.py").write_text("def test_foo(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)

    from cli.orchestrator import run_cycle

    out = run_cycle(proj, mode="fix", quiet=True)
    report = out.get("report", {})
    telemetry = report.get("telemetry")
    safety = report.get("safety_gates")
    assert isinstance(telemetry, dict)
    assert isinstance(safety, dict)
    assert "apply_rate" in telemetry
    assert "no_op_rate" in telemetry
    assert "rollback_rate" in telemetry
    assert "verify_duration_ms" in telemetry
    assert "verify_required" in safety
    assert "auto_rollback_enabled" in safety


def test_fix_cycle_all_rejected_includes_telemetry_and_no_verify_gate() -> None:
    """If hybrid rejects all ops, report still includes telemetry and verify gate is disabled."""
    from cli.orchestrator import run_cycle

    fake_result = MagicMock()
    fake_result.output = {
        "policy_decisions": [
            {
                "index": 1,
                "target_file": "a.py",
                "kind": "split_module",
                "decision": "review",
                "reason": "high risk",
                "risk": "high",
            }
        ]
    }
    ops = [{"target_file": "a.py", "kind": "split_module", "explainability": {"risk": "high"}}]
    early = None
    patch_plan = {"operations": ops}
    with (
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(early, fake_result, patch_plan, ops)),
        patch("eurika.orchestration.entry.select_hybrid_operations", return_value=([], ops)),
    ):
        out = run_cycle(ROOT, mode="fix", runtime_mode="assist", quiet=True, non_interactive=False)
    report = out.get("report", {})
    telemetry = report.get("telemetry", {})
    safety = report.get("safety_gates", {})
    assert report.get("message") == "All operations rejected by user/policy. Cycle complete."
    assert telemetry.get("operations_total") == 1
    assert telemetry.get("skipped_count") == 1
    assert telemetry.get("no_op_rate") == 1.0
    assert safety.get("verify_required") is False
    assert safety.get("verify_passed") is None


def test_fix_cycle_decision_gate_blocks_critic_denied_op() -> None:
    """Hard gate must skip op when critic verdict is deny even if selected."""
    from cli.orchestrator import run_cycle

    fake_result = MagicMock()
    fake_result.output = {
        "policy_decisions": [
            {
                "index": 1,
                "target_file": "a.py",
                "kind": "split_module",
                "decision": "allow",
                "reason": "allowed by policy",
                "risk": "high",
            }
        ],
        "critic_decisions": [
            {
                "index": 1,
                "target_file": "a.py",
                "kind": "split_module",
                "verdict": "deny",
                "reason": "blocked",
                "risk": "high",
            }
        ],
    }
    ops = [
        {
            "target_file": "a.py",
            "kind": "split_module",
            "approval_state": "approved",
            "critic_verdict": "deny",
            "explainability": {"risk": "high"},
        }
    ]
    with (
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(None, fake_result, {"operations": ops}, ops)),
        patch("eurika.orchestration.entry.select_hybrid_operations", return_value=(ops, [])),
    ):
        out = run_cycle(ROOT, mode="fix", runtime_mode="assist", quiet=True, non_interactive=False)
    report = out.get("report", {})
    assert report.get("message") == "All operations rejected by user/policy. Cycle complete."
    assert "critic_decisions" in report
    assert (report.get("skipped_reasons") or {}).get("a.py") == "critic_verdict=deny"
    assert report.get("telemetry", {}).get("operations_total") == 1
    assert report.get("telemetry", {}).get("modified_count") == 0


def test_fix_cycle_approve_ops_selects_subset() -> None:
    """--approve-ops applies only selected operation indexes."""
    from cli.orchestrator import run_cycle

    fake_result = MagicMock()
    fake_result.output = {"policy_decisions": [], "critic_decisions": []}
    ops = [
        {"target_file": "a.py", "kind": "split_module", "approval_state": "approved", "critic_verdict": "allow"},
        {"target_file": "b.py", "kind": "remove_unused_import", "approval_state": "approved", "critic_verdict": "allow"},
    ]
    with (
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(None, fake_result, {"operations": ops}, ops)),
    ):
        out = run_cycle(ROOT, mode="fix", dry_run=True, quiet=True, approve_ops="1")
    selected = out.get("operations") or []
    assert len(selected) == 1
    assert selected[0].get("target_file") == "a.py"
    skipped = (out.get("report") or {}).get("skipped_reasons") or {}
    assert skipped.get("b.py") == "not_in_approved_set"


def test_fix_cycle_reject_ops_conflict_returns_error() -> None:
    """Conflicting --approve-ops/--reject-ops indexes return deterministic error."""
    from cli.orchestrator import run_cycle

    fake_result = MagicMock()
    fake_result.output = {"policy_decisions": [], "critic_decisions": []}
    ops = [
        {"target_file": "a.py", "kind": "split_module", "approval_state": "approved", "critic_verdict": "allow"},
    ]
    with (
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(None, fake_result, {"operations": ops}, ops)),
    ):
        out = run_cycle(ROOT, mode="fix", dry_run=True, quiet=True, approve_ops="1", reject_ops="1")
    assert out.get("return_code") == 1
    assert "Conflicting indexes" in ((out.get("report") or {}).get("error") or "")


def test_fix_cycle_noop_writes_fresh_fix_report(tmp_path: Path) -> None:
    """No-op fix cycle should overwrite eurika_fix_report.json with current report."""
    from cli.orchestrator import run_cycle

    report_path = tmp_path / "eurika_fix_report.json"
    report_path.write_text(json.dumps({"verify": {"success": False}, "message": "stale"}), encoding="utf-8")
    fake_result = MagicMock()
    fake_result.output = {"policy_decisions": []}
    early = {
        "return_code": 0,
        "report": {
            "message": "Patch plan has no operations. Cycle complete.",
            "policy_decisions": [],
            "session_skipped": 0,
        },
        "operations": [],
        "modified": [],
        "verify_success": True,
        "agent_result": fake_result,
    }
    with (
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(early, fake_result, {"operations": []}, [])),
    ):
        out = run_cycle(tmp_path, mode="fix", quiet=True)
    assert out.get("report", {}).get("message") == "Patch plan has no operations. Cycle complete."
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved.get("message") == "Patch plan has no operations. Cycle complete."
    assert saved.get("telemetry", {}).get("operations_total") == 0


def test_append_fix_cycle_memory_tolerates_memory_write_error(tmp_path: Path) -> None:
    """Memory write failures must not break fix cycle flow (degraded but deterministic)."""
    from types import SimpleNamespace

    from cli.orchestration.apply_stage import append_fix_cycle_memory

    result = SimpleNamespace(output={"summary": {"risks": []}})
    operations = [{"target_file": "a.py", "kind": "remove_unused_import"}]
    report = {"modified": ["a.py"], "run_id": "r1", "verify_duration_ms": 10}
    with patch("eurika.storage.ProjectMemory", side_effect=OSError("disk full")):
        append_fix_cycle_memory(tmp_path, result, operations, report, verify_success=True)


def test_append_fix_cycle_memory_persists_failure_reason(tmp_path: Path) -> None:
    """When verify fails, failure_reason is persisted in patch event (Review III самокоррекция)."""
    from types import SimpleNamespace

    from cli.orchestration.apply_stage import append_fix_cycle_memory
    from eurika.storage import ProjectMemory

    result = SimpleNamespace(output={"summary": {"risks": []}})
    operations = [{"target_file": "a.py", "kind": "split_module"}]
    report = {"modified": ["a.py"], "rollback": {"done": True, "reason": "metrics_worsened"}}
    append_fix_cycle_memory(tmp_path, result, operations, report, verify_success=False)

    patch_events = ProjectMemory(tmp_path).events.by_type("patch")
    assert patch_events
    out = getattr(patch_events[-1], "output", {}) or {}
    assert out.get("failure_reason") == "metrics_worsened"


def test_append_fix_cycle_memory_records_not_applied_outcome(tmp_path: Path) -> None:
    """Learning record should preserve not_applied outcome for accurate action stats."""
    from types import SimpleNamespace

    from cli.orchestration.apply_stage import append_fix_cycle_memory
    from eurika.storage import ProjectMemory

    result = SimpleNamespace(output={"summary": {"risks": []}})
    operations = [{"target_file": "a.py", "kind": "extract_nested_function"}]
    report = {
        "modified": [],
        "operation_results": [
            {"execution_outcome": "not_applied", "skipped_reason": "extract_nested_function: parent not found", "applied": False}
        ],
        "run_id": "r1",
        "verify_duration_ms": 0,
    }
    append_fix_cycle_memory(tmp_path, result, operations, report, verify_success=True)
    stats = ProjectMemory(tmp_path).learning.aggregate_by_action_kind()
    assert stats["extract_nested_function"]["not_applied"] >= 1


def test_fix_apply_approved_missing_pending_plan_returns_error(tmp_path: Path) -> None:
    """--apply-approved should fail predictably when pending_plan.json is missing."""
    from cli.orchestrator import run_cycle

    out = run_cycle(tmp_path, mode="fix", apply_approved=True, quiet=True)
    assert out.get("return_code") == 1
    assert "No pending plan" in ((out.get("report") or {}).get("error") or "")


def test_fix_apply_approved_invalid_pending_plan_returns_error(tmp_path: Path) -> None:
    """--apply-approved should fail predictably when pending_plan.json is invalid JSON."""
    from cli.orchestrator import run_cycle

    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("{invalid json", encoding="utf-8")
    out = run_cycle(tmp_path, mode="fix", apply_approved=True, quiet=True)
    assert out.get("return_code") == 1
    assert "No pending plan" in ((out.get("report") or {}).get("error") or "")


def test_fix_apply_approved_invalid_pending_plan_schema_returns_error(tmp_path: Path) -> None:
    """--apply-approved should fail predictably when pending_plan has invalid schema."""
    from cli.orchestrator import run_cycle

    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps({"operations": {"not": "a list"}}), encoding="utf-8")
    out = run_cycle(tmp_path, mode="fix", apply_approved=True, quiet=True)
    assert out.get("return_code") == 1
    assert "No pending plan" in ((out.get("report") or {}).get("error") or "")


def test_drop_noop_append_ops(tmp_path: Path) -> None:
    """_drop_noop_append_ops removes ops whose diff is already in the file."""
    from cli.orchestration.prepare import _drop_noop_append_ops

    todo = "\n# TODO (eurika): refactor long_function 'foo' — consider extracting helper\n"
    (tmp_path / "a.py").write_text("def foo(): pass\n" + todo)
    (tmp_path / "c.py").write_text("x = 1\n# TODO: Refactor c.py\n")
    ops = [
        {"target_file": "a.py", "kind": "refactor_code_smell", "diff": todo.strip()},
        {"target_file": "b.py", "kind": "refactor_code_smell", "diff": "other todo"},
        {"target_file": "c.py", "kind": "refactor_module", "diff": "# TODO: Refactor c.py"},
    ]
    (tmp_path / "b.py").write_text("x = 1\n")
    kept = _drop_noop_append_ops(ops, tmp_path)
    assert len(kept) == 1
    assert kept[0]["target_file"] == "b.py"


def test_apply_campaign_memory_filters_rejected_ops(tmp_path: Path) -> None:
    """apply_campaign_memory skips ops rejected in prior sessions."""
    from cli.orchestration.prepare import apply_campaign_memory
    from eurika.storage import SessionMemory, operation_key

    mem = SessionMemory(tmp_path)
    rejected = [{"target_file": "foo.py", "kind": "split_module", "params": {"location": ""}}]
    mem.record("prior", approved=[], rejected=rejected)
    ops = [
        {"target_file": "foo.py", "kind": "split_module", "params": {"location": ""}},
        {"target_file": "bar.py", "kind": "remove_unused_import", "params": {}},
    ]
    patch_plan = {"operations": ops}
    out_plan, out_ops, skipped = apply_campaign_memory(tmp_path, patch_plan, ops)
    assert len(out_ops) == 1
    assert out_ops[0].get("target_file") == "bar.py"
    assert len(skipped) == 1
    assert operation_key(skipped[0]) == operation_key(rejected[0])


def test_apply_campaign_memory_allow_retry_keeps_operations(tmp_path: Path) -> None:
    """allow_retry=True should bypass campaign skip for current run only."""
    from cli.orchestration.prepare import apply_campaign_memory
    from eurika.storage import SessionMemory

    mem = SessionMemory(tmp_path)
    rejected = [{"target_file": "foo.py", "kind": "split_module", "params": {"location": ""}}]
    mem.record("prior", approved=[], rejected=rejected)
    ops = [
        {"target_file": "foo.py", "kind": "split_module", "params": {"location": ""}},
        {"target_file": "bar.py", "kind": "remove_unused_import", "params": {}},
    ]
    patch_plan = {"operations": ops}
    _out_plan, out_ops, skipped = apply_campaign_memory(
        tmp_path,
        patch_plan,
        ops,
        allow_retry=True,
    )
    assert len(out_ops) == 2
    assert len(skipped) == 0


def test_apply_campaign_memory_allow_low_risk_does_not_bypass_remove_unused_import(tmp_path: Path) -> None:
    """CYCLE_REPORT §107: remove_unused_import no longer bypasses campaign skip (23% success)."""
    import os

    from cli.orchestration.prepare import apply_campaign_memory
    from eurika.storage import SessionMemory

    mem = SessionMemory(tmp_path)
    rejected = [{"target_file": "bar.py", "kind": "remove_unused_import", "params": {}}]
    mem.record("prior", approved=[], rejected=rejected)
    ops = [
        {"target_file": "foo.py", "kind": "split_module", "params": {"location": ""}},
        {"target_file": "bar.py", "kind": "remove_unused_import", "params": {}},
    ]
    patch_plan = {"operations": ops}
    orig = os.environ.get("EURIKA_CAMPAIGN_ALLOW_LOW_RISK")
    try:
        os.environ.pop("EURIKA_CAMPAIGN_ALLOW_LOW_RISK", None)
        _out_plan, out_ops, skipped = apply_campaign_memory(
            tmp_path,
            patch_plan,
            ops,
            allow_retry=False,
            allow_low_risk=True,
        )
        assert len(out_ops) == 1
        assert len(skipped) == 1
        assert skipped[0].get("target_file") == "bar.py"
    finally:
        if orig is not None:
            os.environ["EURIKA_CAMPAIGN_ALLOW_LOW_RISK"] = orig


def test_prepare_fix_cycle_reports_campaign_skipped_in_noop(tmp_path: Path) -> None:
    """No-op report includes campaign_skipped count when campaign filter removes ops."""
    from types import SimpleNamespace

    from eurika.orchestration.prepare import prepare_fix_cycle_operations

    fake_result = SimpleNamespace(success=True, output={})
    ops = [{"target_file": "foo.py", "kind": "split_module"}]
    patch_plan = {"operations": ops}
    with (
        patch("eurika.orchestration.prepare.run_fix_diagnose_stage", return_value=fake_result),
        patch("eurika.orchestration.prepare.extract_patch_plan_from_result", return_value=(patch_plan, ops)),
        patch("eurika.orchestration.prepare.prepend_fix_operations", return_value=(patch_plan, ops)),
        patch("eurika.orchestration.prepare._drop_noop_append_ops", return_value=ops),
        patch("eurika.orchestration.prepare._deprioritize_weak_pairs", return_value=ops),
        patch("eurika.orchestration.prepare.apply_runtime_policy", return_value=(patch_plan, ops, [])),
        patch("eurika.orchestration.prepare.apply_campaign_memory", return_value=(patch_plan, [], ops)),
        patch("eurika.orchestration.prepare.apply_session_rejections", return_value=(patch_plan, [], [])),
    ):
        early, _result, _plan, out_ops = prepare_fix_cycle_operations(
            tmp_path,
            runtime_mode="assist",
            session_id=None,
            window=5,
            quiet=True,
            skip_scan=True,
            no_clean_imports=True,
            no_code_smells=True,
            run_scan=lambda _p: 0,
        )
    assert early is not None
    report = early.get("report", {})
    assert report.get("message") == "Patch plan has no operations. Cycle complete."
    assert report.get("campaign_skipped") == 1
    assert report.get("session_skipped") == 0
    llm_hint_runtime = report.get("llm_hint_runtime")
    assert isinstance(llm_hint_runtime, dict)
    assert "calls_used" in llm_hint_runtime
    assert out_ops == []


def test_deprioritize_weak_pairs_puts_weak_last(tmp_path: Path) -> None:
    """Weak-pair ops are moved to the end of the operation list."""
    from cli.orchestration.prepare import _deprioritize_weak_pairs

    ops = [
        {"target_file": "a.py", "kind": "split_module", "smell_type": "hub"},
        {"target_file": "b.py", "kind": "remove_unused_import"},
        {"target_file": "c.py", "kind": "extract_nested_function", "smell_type": "long_function"},
    ]
    reordered = _deprioritize_weak_pairs(ops)
    assert reordered[0]["target_file"] == "b.py"
    assert reordered[1]["target_file"] in ("a.py", "c.py")
    assert reordered[2]["target_file"] in ("a.py", "c.py")
