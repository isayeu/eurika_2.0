"""Implementation body for fix cycle orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .apply_stage import write_fix_report
from .logging import get_logger
from .models import FixCycleContext

_LOG = get_logger("orchestration.fix_cycle")


def _filter_executable_operations(
    operations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str], list[str]]:
    """Apply hard decision gate: only approved + critic allow/review are executable."""
    executable: list[dict[str, Any]] = []
    skipped_meta: list[dict[str, Any]] = []
    skipped_reasons: dict[str, str] = {}
    skipped_files: list[str] = []
    for op in operations:
        approval_state = str(op.get("approval_state", "approved"))
        critic_verdict = str(op.get("critic_verdict", "allow"))
        target = str(op.get("target_file") or "")
        reason = ""
        if approval_state != "approved":
            reason = f"approval_state={approval_state}"
        elif critic_verdict not in {"allow", "review"}:
            reason = f"critic_verdict={critic_verdict}"
        if reason:
            skipped_meta.append(
                {
                    "target_file": target,
                    "kind": op.get("kind"),
                    "approval_state": approval_state,
                    "critic_verdict": critic_verdict,
                    "decision_source": str(op.get("decision_source") or "policy"),
                    "skipped_reason": reason,
                }
            )
            if target:
                skipped_files.append(target)
                skipped_reasons[target] = reason
            continue
        executable.append(op)
    return executable, skipped_meta, skipped_reasons, skipped_files


def _parse_operation_indexes(raw: str | None, total_ops: int, *, flag_name: str) -> tuple[set[int], str | None]:
    """Parse 1-based indexes from CSV string."""
    if not raw:
        return set(), None
    out: set[int] = set()
    parts = [p.strip() for p in str(raw).split(",")]
    for p in parts:
        if not p:
            continue
        if not p.isdigit():
            return set(), f"Invalid {flag_name} value '{p}': expected integers"
        idx = int(p)
        if idx < 1 or idx > total_ops:
            return set(), f"Invalid {flag_name} index {idx}: expected range 1..{total_ops}"
        out.add(idx)
    return out, None


def _select_operations_by_indexes(
    operations: list[dict[str, Any]],
    *,
    approve_ops: str | None,
    reject_ops: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Apply explicit CLI approve/reject selection by operation indexes."""
    approve_idx, err = _parse_operation_indexes(approve_ops, len(operations), flag_name="--approve-ops")
    if err:
        return [], [], err
    reject_idx, err = _parse_operation_indexes(reject_ops, len(operations), flag_name="--reject-ops")
    if err:
        return [], [], err
    overlap = approve_idx & reject_idx
    if overlap:
        return [], [], f"Conflicting indexes in --approve-ops and --reject-ops: {sorted(overlap)}"

    if not approve_idx and not reject_idx:
        return operations, [], None

    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        op2 = dict(op)
        if idx in reject_idx:
            op2["approval_state"] = "rejected"
            op2["decision_source"] = "human"
            op2["rejection_reason"] = "rejected_by_index"
            rejected.append(op2)
            continue
        if approve_idx and idx not in approve_idx:
            op2["approval_state"] = "rejected"
            op2["decision_source"] = "human"
            op2["rejection_reason"] = "not_in_approved_set"
            rejected.append(op2)
            continue
        op2["approval_state"] = "approved"
        op2["decision_source"] = "human"
        approved.append(op2)
    return approved, rejected, None


def _attach_decision_summary(report: dict[str, Any]) -> None:
    """Attach compact decision summary for CLI/report UX."""
    op_results = report.get("operation_results") or []
    policy_blocked = 0
    critic_blocked = 0
    human_blocked = 0
    if isinstance(op_results, list):
        for item in op_results:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("skipped_reason") or "")
            source = str(item.get("decision_source") or "policy")
            if reason.startswith("critic_verdict="):
                critic_blocked += 1
            elif reason.startswith("approval_state="):
                if source in {"human", "team"}:
                    human_blocked += 1
                else:
                    policy_blocked += 1
            elif reason in {"rejected_in_hybrid", "rejected_by_human", "rejected_by_index", "not_in_approved_set"}:
                human_blocked += 1
    # Fallback for legacy/partial payloads where operation_results may be absent.
    if policy_blocked == 0:
        policy_blocked = sum(
            1
            for d in (report.get("policy_decisions") or [])
            if isinstance(d, dict) and str(d.get("decision") or "").lower() == "deny"
        )
    if critic_blocked == 0:
        critic_blocked = sum(
            1
            for d in (report.get("critic_decisions") or [])
            if isinstance(d, dict) and str(d.get("verdict") or "").lower() == "deny"
        )
    report["decision_summary"] = {
        "blocked_by_policy": int(policy_blocked),
        "blocked_by_critic": int(critic_blocked),
        "blocked_by_human": int(human_blocked),
    }


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
    approve_ops: str | None = None,
    reject_ops: str | None = None,
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
        approved, _, skipped_reasons, skipped_files = _filter_executable_operations(approved)
        if not approved:
            op_results = []
            for target, reason in skipped_reasons.items():
                op_results.append(
                    {
                        "target_file": target,
                        "kind": None,
                        "approval_state": "approved",
                        "critic_verdict": "deny",
                        "decision_source": "team",
                        "applied": False,
                        "skipped_reason": reason,
                    }
                )
            report = {
                "message": "No executable approved operations after decision gate.",
                "skipped": skipped_files,
                "skipped_reasons": skipped_reasons,
                "operation_results": op_results,
            }
            _attach_decision_summary(report)
            attach_fix_telemetry(report, [])
            write_fix_report(path, report, quiet)
            return {
                "return_code": 0,
                "report": report,
                "operations": [],
                "modified": [],
                "verify_success": True,
                "agent_result": None,
            }
        patch_plan = dict(patch_plan, operations=approved)
        result = type(
            "R",
            (),
            {
                "output": {
                    "policy_decisions": [{"decision": "allow"} for _ in approved],
                    "critic_decisions": [],
                    "summary": {"risks": []},
                }
            },
        )()

        report, modified, verify_success = execute_fix_apply_stage(
            path,
            patch_plan,
            approved,
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

    planned_ops = list(operations)
    if approve_ops or reject_ops:
        approved_ops, rejected_ops, selection_error = _select_operations_by_indexes(
            operations,
            approve_ops=approve_ops,
            reject_ops=reject_ops,
        )
        if selection_error:
            report = {"error": selection_error}
            write_fix_report(path, report, quiet)
            return {
                "return_code": 1,
                "report": report,
                "operations": [],
                "modified": [],
                "verify_success": False,
                "agent_result": result,
                "dry_run": dry_run,
            }
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
    executable_ops, gate_skipped, gate_skipped_reasons, gate_skipped_files = _filter_executable_operations(operations)
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
        _attach_decision_summary(report)
        attach_fix_telemetry(report, planned_ops)
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
        out["report"]["critic_decisions"] = result.output.get("critic_decisions", [])
        out["report"]["operation_results"] = list(out["report"].get("operation_results", [])) + gate_skipped + rejected_meta
        if gate_skipped_reasons:
            out["report"]["skipped_reasons"] = gate_skipped_reasons
            out["report"]["skipped"] = gate_skipped_files
        if rejected_reasons:
            out["report"]["skipped_reasons"] = {
                **(out["report"].get("skipped_reasons") or {}),
                **rejected_reasons,
            }
            out["report"]["skipped"] = list(out["report"].get("skipped", [])) + rejected_files
        _attach_decision_summary(out["report"])
        attach_fix_telemetry(out["report"], planned_ops)
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
        report["operation_results"] = list(report.get("operation_results", [])) + gate_skipped
        report["skipped"] = list(report.get("skipped", [])) + gate_skipped_files
        report["skipped_reasons"] = {
            **(report.get("skipped_reasons") or {}),
            **gate_skipped_reasons,
        }
    if rejected_meta:
        report["operation_results"] = list(report.get("operation_results", [])) + rejected_meta
        report["skipped"] = list(report.get("skipped", [])) + rejected_files
        report["skipped_reasons"] = {
            **(report.get("skipped_reasons") or {}),
            **rejected_reasons,
        }
    _attach_decision_summary(report)
    write_fix_report(path, report, quiet)
    return build_fix_cycle_result(report, executable_ops, modified, verify_success, result)
