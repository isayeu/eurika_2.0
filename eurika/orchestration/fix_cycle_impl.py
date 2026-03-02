"""Implementation body for fix cycle orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .apply_stage import write_fix_report
from .contracts import FixReport, OperationRecord, PatchPlan
from .cycle_state import with_cycle_state
from .deps import FixCycleDeps
from .fix_cycle_helpers import (
    attach_decision_summary,
    filter_executable_operations,
    infer_early_stages,
    select_operations_by_indexes,
)
from .logging import get_logger
from .models import FixCycleContext
from .pipeline_model import PipelineStage, attach_pipeline_trace

_LOG = get_logger("orchestration.fix_cycle")


def run_fix_cycle_impl(
    path: Path,
    *,
    runtime_mode: str = "assist",
    non_interactive: bool = False,
    session_id: str | None = None,
    window: int = 5,
    dry_run: bool = False,
    quiet: bool = False,
    skip_scan: bool = False,
    no_clean_imports: bool = False,
    no_code_smells: bool = False,
    verify_cmd: str | None = None,
    verify_timeout: int | None = None,
    allow_campaign_retry: bool = False,
    allow_low_risk_campaign: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
    fix_cycle_deps: Callable[[], FixCycleDeps],
    prepare_fix_cycle_operations: Callable[..., tuple[dict[str, Any] | None, Any, PatchPlan | None, list[OperationRecord]]],
    select_hybrid_operations: Callable[..., tuple[list[OperationRecord], list[OperationRecord]]],
    build_fix_dry_run_result: Callable[[Path, PatchPlan, list[OperationRecord], Any], dict[str, Any]],
    attach_fix_telemetry: Callable[[FixReport, list[OperationRecord]], None],
    build_fix_cycle_result: Callable[[FixReport, list[OperationRecord], list[str], bool, Any], dict[str, Any]],
    execute_fix_apply_stage: Callable[..., tuple[FixReport, list[str], bool]],
) -> dict[str, Any]:
    """Core implementation for run_fix_cycle; callbacks keep orchestrator patchability in tests."""
    _ = FixCycleContext(
        path=path,
        runtime_mode=runtime_mode,
        non_interactive=non_interactive,
        session_id=session_id,
        window=window,
        dry_run=dry_run,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        allow_campaign_retry=allow_campaign_retry,
    )
    deps = fix_cycle_deps()
    run_scan = deps["run_scan"]
    patch_plan: PatchPlan | None = None

    if apply_approved:
        from .fix_cycle_apply_approved import run_apply_approved_path

        return run_apply_approved_path(
            path,
            session_id=session_id,
            quiet=quiet,
            verify_cmd=verify_cmd,
            verify_timeout=verify_timeout,
            deps=deps,
            execute_fix_apply_stage=execute_fix_apply_stage,
            build_fix_cycle_result=build_fix_cycle_result,
            attach_fix_telemetry=attach_fix_telemetry,
        )

    early, result, patch_plan, operations = prepare_fix_cycle_operations(
        path,
        runtime_mode=runtime_mode,
        session_id=session_id,
        window=window,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        allow_campaign_retry=allow_campaign_retry,
        allow_low_risk_campaign=allow_low_risk_campaign,
        run_scan=run_scan,
    )
    if early is not None:
        if team_mode:
            from .team_mode import save_pending_plan

            ops_early = early.get("operations", [])
            patch_early = patch_plan or {"operations": ops_early}
            policy_dec = (early.get("report") or {}).get("policy_decisions", [])
            saved = save_pending_plan(path, patch_early, ops_early, policy_dec, session_id)
            if not quiet:
                _LOG.info(f"Team mode: plan saved to {saved}")
            _LOG.info(
                "Edit team_decision='approve' for desired ops, then run: eurika fix . --apply-approved"
                )
            rc = early.get("return_code", 0)
            rep = dict(
                early.get("report", {}),
                message=f"Plan saved to {saved}. Run eurika fix . --apply-approved after review.",
                patch_plan=dict(patch_early) if patch_early else {"operations": ops_early},
            )
            _early_stages = infer_early_stages(early)
            attach_pipeline_trace(rep, _early_stages)
            return with_cycle_state(
                {
                    "return_code": rc,
                    "report": rep,
                    "operations": ops_early,
                    "modified": [],
                    "verify_success": None,
                    "agent_result": early.get("agent_result"),
                    "dry_run": True,
                },
                is_error=(rc != 0),
            )
        if isinstance(early, dict) and isinstance(early.get("report"), dict):
            attach_fix_telemetry(early["report"], early.get("operations", []))
            attach_pipeline_trace(early["report"], infer_early_stages(early))
            write_fix_report(path, early["report"], quiet)
        early["dry_run"] = dry_run
        return with_cycle_state(early, is_error=(early.get("return_code", 0) != 0))

    if team_mode:
        from .team_mode import save_pending_plan

        policy_decisions = result.output.get("policy_decisions", [])
        pending_patch_plan = patch_plan or {"operations": operations}
        saved = save_pending_plan(path, pending_patch_plan, operations, policy_decisions, session_id)
        if not quiet:
            _LOG.info(f"Team mode: plan saved to {saved}")
            _LOG.info(
                "Edit team_decision='approve' and approved_by for desired ops, then run: eurika fix . --apply-approved",
            )
        rep = {
            "message": f"Plan saved to {saved}. Run eurika fix . --apply-approved after review.",
            "patch_plan": dict(pending_patch_plan) if pending_patch_plan else {"operations": operations},
            "policy_decisions": policy_decisions,
        }
        attach_pipeline_trace(rep, [PipelineStage.INPUT.value, PipelineStage.PLAN.value])
        return with_cycle_state(
            {
                "return_code": 0,
                "report": rep,
                "operations": operations,
                "modified": [],
                "verify_success": None,
                "agent_result": result,
                "dry_run": True,
            },
            is_error=False,
        )

    planned_ops = list(operations)
    if approve_ops or reject_ops:
        approved_ops, rejected_ops, selection_error = select_operations_by_indexes(
            operations,
            approve_ops=approve_ops,
            reject_ops=reject_ops,
        )
        if selection_error:
            report = {"error": selection_error}
            attach_pipeline_trace(
                report,
                [PipelineStage.INPUT.value, PipelineStage.PLAN.value, PipelineStage.VALIDATE.value],
            )
            write_fix_report(path, report, quiet)
            return with_cycle_state(
                {
                    "return_code": 1,
                    "report": report,
                    "operations": [],
                    "modified": [],
                    "verify_success": False,
                    "agent_result": result,
                    "dry_run": dry_run,
                },
                is_error=True,
            )
    else:
        approved_ops, rejected_ops = select_hybrid_operations(
            operations,
            quiet=quiet,
            non_interactive=non_interactive or runtime_mode != "hybrid",
        )
    if rejected_ops and session_id:
        from eurika.storage import SessionMemory

        SessionMemory(path).record(session_id, approved=approved_ops, rejected=rejected_ops)
    operations = approved_ops
    if patch_plan is None:
        report = {"error": "Internal error: missing patch plan after prepare stage."}
        attach_pipeline_trace(
            report,
            [PipelineStage.INPUT.value, PipelineStage.PLAN.value, PipelineStage.VALIDATE.value],
        )
        write_fix_report(path, report, quiet)
        return with_cycle_state(
            {
                "return_code": 1,
                "report": report,
                "operations": [],
                "modified": [],
                "verify_success": False,
                "agent_result": result,
                "dry_run": dry_run,
            },
            is_error=True,
        )
    patch_plan = dict(patch_plan, operations=operations)
    rejected_files = [
        str(op.get("target_file", ""))
        for op in rejected_ops
        if op.get("target_file")
    ]
    rejected_meta: list[dict[str, Any]] = []
    rejected_reasons: dict[str, str] = {}
    for op in rejected_ops:
        target = str(op.get("target_file") or "")
        reason = str(op.get("rejection_reason") or "rejected_by_human")
        rejected_meta.append(
            {
                "target_file": target,
                "kind": op.get("kind"),
                "approval_state": "rejected",
                "critic_verdict": str(op.get("critic_verdict") or "allow"),
                "decision_source": str(op.get("decision_source") or "human"),
                "skipped_reason": reason,
            }
        )
        if target:
            rejected_reasons[target] = reason
    executable_ops, gate_skipped, gate_skipped_reasons, gate_skipped_files = filter_executable_operations(operations)
    if not executable_ops:
        all_skipped = rejected_files + gate_skipped_files
        skipped_reasons = dict(gate_skipped_reasons)
        skipped_reasons.update(rejected_reasons)
        report = {
            "message": "All operations rejected by user/policy. Cycle complete.",
            "policy_decisions": result.output.get("policy_decisions", []),
            "critic_decisions": result.output.get("critic_decisions", []),
            "context_sources": result.output.get("context_sources"),
            "llm_hint_runtime": result.output.get("llm_hint_runtime"),
            "operation_explanations": [],
            "operation_results": gate_skipped + rejected_meta,
            "skipped": all_skipped,
            "skipped_reasons": skipped_reasons,
        }
        attach_decision_summary(report)
        attach_fix_telemetry(report, planned_ops)
        attach_pipeline_trace(
            report,
            [PipelineStage.INPUT.value, PipelineStage.PLAN.value, PipelineStage.VALIDATE.value],
        )
        write_fix_report(path, report, quiet)
        return with_cycle_state(
            {
                "return_code": 0,
                "report": report,
                "operations": [],
                "modified": [],
                "verify_success": True,
                "agent_result": result,
                "dry_run": dry_run,
            },
            is_error=False,
        )

    if dry_run:
        if not quiet:
            _LOG.info("--- Step 3/3: plan (dry-run, no apply) ---")
        out = build_fix_dry_run_result(path, patch_plan, operations, result)
        out["report"]["critic_decisions"] = result.output.get("critic_decisions", [])
        out["report"]["operation_results"] = list(out["report"].get("operation_results", [])) + gate_skipped + rejected_meta
        if gate_skipped_reasons:
            out["report"]["skipped_reasons"] = dict(gate_skipped_reasons)
            out["report"]["skipped"] = list(gate_skipped_files)
        if rejected_reasons:
            out["report"]["skipped_reasons"] = {
                **(out["report"].get("skipped_reasons") or {}),
                **rejected_reasons,
            }
            out["report"]["skipped"] = list(out["report"].get("skipped", [])) + list(rejected_files)
        attach_decision_summary(out["report"])
        attach_fix_telemetry(out["report"], planned_ops)
        attach_pipeline_trace(
            out["report"],
            [PipelineStage.INPUT.value, PipelineStage.PLAN.value, PipelineStage.VALIDATE.value],
        )
        return out
    patch_plan = dict(patch_plan, operations=executable_ops)
    report, modified, verify_success = execute_fix_apply_stage(
        path,
        patch_plan,
        executable_ops,
        session_id=session_id,
        quiet=quiet,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        backup_dir=deps["BACKUP_DIR"],
        apply_and_verify=deps["apply_and_verify"],
        run_scan=run_scan,
        build_snapshot_from_self_map=deps["build_snapshot_from_self_map"],
        diff_architecture_snapshots=deps["diff_architecture_snapshots"],
        metrics_from_graph=deps["metrics_from_graph"],
        rollback_patch=deps["rollback_patch"],
        result=result,
    )
    if gate_skipped:
        report["operation_results"] = list(report.get("operation_results", [])) + list(gate_skipped)
        report["skipped"] = list(report.get("skipped", [])) + list(gate_skipped_files)
        report["skipped_reasons"] = {**(report.get("skipped_reasons") or {}), **gate_skipped_reasons}  # type: ignore[dict-item]
    if rejected_meta:
        report["operation_results"] = list(report.get("operation_results", [])) + list(rejected_meta)
        report["skipped"] = list(report.get("skipped", [])) + list(rejected_files)
        report["skipped_reasons"] = {**(report.get("skipped_reasons") or {}), **rejected_reasons}  # type: ignore[dict-item]
    attach_decision_summary(report)
    attach_pipeline_trace(
        report,
        [
            PipelineStage.INPUT.value,
            PipelineStage.PLAN.value,
            PipelineStage.VALIDATE.value,
            PipelineStage.APPLY.value,
            PipelineStage.VERIFY.value,
        ],
    )
    write_fix_report(path, report, quiet)
    return build_fix_cycle_result(report, executable_ops, modified, verify_success, result)
