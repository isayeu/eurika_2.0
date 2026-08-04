"""Apply-from-report path: load patch_plan from last dry-run (eurika_fix_report.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .apply_stage import attach_run_params, write_fix_report
from .contracts import FixReport, OperationRecord
from .cycle_state import with_cycle_state
from .deps import FixCycleDeps
from .fix_cycle_helpers import attach_decision_summary, filter_executable_operations
from .pipeline_model import PipelineStage, attach_pipeline_trace


def load_plan_from_fix_report(project_root: Path) -> tuple[list[OperationRecord], dict[str, Any] | None]:
    """Load patch_plan from eurika_fix_report.json if from dry-run. Returns (ops, full_report) or ([], None)."""
    report_path = Path(project_root).resolve() / "eurika_fix_report.json"
    if not report_path.exists():
        return [], None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return [], None
    if not isinstance(data, dict):
        return [], None
    if not data.get("dry_run"):
        return [], None
    patch_plan = data.get("patch_plan")
    if not isinstance(patch_plan, dict):
        return [], None
    ops = patch_plan.get("operations")
    if not isinstance(ops, list) or not ops:
        return [], None
    # Mark all as approved (from report, bypass re-diagnose)
    approved: list[OperationRecord] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        op_copy = dict(op)
        op_copy["approval_state"] = "approved"
        op_copy["decision_source"] = "report"
        op_copy["critic_verdict"] = str(op_copy.get("critic_verdict") or "allow").lower()
        approved.append(op_copy)
    return approved, data


def run_apply_from_report_path(
    path: Path,
    *,
    session_id: str | None,
    quiet: bool,
    verify_cmd: str | None,
    verify_timeout: int | None,
    run_params: dict[str, Any] | None = None,
    deps: FixCycleDeps,
    execute_fix_apply_stage: Callable[..., tuple[FixReport, list[str], bool]],
    build_fix_cycle_result: Callable[[FixReport, list[OperationRecord], list[str], bool, Any], dict[str, Any]],
    attach_fix_telemetry: Callable[[FixReport, list[OperationRecord]], None],
) -> dict[str, Any]:
    """Handle --apply-from-report: load patch_plan from eurika_fix_report.json, apply (skip scan+diagnose)."""
    approved, report_data = load_plan_from_fix_report(path)
    if not report_data:
        rep: FixReport = {
            "error": "No dry-run report. Run eurika fix . --dry-run first.",
            "hint": "eurika_fix_report.json must exist with dry_run: true and patch_plan.",
        }
        attach_pipeline_trace(rep, [])
        return with_cycle_state(
            {"return_code": 1, "report": rep, "operations": [], "modified": [], "verify_success": False, "agent_result": None},
            is_error=True,
        )
    if not approved:
        rep = {"message": "No operations in last dry-run plan.", "patch_plan": report_data.get("patch_plan", {})}
        attach_pipeline_trace(rep, [])
        return with_cycle_state(
            {"return_code": 0, "report": rep, "operations": [], "modified": [], "verify_success": True, "agent_result": None},
            is_error=False,
        )
    patch_plan = dict(report_data.get("patch_plan") or {}, operations=approved)
    approved, _, skipped_reasons, skipped_files = filter_executable_operations(approved, team_override=True)
    if not approved:
        op_results = []
        for target, reason in skipped_reasons.items():
            op_results.append({
                "target_file": target,
                "kind": None,
                "approval_state": "approved",
                "critic_verdict": "deny",
                "decision_source": "report",
                "applied": False,
                "skipped_reason": reason,
            })
        report = {
            "message": "No executable operations after decision gate.",
            "skipped": skipped_files,
            "skipped_reasons": skipped_reasons,
            "operation_results": op_results,
        }
        if run_params:
            attach_run_params(report, **run_params)
        attach_decision_summary(report)
        attach_fix_telemetry(report, [])
        attach_pipeline_trace(report, [PipelineStage.VALIDATE.value])
        write_fix_report(path, report, quiet)
        return with_cycle_state(
            {"return_code": 0, "report": report, "operations": [], "modified": [], "verify_success": True, "agent_result": None},
            is_error=False,
        )
    patch_plan = dict(patch_plan, operations=approved)
    result = type("R", (), {
        "output": {
            "policy_decisions": [{"decision": "allow"} for _ in approved],
            "critic_decisions": [],
            "summary": {"risks": []},
        },
    })()
    report, modified, verify_success = execute_fix_apply_stage(
        path,
        patch_plan,
        approved,
        session_id=session_id,
        quiet=quiet,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        run_params=run_params,
        backup_dir=deps["BACKUP_DIR"],
        apply_and_verify=deps["apply_and_verify"],
        run_scan=deps["run_scan"],
        build_snapshot_from_self_map=deps["build_snapshot_from_self_map"],
        diff_architecture_snapshots=deps["diff_architecture_snapshots"],
        metrics_from_graph=deps["metrics_from_graph"],
        rollback_patch=deps["rollback_patch"],
        result=result,
    )
    attach_pipeline_trace(report, [PipelineStage.VALIDATE.value, PipelineStage.APPLY.value, PipelineStage.VERIFY.value])
    return build_fix_cycle_result(report, approved, modified, verify_success, result)
