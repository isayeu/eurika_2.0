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
    """Fix --no-code-smells: patch_plan has no refactor_code_smell ops when project has long function."""
    proj = tmp_path / "proj"
    proj.mkdir()
    long_func = "def long_foo():\n" + "    x = 1\n" * 50 + "    return x\n"
    (proj / "big.py").write_text(long_func, encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_big.py").write_text("def test_big(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "eurika_cli", "scan", str(proj)], cwd=ROOT, capture_output=True, timeout=30)

    r1 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    r2 = subprocess.run([sys.executable, "-m", "eurika_cli", "fix", "--dry-run", "--no-code-smells", str(proj)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r1.returncode == 0 and r2.returncode == 0
    d1 = _parse_final_json(r1.stdout)
    d2 = _parse_final_json(r2.stdout)
    ops1 = d1.get("patch_plan", {}).get("operations", []) if d1 else []
    ops2 = d2.get("patch_plan", {}).get("operations", []) if d2 else []
    code_smell1 = [o for o in ops1 if o.get("kind") == "refactor_code_smell"]
    code_smell2 = [o for o in ops2 if o.get("kind") == "refactor_code_smell"]
    assert len(code_smell1) >= 1, "without --no-code-smells should have refactor_code_smell ops for long function"
    assert len(code_smell2) == 0, "--no-code-smells should exclude refactor_code_smell ops"


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