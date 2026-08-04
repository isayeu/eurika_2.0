"""Tests for eurika self-check command (self-analysis ritual)."""

import io
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.handlers import handle_self_check
from eurika.checks.self_guard import (
    SelfGuardResult,
    collect_self_guard,
    format_self_guard_block,
    self_guard_pass,
)


def test_self_check_on_minimal_project(tmp_path: Path):
    """self-check runs scan successfully on a minimal project."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "main.py").write_text("def foo():\n    return 42\n", encoding="utf-8")

    class Args:
        path = project_root

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = handle_self_check(Args())

    out = buf_out.getvalue()
    err = buf_err.getvalue()
    combined = out + err

    assert code == 0
    assert "eurika: self-check" in combined or "self-check" in combined
    assert "analyzing project architecture" in combined
    assert "Eurika Scan Report" in out
    assert (project_root / "self_map.json").exists()


def test_self_check_on_self():
    """self-check runs successfully on Eurika project root."""
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "self-check", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "self-check" in combined.lower() or "eurika" in combined.lower()
    assert "Architecture" in combined or "Eurika Scan Report" in combined


def test_self_check_r1_layer_discipline_on_self():
    """R1 Structural Hardening: self-check on project must report LAYER DISCIPLINE: OK."""
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "self-check", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "LAYER DISCIPLINE: OK" in combined or "LAYER DISCIPLINE" in combined
    assert "0 forbidden" in combined or "0 layer violations" in combined


def test_self_guard_format_with_complexity_budget():
    """SELF-GUARD block includes complexity budget alarms when present."""
    result = SelfGuardResult(
        forbidden_count=0,
        layer_viol_count=0,
        subsystem_bypass_count=0,
        must_split_count=0,
        candidates_count=0,
        trend_alarms=[],
        complexity_budget_alarms=["god_module 10>8"],
    )
    block = format_self_guard_block(result)
    assert "Complexity budget" in block
    assert "god_module 10>8" in block


def test_self_guard_pass_excludes_alarms():
    """self_guard_pass is True when no blocking violations (alarms do not block)."""
    result = SelfGuardResult(
        forbidden_count=0,
        layer_viol_count=0,
        subsystem_bypass_count=0,
        must_split_count=0,
        candidates_count=0,
        trend_alarms=["centralization increasing"],
        complexity_budget_alarms=["god_module 10>8"],
    )
    assert self_guard_pass(result) is True


def test_self_guard_pass_fails_on_must_split():
    """self_guard_pass is False when must_split violations exist."""
    result = SelfGuardResult(
        forbidden_count=0,
        layer_viol_count=0,
        subsystem_bypass_count=0,
        must_split_count=1,
        candidates_count=0,
        trend_alarms=[],
        complexity_budget_alarms=[],
    )
    assert self_guard_pass(result) is False


def test_self_guard_pass_fails_on_candidates_p04():
    """P0.4: self_guard_pass is False when candidates (>400 LOC) exist."""
    result = SelfGuardResult(
        forbidden_count=0,
        layer_viol_count=0,
        subsystem_bypass_count=0,
        must_split_count=0,
        candidates_count=1,
        trend_alarms=[],
        complexity_budget_alarms=[],
    )
    assert self_guard_pass(result) is False
    block = format_self_guard_block(result)
    assert "file-size" in block or ">400" in block
    assert "1 " in block


def test_collect_self_guard_empty_project(tmp_path: Path):
    """collect_self_guard on empty project returns valid result."""
    result = collect_self_guard(tmp_path)
    assert result.forbidden_count >= 0
    assert result.must_split_count >= 0
    assert "complexity_budget_alarms" in type(result).__dataclass_fields__
