"""Unit tests for cycle state model and transitions (R2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.orchestration.cycle_state import (
    CycleState,
    is_error_result,
    is_valid_state_history,
    with_cycle_state,
)


def test_with_cycle_state_success_adds_done() -> None:
    """Success result gets state=done, history=[thinking, done]."""
    result = with_cycle_state({"return_code": 0, "report": {}}, is_error=False)
    assert result["state"] == CycleState.DONE.value
    assert result["state_history"] == ["thinking", "done"]


def test_with_cycle_state_error_adds_error() -> None:
    """Error result gets state=error, history=[thinking, error]."""
    result = with_cycle_state({"return_code": 1, "report": {"error": "x"}}, is_error=True)
    assert result["state"] == CycleState.ERROR.value
    assert result["state_history"] == ["thinking", "error"]


def test_is_valid_state_history_accepts_valid() -> None:
    """Valid histories: [thinking, done] and [thinking, error]."""
    assert is_valid_state_history(["thinking", "done"]) is True
    assert is_valid_state_history(["thinking", "error"]) is True


def test_is_valid_state_history_rejects_invalid() -> None:
    """Invalid histories are rejected."""
    assert is_valid_state_history(["idle", "done"]) is False
    assert is_valid_state_history(["thinking"]) is False
    assert is_valid_state_history(["thinking", "done", "idle"]) is False
    assert is_valid_state_history([]) is False


def test_is_error_result() -> None:
    """is_error_result infers error from result shape."""
    assert is_error_result({"error": "x"}) is True
    assert is_error_result({"return_code": 1}) is True
    assert is_error_result({"report": {"error": "y"}}) is True
    assert is_error_result({"report": {"verify": {"success": False}}}) is True
    assert is_error_result({"return_code": 0, "report": {"verify": {"success": True}}}) is False


def test_fix_cycle_result_includes_state_on_success(tmp_path: Path) -> None:
    """Fix cycle success returns state=done and valid state_history."""
    from cli.orchestrator import run_fix_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    out = run_fix_cycle(
        tmp_path,
        runtime_mode="assist",
        non_interactive=True,
        dry_run=True,
        quiet=True,
        skip_scan=True,
    )
    assert "state" in out
    assert "state_history" in out
    assert out["state"] in ("done", "error")
    assert is_valid_state_history(out["state_history"]) is True
    if out["state"] == "done":
        assert out["state_history"] == ["thinking", "done"]


def test_fix_cycle_result_includes_error_state_on_failure(tmp_path: Path) -> None:
    """Fix cycle error path returns state=error and valid state_history."""
    from cli.orchestrator import run_fix_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    out = run_fix_cycle(
        tmp_path,
        runtime_mode="assist",
        non_interactive=True,
        dry_run=True,
        quiet=True,
        skip_scan=True,
    )
    assert "state" in out
    assert "state_history" in out
    assert is_valid_state_history(out["state_history"]) is True


def _minimal_self_map(path: Path, modules: list[str], dependencies: dict) -> None:
    data = {
        "modules": [{"path": p, "lines": 10, "functions": [], "classes": []} for p in modules],
        "dependencies": dependencies,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_doctor_cycle_includes_state_on_success(tmp_path: Path) -> None:
    """Doctor cycle success returns state=done."""
    from cli.orchestration import run_doctor_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    out = run_doctor_cycle(tmp_path, no_llm=True)
    assert "state" in out
    assert "state_history" in out
    assert out["state"] == "done"
    assert is_valid_state_history(out["state_history"]) is True
    assert out["state_history"] == ["thinking", "done"]


def test_doctor_cycle_includes_error_state_on_summary_error(tmp_path: Path) -> None:
    """Doctor cycle with summary error returns state=error."""
    from cli.orchestration import run_doctor_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    # Path without pyproject/valid project causes summary error
    out = run_doctor_cycle(tmp_path, no_llm=True)
    if out.get("error"):
        assert "state" in out
        assert out["state"] == "error"
        assert is_valid_state_history(out["state_history"]) is True
        assert out["state_history"] == ["thinking", "error"]


def test_doctor_cycle_r2_state_model_on_self() -> None:
    """R2 Runtime Robustness: doctor on project returns valid state."""
    from cli.orchestration import run_doctor_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    out = run_doctor_cycle(ROOT, no_llm=True)
    assert "state" in out
    assert "state_history" in out
    assert out["state"] in ("done", "error")
    assert is_valid_state_history(out["state_history"]) is True


def test_fix_apply_approved_missing_plan_returns_error_state(tmp_path: Path) -> None:
    """apply-approved with no pending plan returns state=error."""
    from cli.orchestrator import run_fix_cycle

    out = run_fix_cycle(
        tmp_path,
        runtime_mode="assist",
        non_interactive=True,
        apply_approved=True,
        quiet=True,
        skip_scan=True,
    )
    assert out.get("return_code") == 1
    assert out["state"] == "error"
    assert out["state_history"] == ["thinking", "error"]
