"""Tests for eurika agent cycle and eurika fix (product) commands."""
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
    result = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--quiet", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
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
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'fix', '--dry-run', str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
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
        assert isinstance(ops, list)
        if ops:
            assert all(('target_file' in op and 'diff' in op and ('smell_type' in op) for op in ops))
    else:
        assert data.get('message') == 'Patch plan has no operations. Cycle complete.'

def test_cycle_dry_run_on_self() -> None:
    """
    Cycle --dry-run: scan → arch-review → patch-plan, no apply.
    Verifies patch_plan JSON in stdout, no files modified.
    """
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--dry-run', str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
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
        assert isinstance(ops, list)
        if ops:
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


def test_multi_repo_fix_aggregated_report(tmp_path: Path) -> None:
    """3.0.1: eurika fix [path1 path2] writes eurika_fix_report_aggregated.json."""
    p1 = tmp_path / "proj1"
    p2 = tmp_path / "proj2"
    p1.mkdir()
    p2.mkdir()
    for proj in (p1, p2):
        (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
        (proj / "tests").mkdir()
        (proj / "tests" / "__init__.py").write_text("")
        (proj / "tests" / "test_a.py").write_text("def test_ok(): assert True\n")
        (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--quiet", str(p1), str(p2)],
        cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    agg_path = p1 / "eurika_fix_report_aggregated.json"
    assert agg_path.exists(), "eurika_fix_report_aggregated.json should be written to first path"
    data = json.loads(agg_path.read_text(encoding="utf-8"))
    assert data.get("aggregate", {}).get("total_projects") == 2
    assert len(data.get("projects", [])) == 2


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
    result = subprocess.run([sys.executable, '-m', 'eurika_cli', 'agent', 'cycle', '--dry-run', str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=CYCLE_LLM_TIMEOUT)
    assert result.returncode == 0, f'stderr: {result.stderr}'


def test_run_doctor_cycle_wrapper_delegates_to_orchestration_module() -> None:
    """Thin orchestrator wrapper should delegate doctor-cycle execution."""
    from cli.orchestrator import run_doctor_cycle

    expected = {"ok": True}
    with patch("eurika.orchestration.entry._run_doctor_cycle", return_value=expected) as mock_doctor:
        out = run_doctor_cycle(ROOT, window=7, no_llm=True)
    assert out == expected
    mock_doctor.assert_called_once_with(ROOT, window=7, no_llm=True, online=False, quiet=False)


def test_run_full_cycle_wrapper_delegates_to_orchestration_module() -> None:
    """Thin orchestrator wrapper should delegate full-cycle wiring."""
    from cli.orchestrator import run_full_cycle

    expected = {"ok": True}
    with patch("eurika.orchestration.entry._run_full_cycle_impl", return_value=expected) as mock_full:
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


def test_prepare_fix_cycle_operations_wrapper_delegates() -> None:
    """Compatibility wrapper for prepare-stage should delegate unchanged."""
    from eurika.orchestration.entry import _prepare_fix_cycle_operations

    expected = ({"early": True}, None, None, [])
    with patch("eurika.orchestration.entry.prepare_fix_cycle_operations", return_value=expected) as mock_prepare:
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
        patch("eurika.orchestration.entry.load_fix_cycle_deps", return_value=deps),
        patch("eurika.orchestration.entry._prepare_fix_cycle_operations", return_value=(None, fake_result, patch_plan, ops)),
        patch("eurika.orchestration.entry.select_hybrid_operations", return_value=(ops, [])),
        patch("eurika.orchestration.entry.execute_fix_apply_stage", return_value=({"verify": {"success": True}}, ["a.py"], True)) as mock_apply,
        patch("eurika.orchestration.entry.build_fix_cycle_result", return_value={"ok": True}) as mock_build,
    ):
        out = run_cycle(ROOT, mode="fix", quiet=True)
    assert out == {"ok": True}
    assert mock_apply.call_count == 1
    assert mock_build.call_count == 1
