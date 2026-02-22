"""Tests for eurika agent cycle and eurika fix (product) commands."""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_fix_quiet_exit_code_success(tmp_path: Path) -> None:
    """CI: eurika fix . --quiet returns 0 when verify passes."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\n")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("")
    (proj / "tests" / "test_a.py").write_text("def test_ok(): assert True\n")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)
    result = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--quiet", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"CI: fix --quiet should exit 0 on success. stderr: {result.stderr}"


def test_run_cycle_single_entry_point() -> None:
    """run_cycle(mode) dispatches to doctor, fix, or full; unknown mode returns error."""
    from cli.orchestrator import run_cycle
    err = run_cycle(ROOT, mode="unknown")
    assert "error" in err
    assert "Unknown mode" in err["error"]


def test_run_cycle_rejects_unknown_runtime_mode() -> None:
    from cli.orchestrator import run_cycle

    err = run_cycle(ROOT, mode="doctor", runtime_mode="bad-mode")
    assert "error" in err
    assert "Unknown runtime_mode" in err["error"]


def test_eurika_orchestrator_run() -> None:
    """EurikaOrchestrator.run() delegates to run_cycle; doctor mode returns summary, patch_plan."""
    from cli.orchestrator import EurikaOrchestrator
    orch = EurikaOrchestrator()
    out = orch.run(ROOT, mode="doctor", no_llm=True)
    assert "error" not in out
    assert "summary" in out
    assert "patch_plan" in out
    assert "architect_text" in out


def test_fix_dry_run_on_self() -> None:
    """
    Product command eurika fix --dry-run: same flow as agent cycle --dry-run.
    Ensures the main entry point (fix) runs scan → arch-review → patch-plan without apply.
    """
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'fix', '--dry-run', str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f'stderr: {result.stderr}'
    assert (
        '"patch_plan"' in result.stdout
        or '"message": "Patch plan has no operations. Cycle complete."' in result.stdout
    ), f'No dry-run payload in output: {result.stdout[:500]}...'
    last_brace = result.stdout.rfind('}')
    assert last_brace >= 0
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = result.stdout[i]
        if c == '}':
            depth += 1
        elif c == '{':
            depth -= 1
            if depth == 0:
                start = i
                break
    data = json.loads(result.stdout[start:last_brace + 1])
    if 'patch_plan' in data:
        plan = data['patch_plan']
        ops = plan.get('operations', [])
        assert ops, 'Patch plan should have operations on this project'
        assert all(('target_file' in op and 'diff' in op and ('smell_type' in op) for op in ops))
    else:
        assert data.get('message') == 'Patch plan has no operations. Cycle complete.'

def test_cycle_dry_run_on_self() -> None:
    """
    Cycle --dry-run: scan → arch-review → patch-plan, no apply.
    Verifies patch_plan JSON in stdout, no files modified.
    """
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--dry-run', str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f'stderr: {result.stderr}'
    assert (
        '"patch_plan"' in result.stdout
        or '"message": "Patch plan has no operations. Cycle complete."' in result.stdout
    ), f'No dry-run payload in output: {result.stdout[:500]}...'
    last_brace = result.stdout.rfind('}')
    assert last_brace >= 0, 'No closing brace in output'
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = result.stdout[i]
        if c == '}':
            depth += 1
        elif c == '{':
            depth -= 1
            if depth == 0:
                start = i
                break
    data = json.loads(result.stdout[start:last_brace + 1])
    if 'patch_plan' in data:
        plan = data['patch_plan']
        ops = plan.get('operations', [])
        assert ops, 'Patch plan should have operations on this project'
        assert all(('target_file' in op and 'diff' in op and ('smell_type' in op) for op in ops))
    else:
        assert data.get('message') == 'Patch plan has no operations. Cycle complete.'

def test_product_cycle_dry_run() -> None:
    """eurika cycle --dry-run: scan → doctor → fix (dry-run). Full ritual in one command."""
    result = subprocess.run(
        [sys.executable, '-m', 'eurika_cli', 'cycle', '--dry-run', '--no-llm', str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, f'stderr: {result.stderr[:1000]}'
    assert "eurika cycle" in result.stderr or "patch_plan" in result.stdout


def test_multi_repo_scan(tmp_path: Path) -> None:
    """3.0.1: eurika scan accepts multiple paths and runs sequentially."""
    p1 = tmp_path / "proj1"
    p2 = tmp_path / "proj2"
    p1.mkdir()
    p2.mkdir()
    (p1 / "a.py").write_text("x = 1\n", encoding="utf-8")
    (p2 / "b.py").write_text("y = 2\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "scan", str(p1), str(p2)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Project 1/2" in result.stderr or "Project 2/2" in result.stderr
    assert (p1 / "self_map.json").exists()
    assert (p2 / "self_map.json").exists()


def test_cycle_dry_run_on_minimal_project(tmp_path: Path) -> None:
    """
    Cycle --dry-run on minimal project may return empty operations (no smells).
    Should still complete with exit 0.
    """
    proj = tmp_path / 'min'
    proj.mkdir()
    (proj / 'a.py').write_text('x = 1\n', encoding='utf-8')
    (proj / 'tests').mkdir()
    (proj / 'tests' / '__init__.py').write_text('', encoding='utf-8')
    (proj / 'tests' / 'test_a.py').write_text('def test_ok(): assert True\n', encoding='utf-8')
    (proj / 'pyproject.toml').write_text("[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--dry-run', str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f'stderr: {result.stderr}'


def _minimal_self_map(path: Path, modules: list, dependencies: dict) -> None:
    data = {
        "modules": [{"path": p, "lines": 10, "functions": [], "classes": []} for p in modules],
        "dependencies": dependencies,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_doctor_includes_knowledge_when_cache_present(tmp_path: Path) -> None:
    """
    doctor --no-llm with eurika_knowledge.json in project root: architect output includes
    Reference block from Knowledge Layer (Knowledge Layer integration).
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    _minimal_self_map(proj / "self_map.json", ["a.py"], {})
    (proj / "eurika_knowledge.json").write_text(
        json.dumps({
            "topics": {
                "python": [{"title": "PEP 701", "content": "f-strings can contain nested quotes."}],
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "doctor", "--no-llm", str(proj)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout[:800]}"
    assert "Reference" in result.stdout, "Knowledge Layer: architect should include Reference when cache has topic"
    assert "PEP 701" in result.stdout or "f-strings" in result.stdout, "Reference content from cache should appear"


def test_knowledge_topics_derived_from_summary(monkeypatch: Any) -> None:
    """_knowledge_topics_from_env_or_summary: without env, topics derived from summary (cycles, risks)."""
    monkeypatch.delenv("EURIKA_KNOWLEDGE_TOPIC", raising=False)
    from cli.core_handlers import _knowledge_topics_from_env_or_summary

    topics = _knowledge_topics_from_env_or_summary({"system": {}, "risks": []})
    assert topics == ["python", "python_3_14"]
    topics = _knowledge_topics_from_env_or_summary({"system": {"cycles": 1}, "risks": []})
    assert "python" in topics and "python_3_14" in topics and "cyclic_imports" in topics
    topics = _knowledge_topics_from_env_or_summary({"system": {}, "risks": ["god_module @ a.py"]})
    assert "python" in topics and "python_3_14" in topics and "architecture_refactor" in topics
    topics = _knowledge_topics_from_env_or_summary({"system": {}, "risks": ["long_function @ foo.py"]})
    assert "pep_8" in topics


def test_doctor_runtime_reports_degraded_mode_when_llm_disabled(tmp_path: Path) -> None:
    """Doctor reports deterministic degraded mode metadata when running with --no-llm."""
    from cli.orchestration.doctor import run_doctor_cycle

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=False)
    runtime = out.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "llm_disabled" in (runtime.get("degraded_reasons") or [])
    assert runtime.get("llm_used") is False
    assert runtime.get("use_llm") is False


def test_doctor_handles_network_unavailable_without_crash(tmp_path: Path) -> None:
    """Doctor should degrade gracefully when online knowledge fetch is unavailable."""
    import urllib.error
    from unittest.mock import patch

    from cli.orchestration.doctor import run_doctor_cycle

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    with patch(
        "eurika.knowledge.base.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network down"),
    ):
        out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=True)
    assert "error" not in out
    assert "summary" in out and "architect_text" in out
    runtime = out.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "llm_disabled" in (runtime.get("degraded_reasons") or [])


def test_doctor_suggested_policy_block(tmp_path: Path) -> None:
    """Doctor shows Suggested policy block when fix report has low apply_rate (ROADMAP 2.9.4)."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"telemetry": {"apply_rate": 0.2, "rollback_rate": 0.0}}),
        encoding="utf-8",
    )
    (tmp_path / "self_map.json").write_text(
        json.dumps({
            "modules": [{"path": "a.py", "lines": 10}],
            "dependencies": {},
            "system": {"modules": 1, "dependencies": 0, "cycles": 0},
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "doctor", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "Suggested policy" in result.stdout
    assert "EURIKA_AGENT_MAX_OPS" in result.stdout or "export" in result.stdout


def test_load_suggested_policy_for_apply(tmp_path: Path) -> None:
    """load_suggested_policy_for_apply loads from fix report when doctor report absent."""
    from cli.orchestration.doctor import load_suggested_policy_for_apply

    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"telemetry": {"apply_rate": 0.15, "rollback_rate": 0.0}}),
        encoding="utf-8",
    )
    sugg = load_suggested_policy_for_apply(tmp_path)
    assert sugg.get("EURIKA_AGENT_MAX_OPS") == "40"


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
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--quiet', str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=90)
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
        cwd=ROOT, capture_output=True, text=True, timeout=60,
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

    r1 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    r2 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--no-clean-imports", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
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

    r1 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    r2 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--no-code-smells", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = _parse_final_json(r1.stdout)
    d2 = _parse_final_json(r2.stdout)
    ops1 = d1.get("patch_plan", {}).get("operations", []) if d1 else []
    ops2 = d2.get("patch_plan", {}).get("operations", []) if d2 else []
    code_smell_kinds = {"extract_block_to_helper", "extract_nested_function", "refactor_code_smell"}
    code_smell1 = [o for o in ops1 if o.get("kind") in code_smell_kinds]
    code_smell2 = [o for o in ops2 if o.get("kind") in code_smell_kinds]
    assert len(code_smell1) >= 1, "without --no-code-smells should have code-smell ops (e.g. extract_block_to_helper for deep_nesting)"
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
        patch("cli.orchestrator._fix_cycle_deps", return_value={"run_scan": lambda *_args, **_kwargs: True}),
        patch("cli.orchestrator._prepare_fix_cycle_operations", return_value=(early, fake_result, patch_plan, ops)),
        patch("cli.orchestrator._select_hybrid_operations", return_value=([], ops)),
    ):
        out = run_cycle(ROOT, mode="fix", runtime_mode="hybrid", quiet=True, non_interactive=False)
    report = out.get("report", {})
    telemetry = report.get("telemetry", {})
    safety = report.get("safety_gates", {})
    assert report.get("message") == "All operations rejected by user/policy. Cycle complete."
    assert telemetry.get("operations_total") == 1
    assert telemetry.get("skipped_count") == 1
    assert telemetry.get("no_op_rate") == 1.0
    assert safety.get("verify_required") is False
    assert safety.get("verify_passed") is None


def test_run_doctor_cycle_wrapper_delegates_to_orchestration_module() -> None:
    """Thin orchestrator wrapper should delegate doctor-cycle execution."""
    from cli.orchestrator import run_doctor_cycle

    expected = {"ok": True}
    with patch("cli.orchestrator._doctor_run_doctor_cycle", return_value=expected) as mock_doctor:
        out = run_doctor_cycle(ROOT, window=7, no_llm=True)
    assert out == expected
    mock_doctor.assert_called_once_with(ROOT, window=7, no_llm=True, online=False)


def test_run_full_cycle_wrapper_delegates_to_orchestration_module() -> None:
    """Thin orchestrator wrapper should delegate full-cycle wiring."""
    from cli.orchestrator import run_full_cycle

    expected = {"ok": True}
    with patch("cli.orchestrator._full_run_full_cycle", return_value=expected) as mock_full:
        out = run_full_cycle(ROOT, quiet=True, no_llm=True)
    assert out == expected
    assert mock_full.call_count == 1
    kwargs = mock_full.call_args.kwargs
    assert callable(kwargs.get("run_doctor_cycle_fn"))
    assert callable(kwargs.get("run_fix_cycle_fn"))


def test_full_cycle_propagates_doctor_runtime_to_fix_report() -> None:
    """run_full_cycle should copy doctor runtime metadata into fix report."""
    from cli.orchestration.full_cycle import run_full_cycle

    doctor_out = {
        "summary": {"system": {}, "risks": []},
        "history": {"evolution_report": ""},
        "architect_text": "ok",
        "runtime": {
            "degraded_mode": True,
            "degraded_reasons": ["llm_disabled"],
            "llm_used": False,
            "use_llm": False,
        },
    }
    fix_out = {
        "return_code": 0,
        "report": {},
        "operations": [],
        "modified": [],
        "verify_success": True,
        "agent_result": None,
    }
    with patch("runtime_scan.run_scan", return_value=0):
        out = run_full_cycle(
            ROOT,
            quiet=True,
            no_llm=True,
            run_doctor_cycle_fn=lambda *_args, **_kwargs: doctor_out,
            run_fix_cycle_fn=lambda *_args, **_kwargs: dict(fix_out),
        )
    runtime = (out.get("report") or {}).get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "llm_disabled" in (runtime.get("degraded_reasons") or [])
    assert runtime.get("source") == "doctor"


def test_append_fix_cycle_memory_tolerates_memory_write_error(tmp_path: Path) -> None:
    """Memory write failures must not break fix cycle flow (degraded but deterministic)."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from cli.orchestration.apply_stage import append_fix_cycle_memory

    result = SimpleNamespace(output={"summary": {"risks": []}})
    operations = [{"target_file": "a.py", "kind": "remove_unused_import"}]
    report = {"modified": ["a.py"], "run_id": "r1", "verify_duration_ms": 10}
    with patch("eurika.storage.ProjectMemory", side_effect=OSError("disk full")):
        append_fix_cycle_memory(tmp_path, result, operations, report, verify_success=True)


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


def test_prepare_fix_cycle_operations_wrapper_delegates() -> None:
    """Compatibility wrapper for prepare-stage should delegate unchanged."""
    from cli.orchestrator import _prepare_fix_cycle_operations

    expected = ({"early": True}, None, None, [])
    with patch("cli.orchestrator._prepare_prepare_fix_cycle_operations", return_value=expected) as mock_prepare:
        out = _prepare_fix_cycle_operations(
            ROOT,
            runtime_mode="assist",
            session_id=None,
            window=5,
            quiet=True,
            skip_scan=False,
            no_clean_imports=False,
            no_code_smells=False,
            run_scan=lambda *_args, **_kwargs: 0,
        )
    assert out == expected
    assert mock_prepare.call_count == 1


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
    from eurika.storage import SessionMemory, operation_key
    from cli.orchestration.prepare import apply_campaign_memory

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


def test_handle_report_snapshot_delegates_to_format(capsys: Any, tmp_path: Path) -> None:
    """report-snapshot handler delegates to format_report_snapshot (3.1-arch.5 isolation)."""
    from unittest.mock import patch
    from types import SimpleNamespace

    args = SimpleNamespace(path=tmp_path)
    with patch("report.report_snapshot.format_report_snapshot", return_value="DELEGATED_OUTPUT") as mock_fmt:
        from cli.core_handlers import handle_report_snapshot

        code = handle_report_snapshot(args)
    assert code == 0
    assert mock_fmt.called
    assert mock_fmt.call_args[0][0] == tmp_path
    out, _ = capsys.readouterr()
    assert "DELEGATED_OUTPUT" in out


def test_report_snapshot_empty_project(tmp_path: Path) -> None:
    """report-snapshot outputs fallback when no artifacts exist."""
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "No eurika_doctor_report" in result.stdout or "eurika_fix_report" in result.stdout


def test_report_snapshot_with_fix_report(tmp_path: Path) -> None:
    """report-snapshot reads eurika_fix_report.json when present."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"modified": ["a.py"], "skipped": [], "verify": {"success": True}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "## 1. Fix" in result.stdout
    assert "modified" in result.stdout
    assert "1" in result.stdout


def test_report_snapshot_invalid_fix_report_shows_warning(tmp_path: Path) -> None:
    """report-snapshot should not crash on invalid eurika_fix_report.json and should warn."""
    (tmp_path / "eurika_fix_report.json").write_text("{broken json", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "No eurika_doctor_report" in result.stdout or "Run doctor/fix first" in result.stdout


def test_report_snapshot_invalid_doctor_report_still_shows_fix_and_warning(tmp_path: Path) -> None:
    """report-snapshot should keep valid fix section when doctor report is invalid."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"modified": ["a.py"], "skipped": [], "verify": {"success": True}}),
        encoding="utf-8",
    )
    (tmp_path / "eurika_doctor_report.json").write_text("{oops", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "## 1. Fix" in result.stdout
    assert "Snapshot warnings" in result.stdout
    assert "invalid JSON in eurika_doctor_report.json" in result.stdout


def test_attach_fix_telemetry_median_verify_time(tmp_path: Path) -> None:
    """attach_fix_telemetry adds median_verify_time_ms when path has patch events (ROADMAP 2.7.8)."""
    from eurika.storage import ProjectMemory
    from cli.orchestration.apply_stage import attach_fix_telemetry

    memory = ProjectMemory(tmp_path)
    memory.events.append_event(
        "patch",
        {"operations_count": 1},
        {"modified": ["a.py"], "verify_success": True, "verify_duration_ms": 100},
        result=True,
    )
    memory.events.append_event(
        "patch",
        {"operations_count": 1},
        {"modified": ["b.py"], "verify_success": True, "verify_duration_ms": 200},
        result=True,
    )
    report = {
        "modified": ["c.py"],
        "skipped": [],
        "verify": {"success": True},
        "verify_duration_ms": 300,
    }
    attach_fix_telemetry(report, [{"target_file": "c.py"}], tmp_path)
    assert "median_verify_time_ms" in report.get("telemetry", {})
    # median of [100, 200, 300] = 200
    assert report["telemetry"]["median_verify_time_ms"] == 200


def test_report_snapshot_telemetry_block(tmp_path: Path) -> None:
    """report-snapshot includes telemetry subsection when fix has telemetry (ROADMAP 2.7.8)."""
    fix_report = {
        "modified": ["a.py"],
        "skipped": [],
        "verify": {"success": True},
        "telemetry": {"apply_rate": 1.0, "no_op_rate": 0.0, "rollback_rate": 0.0, "verify_duration_ms": 150},
    }
    (tmp_path / "eurika_fix_report.json").write_text(json.dumps(fix_report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "telemetry" in result.stdout
    assert "1.0" in result.stdout or "apply_rate" in result.stdout


def test_run_fix_cycle_impl_uses_apply_stage_facade() -> None:
    """run_cycle(fix) should wire through delegated apply-stage builders."""
    from cli.orchestrator import run_cycle

    fake_result = MagicMock()
    fake_result.output = {"policy_decisions": []}
    ops = [{"target_file": "a.py", "kind": "split_module", "explainability": {"risk": "low"}}]
    patch_plan = {"operations": ops}
    deps = {
        "run_scan": lambda *_args, **_kwargs: True,
        "BACKUP_DIR": ".eurika_backups",
        "apply_and_verify": object(),
        "build_snapshot_from_self_map": object(),
        "diff_architecture_snapshots": object(),
        "metrics_from_graph": object(),
        "rollback_patch": object(),
    }
    with (
        patch("cli.orchestrator._fix_cycle_deps", return_value=deps),
        patch("cli.orchestrator._prepare_fix_cycle_operations", return_value=(None, fake_result, patch_plan, ops)),
        patch("cli.orchestrator._select_hybrid_operations", return_value=(ops, [])),
        patch("cli.orchestrator._apply_execute_fix_apply_stage", return_value=({"verify": {"success": True}}, ["a.py"], True)) as mock_apply,
        patch("cli.orchestrator._apply_build_fix_cycle_result", return_value={"ok": True}) as mock_build,
    ):
        out = run_cycle(ROOT, mode="fix", quiet=True)
    assert out == {"ok": True}
    assert mock_apply.call_count == 1
    assert mock_build.call_count == 1