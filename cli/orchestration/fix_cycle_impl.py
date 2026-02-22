"""Implementation body for fix cycle orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .apply_stage import write_fix_report
from .logging import get_logger
from .models import FixCycleContext

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
    team_mode: bool = False,
    apply_approved: bool = False,
    fix_cycle_deps: Callable[[], dict[str, Any]],
    prepare_fix_cycle_operations: Callable[..., tuple[dict[str, Any] | None, Any, dict[str, Any] | None, list[dict[str, Any]]]],
    select_hybrid_operations: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    build_fix_dry_run_result: Callable[[Path, dict[str, Any], list[dict[str, Any]], Any], dict[str, Any]],
    attach_fix_telemetry: Callable[[dict[str, Any], list[dict[str, Any]]], None],
    build_fix_cycle_result: Callable[[dict[str, Any], list[dict[str, Any]], list[str], bool, Any], dict[str, Any]],
    execute_fix_apply_stage: Callable[..., tuple[dict[str, Any], list[str], bool]],
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

    if apply_approved:
        from cli.orchestration.team_mode import load_approved_operations

        approved, payload = load_approved_operations(path)
        if not payload:
            return {
                "return_code": 1,
                "report": {"error": "No pending plan. Run eurika fix . --team-mode first."},
                "operations": [],
                "modified": [],
                "verify_success": False,
                "agent_result": None,
            }
        if not approved:
            return {
                "return_code": 0,
                "report": {
                    "message": "No operations approved. Edit .eurika/pending_plan.json and set team_decision='approve'."
                },
                "operations": [],
                "modified": [],
                "verify_success": True,
                "agent_result": None,
            }
        patch_plan = dict(payload.get("patch_plan") or {}, operations=approved)
        result = type(
            "R",
            (),
            {
                "output": {
                    "policy_decisions": [{"decision": "allow"} for _ in approved],
                    "summary": {"risks": []},
                }
            },
        )()

        report, modified, verify_success = execute_fix_apply_stage(
            path,
            patch_plan,
            approved,
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
        return build_fix_cycle_result(report, approved, modified, verify_success, result)

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
        run_scan=run_scan,
    )
    if early is not None:
        if team_mode:
            from cli.orchestration.team_mode import save_pending_plan

            ops_early = early.get("operations", [])
            patch_early = patch_plan or {"operations": ops_early}
            policy_dec = (early.get("report") or {}).get("policy_decisions", [])
            saved = save_pending_plan(path, patch_early, ops_early, policy_dec, session_id)
            if not quiet:
                _LOG.info(f"Team mode: plan saved to {saved}")
                _LOG.info(
                    "Edit team_decision='approve' for desired ops, then run: eurika fix . --apply-approved"
                )
            return {
                "return_code": early.get("return_code", 0),
                "report": dict(
                    early.get("report", {}),
                    message=f"Plan saved to {saved}. Run eurika fix . --apply-approved after review.",
                ),
                "operations": ops_early,
                "modified": [],
                "verify_success": None,
                "agent_result": early.get("agent_result"),
                "dry_run": True,
            }
        if isinstance(early, dict) and isinstance(early.get("report"), dict):
            attach_fix_telemetry(early["report"], early.get("operations", []))
            write_fix_report(path, early["report"], quiet)
        return early

    if team_mode:
        from cli.orchestration.team_mode import save_pending_plan

        policy_decisions = result.output.get("policy_decisions", [])
        saved = save_pending_plan(path, patch_plan, operations, policy_decisions, session_id)
        if not quiet:
            _LOG.info(f"Team mode: plan saved to {saved}")
            _LOG.info(
                "Edit team_decision='approve' and approved_by for desired ops, then run: eurika fix . --apply-approved",
            )
        return {
            "return_code": 0,
            "report": {
                "message": f"Plan saved to {saved}. Run eurika fix . --apply-approved after review.",
                "policy_decisions": policy_decisions,
            },
            "operations": operations,
            "modified": [],
            "verify_success": None,
            "agent_result": result,
            "dry_run": True,
        }

    approved_ops, rejected_ops = select_hybrid_operations(
        operations,
        quiet=quiet,
        non_interactive=non_interactive or runtime_mode != "hybrid",
    )
    if rejected_ops and session_id:
        from eurika.storage import SessionMemory

        SessionMemory(path).record(session_id, approved=approved_ops, rejected=rejected_ops)
    operations = approved_ops
    patch_plan = dict(patch_plan, operations=operations)
    if not operations:
        rejected_files = [
            str(op.get("target_file", ""))
            for op in rejected_ops
            if op.get("target_file")
        ]
        report = {
            "message": "All operations rejected by user/policy. Cycle complete.",
            "policy_decisions": result.output.get("policy_decisions", []),
            "operation_explanations": [],
            "skipped": rejected_files,
        }
        attach_fix_telemetry(report, approved_ops)
        write_fix_report(path, report, quiet)
        return {
            "return_code": 0,
            "report": report,
            "operations": [],
            "modified": [],
            "verify_success": True,
            "agent_result": result,
            "dry_run": dry_run,
        }

    if dry_run:
        if not quiet:
            _LOG.info("--- Step 3/3: plan (dry-run, no apply) ---")
        out = build_fix_dry_run_result(path, patch_plan, operations, result)
        attach_fix_telemetry(out["report"], operations)
        return out
    report, modified, verify_success = execute_fix_apply_stage(
        path,
        patch_plan,
        operations,
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
    return build_fix_cycle_result(report, operations, modified, verify_success, result)
