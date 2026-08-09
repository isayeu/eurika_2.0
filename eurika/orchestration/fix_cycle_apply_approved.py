"""Apply-approved path: load pending plan, filter executable, run apply stage."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from .apply_stage import attach_run_params, write_fix_report
from .contracts import FixReport, OperationRecord
from .cycle_state import with_cycle_state
from .deps import FixCycleDeps
from .fix_cycle_helpers import attach_decision_summary, filter_executable_operations
from .pipeline_model import PipelineStage, attach_pipeline_trace

def run_apply_approved_path(path: Path, *, session_id: str | None, quiet: bool, verify_cmd: str | None, verify_timeout: int | None, run_params: dict[str, Any] | None = None, deps: FixCycleDeps, execute_fix_apply_stage: Callable[..., tuple[FixReport, list[str], bool]], build_fix_cycle_result: Callable[[FixReport, list[OperationRecord], list[str], bool, Any], dict[str, Any]], attach_fix_telemetry: Callable[[FixReport, list[OperationRecord]], None]) -> dict[str, Any]:
    """Handle --apply-approved: load approved ops, filter, execute apply stage."""
    from .team_mode import clear_pending_plan_after_apply, load_approved_operations, record_team_rejections, reset_approvals_after_rollback
    approved, payload = load_approved_operations(path)
    if not payload:
        rep: FixReport = {'error': 'No pending plan. Run eurika fix . --team-mode first.'}
        attach_pipeline_trace(rep, [])
        return with_cycle_state({'return_code': 1, 'report': rep, 'operations': [], 'modified': [], 'verify_success': False, 'agent_result': None}, is_error=True)
    record_team_rejections(path, payload)
    if not approved:
        clear_pending_plan_after_apply(path)
        report: FixReport = {
            'message': "No operations approved. Edit .eurika/pending_plan.json and set team_decision='approve'.",
            'modified': [],
            'operations': [],
            'verify': {'success': True},
            'safety_gates': {'verify_ran': False},
        }
        attach_pipeline_trace(report, [])
        write_fix_report(path, report, quiet)
        return with_cycle_state({'return_code': 0, 'report': report, 'operations': [], 'modified': [], 'verify_success': True, 'agent_result': None}, is_error=False)
    patch_plan = dict(payload.get('patch_plan') or {}, operations=approved)
    approved, _, skipped_reasons, skipped_files = filter_executable_operations(approved, team_override=True)
    if not approved:
        op_results = []
        for target, reason in skipped_reasons.items():
            op_results.append({'target_file': target, 'kind': None, 'approval_state': 'approved', 'critic_verdict': 'deny', 'decision_source': 'team', 'applied': False, 'skipped_reason': reason})
        report = {'message': 'No executable approved operations after decision gate.', 'skipped': skipped_files, 'skipped_reasons': skipped_reasons, 'operation_results': op_results}
        if run_params:
            attach_run_params(report, **run_params)
        attach_decision_summary(report)
        attach_fix_telemetry(report, [])
        attach_pipeline_trace(report, [PipelineStage.VALIDATE.value])
        write_fix_report(path, report, quiet)
        return with_cycle_state({'return_code': 0, 'report': report, 'operations': [], 'modified': [], 'verify_success': True, 'agent_result': None}, is_error=False)
    patch_plan = dict(patch_plan, operations=approved)
    result = type('R', (), {'output': {'policy_decisions': [{'decision': 'allow'} for _ in approved], 'critic_decisions': [], 'summary': {'risks': []}}})()
    report, modified, verify_success = execute_fix_apply_stage(path, patch_plan, approved, session_id=session_id, quiet=quiet, verify_cmd=verify_cmd, verify_timeout=verify_timeout, run_params=run_params, backup_dir=deps['BACKUP_DIR'], apply_and_verify=deps['apply_and_verify'], run_scan=deps['run_scan'], build_snapshot_from_self_map=deps['build_snapshot_from_self_map'], diff_architecture_snapshots=deps['diff_architecture_snapshots'], metrics_from_graph=deps['metrics_from_graph'], rollback_patch=deps['rollback_patch'], result=result)
    rb = report.get("rollback") if isinstance(report, dict) else None
    if not verify_success and isinstance(rb, dict) and rb.get("done"):
        reset_approvals_after_rollback(path)
    elif verify_success:
        clear_pending_plan_after_apply(path)
    attach_pipeline_trace(report, [PipelineStage.VALIDATE.value, PipelineStage.APPLY.value, PipelineStage.VERIFY.value])
    return build_fix_cycle_result(report, approved, modified, verify_success, result)