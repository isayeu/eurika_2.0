"""Tests for eurika agent cycle and eurika fix (product) commands."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_fix_dry_run_on_self() -> None:
    """
    Product command eurika fix --dry-run: same flow as agent cycle --dry-run.
    Ensures the main entry point (fix) runs scan → arch-review → patch-plan without apply.
    """
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "fix", "--dry-run", str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    assert '"patch_plan"' in result.stdout, f"No patch_plan in output: {result.stdout[:500]}..."
    last_brace = result.stdout.rfind("}")
    assert last_brace >= 0
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = result.stdout[i]
        if c == "}":
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    data = json.loads(result.stdout[start : last_brace + 1])
    assert "patch_plan" in data
    plan = data["patch_plan"]
    ops = plan.get("operations", [])
    assert ops, "Patch plan should have operations on this project"
    assert all("target_file" in op and "diff" in op and "smell_type" in op for op in ops)


def test_cycle_dry_run_on_self() -> None:
    """
    Cycle --dry-run: scan → arch-review → patch-plan, no apply.
    Verifies patch_plan JSON in stdout, no files modified.
    """
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "agent", "cycle", "--dry-run", str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # Stdout has scan report first, then JSON with patch_plan at the end
    assert '"patch_plan"' in result.stdout, f"No patch_plan in output: {result.stdout[:500]}..."
    # Find JSON: last complete { ... } object (our print is at the end)
    last_brace = result.stdout.rfind("}")
    assert last_brace >= 0, "No closing brace in output"
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = result.stdout[i]
        if c == "}":
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    data = json.loads(result.stdout[start : last_brace + 1])
    assert "patch_plan" in data
    plan = data["patch_plan"]
    ops = plan.get("operations", [])
    assert ops, "Patch plan should have operations on this project"
    assert all("target_file" in op and "diff" in op and "smell_type" in op for op in ops)


def test_cycle_dry_run_on_minimal_project(tmp_path: Path) -> None:
    """
    Cycle --dry-run on minimal project may return empty operations (no smells).
    Should still complete with exit 0.
    """
    proj = tmp_path / "min"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_a.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "agent", "cycle", "--dry-run", str(proj)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # May have operations or not; main thing is it completes
    assert result.returncode == 0, f"stderr: {result.stderr}"


def _parse_final_json(stdout: str):
    """Extract last top-level JSON object from stdout (cycle prints report at end)."""
    last_brace = stdout.rfind("}")
    if last_brace < 0:
        return None
    depth = 1
    start = last_brace
    for i in range(last_brace - 1, -1, -1):
        c = stdout[i]
        if c == "}":
            depth += 1
        elif c == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    try:
        return json.loads(stdout[start : last_brace + 1])
    except json.JSONDecodeError:
        return None


def test_cycle_full_apply_then_rollback(tmp_path: Path) -> None:
    """
    Full cycle with apply on a minimal project: run cycle (apply + verify),
    assert report contains rescan_diff when apply happened, then rollback.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    # One "center" module imported by several others -> may get bottleneck/god_module
    (proj / "center.py").write_text("def value():\n    return 42\n", encoding="utf-8")
    for name in ("a", "b", "c", "d", "e"):
        (proj / f"{name}.py").write_text(
            f"from center import value\nx = value()\n", encoding="utf-8"
        )
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "tests" / "test_center.py").write_text(
        "from center import value\ndef test_value(): assert value() == 42\n",
        encoding="utf-8",
    )
    (proj / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "agent", "cycle", "--quiet", str(proj)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout[:1000]}"

    data = _parse_final_json(result.stdout)
    # If patch plan had operations, we get apply report with optional rescan_diff
    if data and "rescan_diff" in data:
        assert "structures" in data["rescan_diff"] or "smells" in data["rescan_diff"]
    if data and data.get("run_id"):
        rollback = subprocess.run(
            [sys.executable, "-m", "eurika_cli", "agent", "patch-rollback", str(proj)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert rollback.returncode == 0, rollback.stderr
        out = json.loads(rollback.stdout)
        assert out.get("errors") == []
        assert len(out.get("restored", [])) >= 1
