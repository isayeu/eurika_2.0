"""Tests for ROADMAP v3.0 Stage 3 — Safety (risk-based, simulation-first, regression)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from eurika.reasoning.planner.models import risk_report_from_plan
from patch_engine import simulate_patch


def test_risk_report_from_plan_empty() -> None:
    r = risk_report_from_plan({})
    assert r.total_risk == 0.0
    assert r.level == "low"


def test_risk_report_from_plan_low_risk() -> None:
    plan = {
        "operations": [
            {"target_file": "a.py", "kind": "remove_unused_import"},
        ]
    }
    r = risk_report_from_plan(plan)
    assert r.total_risk < 0.5
    assert r.level == "low"


def test_risk_report_from_plan_high_risk() -> None:
    plan = {
        "operations": [
            {"target_file": "big.py", "kind": "split_module"},
            {"target_file": "other.py", "kind": "extract_class"},
        ]
    }
    r = risk_report_from_plan(plan)
    assert r.total_risk >= 0.7
    assert r.level == "high"
    assert "simulate_patch" in str(r.recommendations).lower()


def test_simulation_first_abort_on_errors(tmp_path: Path) -> None:
    """When simulate_patch reports errors, execute_fix_apply_stage aborts without apply."""
    from eurika.orchestration.apply_stage import execute_fix_apply_stage

    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    # Plan with missing target_file triggers errors in patch_apply
    plan = {
        "operations": [
            {"target_file": "", "kind": "refactor_module", "diff": "# x", "description": "bad"},
        ]
    }
    sim = simulate_patch(tmp_path, plan)
    assert "operation missing target_file" in (sim.get("errors") or [])

    # Execute apply stage — should abort before apply_and_verify (no disk writes)
    class FakeResult:
        output = {"policy_decisions": [], "critic_decisions": [], "summary": {"risks": []}}

    report, modified, verify_success = execute_fix_apply_stage(
        tmp_path,
        plan,
        [{"target_file": "", "kind": "refactor_module"}],
        session_id=None,
        quiet=True,
        verify_cmd=None,
        verify_timeout=None,
        backup_dir=".eurika_backups",
        apply_and_verify=lambda *a, **k: {"modified": [], "verify": {"success": False}},
        run_scan=lambda *a: None,
        build_snapshot_from_self_map=lambda *a: None,
        diff_architecture_snapshots=lambda *a: {},
        metrics_from_graph=lambda *a: {},
        rollback_patch=lambda *a: {},
        result=FakeResult(),
    )
    assert report.get("aborted_reason") == "simulation_errors"
    assert modified == []
    assert verify_success is False
