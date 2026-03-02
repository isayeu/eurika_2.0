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


def test_is_error_result_edge_cases() -> None:
    """is_error_result edge cases: verify success false, missing report."""
    assert is_error_result({"return_code": 0, "report": {"verify": {"success": False}}}) is True
    assert is_error_result({"return_code": 0, "report": {}}) is False  # no verify → not error
    assert is_error_result({"return_code": 0}) is False
    assert is_error_result({}) is False
    assert is_error_result({"report": {"verify": {}}}) is False  # success not False
    assert is_error_result({"report": {"verify": {"success": True}}}) is False


def test_with_cycle_state_matches_is_error_result() -> None:
    """with_cycle_state output matches is_error_result inference."""
    err_cases = [
        {"error": "fail"},
        {"return_code": 1},
        {"report": {"verify": {"success": False}}},
    ]
    for r in err_cases:
        assert is_error_result(r) is True
        out = with_cycle_state(dict(r), is_error=True)
        assert out["state"] == CycleState.ERROR.value
        assert out["state_history"] == ["thinking", "error"]

    ok_cases = [
        {"return_code": 0, "report": {"verify": {"success": True}}},
        {"return_code": 0, "report": {}},
    ]
    for r in ok_cases:
        assert is_error_result(r) is False
        out = with_cycle_state(dict(r), is_error=False)
        assert out["state"] == CycleState.DONE.value
        assert out["state_history"] == ["thinking", "done"]


def test_cycle_state_enum_values() -> None:
    """CycleState has expected R2 values."""
    assert CycleState.IDLE.value == "idle"
    assert CycleState.THINKING.value == "thinking"
    assert CycleState.ERROR.value == "error"
    assert CycleState.DONE.value == "done"


def test_pipeline_model_stages_and_validation() -> None:
    """P0.3: PipelineStage enum and is_valid_stage_sequence."""
    from eurika.orchestration.pipeline_model import (
        PipelineStage,
        is_valid_stage_sequence,
        next_stage,
        build_pipeline_trace,
    )

    assert PipelineStage.INPUT.value == "input"
    assert PipelineStage.PLAN.value == "plan"
    assert PipelineStage.VALIDATE.value == "validate"
    assert PipelineStage.APPLY.value == "apply"
    assert PipelineStage.VERIFY.value == "verify"

    assert is_valid_stage_sequence(["input"]) is True
    assert is_valid_stage_sequence(["input", "plan", "validate"]) is True
    assert is_valid_stage_sequence(["input", "plan", "validate", "apply", "verify"]) is True
    assert is_valid_stage_sequence(["plan", "validate"]) is True  # prefix
    assert is_valid_stage_sequence(["validate", "input"]) is False  # wrong order
    assert is_valid_stage_sequence(["input", "input"]) is False  # non-strict

    assert next_stage(PipelineStage.INPUT) == PipelineStage.PLAN
    assert next_stage(PipelineStage.VERIFY) is None

    trace = build_pipeline_trace(["input", "plan"])
    assert trace["pipeline_stages"] == ["input", "plan"]
    assert "Input → Plan → Validate → Apply → Verify" in trace["pipeline_model"]


def test_fix_cycle_report_includes_pipeline_stages(tmp_path: Path) -> None:
    """P0.3: Fix cycle report includes pipeline_stages and pipeline_model."""
    from cli.orchestrator import run_fix_cycle

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "self_map.json").write_text('{"modules":[],"dependencies":{}}')
    out = run_fix_cycle(
        tmp_path,
        runtime_mode="assist",
        non_interactive=True,
        dry_run=True,
        quiet=True,
        skip_scan=True,
    )
    report = out.get("report") or {}
    assert "pipeline_stages" in report
    assert "pipeline_model" in report
    assert isinstance(report["pipeline_stages"], list)
    assert report["pipeline_model"] == "Input → Plan → Validate → Apply → Verify"


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
    """Doctor cycle with summary error returns state=error and degraded runtime."""
    from cli.orchestration import run_doctor_cycle
    from cli.orchestration.cycle_state import is_valid_state_history

    # Path without pyproject/valid project causes summary error
    out = run_doctor_cycle(tmp_path, no_llm=True)
    if out.get("error"):
        assert "state" in out
        assert out["state"] == "error"
        assert is_valid_state_history(out["state_history"]) is True
        assert out["state_history"] == ["thinking", "error"]
        runtime = out.get("runtime") or {}
        assert runtime.get("degraded_mode") is True
        assert "summary_unavailable" in (runtime.get("degraded_reasons") or [])


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


def test_full_cycle_doctor_error_propagates_state(tmp_path: Path) -> None:
    """Full cycle when doctor returns error propagates state=error."""
    from unittest.mock import patch

    from cli.orchestrator import run_doctor_cycle, run_fix_cycle
    from cli.orchestration.full_cycle import run_full_cycle

    def _doctor_error(path, **kwargs):
        from cli.orchestration.cycle_state import with_cycle_state

        return with_cycle_state(
            {"error": "summary_unavailable", "runtime": {"degraded_mode": True}},
            is_error=True,
        )

    with patch("runtime_scan.run_scan", return_value=0):
        out = run_full_cycle(
            tmp_path,
            quiet=True,
            no_llm=True,
            run_doctor_cycle_fn=_doctor_error,
            run_fix_cycle_fn=run_fix_cycle,
        )
    assert out["state"] == "error"
    assert out["state_history"] == ["thinking", "error"]
    assert out.get("return_code") == 1


def test_full_cycle_scan_fail_returns_degraded_runtime(tmp_path: Path) -> None:
    """Full cycle when scan fails returns report.runtime with degraded_reasons."""
    from unittest.mock import patch

    from cli.orchestrator import run_doctor_cycle, run_fix_cycle
    from cli.orchestration.full_cycle import run_full_cycle

    with patch("runtime_scan.run_scan", return_value=1):
        out = run_full_cycle(
            tmp_path,
            quiet=True,
            no_llm=True,
            run_doctor_cycle_fn=run_doctor_cycle,
            run_fix_cycle_fn=run_fix_cycle,
        )
    assert out.get("return_code") == 1
    assert out["state"] == "error"
    report = out.get("report") or {}
    runtime = report.get("runtime") or {}
    assert runtime.get("degraded_mode") is True
    assert "scan_failed" in (runtime.get("degraded_reasons") or [])
