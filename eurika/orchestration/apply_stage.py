"""Apply-stage helpers for fix-cycle orchestration."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from .contracts import FixReport, OperationRecord, PatchPlan, SafetyGatesPayload, TelemetryPayload
from .cycle_state import with_cycle_state
from .logging import get_logger

_LOG = get_logger("orchestration.apply_stage")


def build_fix_dry_run_result(
    path: Path,
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    result: Any,
) -> dict[str, Any]:
    """Build and persist dry-run report/result payload."""
    expls = [dict(op.get("explainability") or {}, verify_outcome=None) for op in operations]
    op_results = []
    for idx, op in enumerate(operations, start=1):
        op_results.append(
            {
                "index": idx,
                "target_file": op.get("target_file"),
                "kind": op.get("kind"),
                "approval_state": op.get("approval_state", "approved"),
                "critic_verdict": op.get("critic_verdict", "allow"),
                "applied": False,
                "skipped_reason": "dry_run",
            }
        )
    report = {
        "dry_run": True,
        "patch_plan": patch_plan,
        "modified": [],
        "verify": {"success": None},
        "operation_explanations": expls,
        "operation_results": op_results,
        "policy_decisions": result.output.get("policy_decisions", []),
        "critic_decisions": result.output.get("critic_decisions", []),
        "context_sources": result.output.get("context_sources"),
        "llm_hint_runtime": result.output.get("llm_hint_runtime"),
    }
    try:
        (path / "eurika_fix_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
    return with_cycle_state(
        {
            "return_code": 0,
            "report": report,
            "operations": operations,
            "modified": [],
            "verify_success": None,
            "agent_result": result,
            "dry_run": True,
        },
        is_error=False,
    )


def prepare_rescan_before(path: Path, backup_dir_name: str) -> Path:
    """Persist self_map snapshot before apply stage."""
    self_map_path = path / "self_map.json"
    rescan_before = path / backup_dir_name / "self_map_before.json"
    if self_map_path.exists():
        (path / backup_dir_name).mkdir(parents=True, exist_ok=True)
        rescan_before.write_text(self_map_path.read_text(encoding="utf-8"), encoding="utf-8")
    return rescan_before


def _compute_rescan_metrics(
    old_snap: Any,
    new_snap: Any,
    metrics_from_graph: Any,
) -> dict[str, Any]:
    """Compute verify_metrics dict from before/after snapshots."""
    trends: dict[str, Any] = {}
    metrics_before = metrics_from_graph(old_snap.graph, old_snap.smells, trends)
    metrics_after = metrics_from_graph(new_snap.graph, new_snap.smells, trends)
    before_score = metrics_before.get("score", 0)
    after_score = metrics_after.get("score", 0)
    return {
        "success": after_score >= before_score,
        "before_score": before_score,
        "after_score": after_score,
    }


def enrich_report_with_rescan(
    path: Path,
    report: FixReport,
    rescan_before: Path,
    quiet: bool,
    run_scan: Any,
    build_snapshot_from_self_map: Any,
    diff_architecture_snapshots: Any,
    metrics_from_graph: Any,
    rollback_patch: Any,
) -> None:
    """Add rescan_diff and verify_metrics to report; rollback if metrics worsened."""
    if not (report["verify"]["success"] and rescan_before.exists()):
        return
    if not quiet:
        _LOG.info("--- Step 4/4: rescan (compare before/after) ---")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        run_scan(path)
    self_map_after = path / "self_map.json"
    if not self_map_after.exists():
        return
    try:
        old_snap = build_snapshot_from_self_map(rescan_before)
        new_snap = build_snapshot_from_self_map(self_map_after)
        diff = diff_architecture_snapshots(old_snap, new_snap)
        report["rescan_diff"] = {
            "structures": diff["structures"],
            "smells": diff["smells"],
            "maturity": diff["maturity"],
            "centrality_shifts": diff.get("centrality_shifts", [])[:10],
        }
        vm = _compute_rescan_metrics(old_snap, new_snap, metrics_from_graph)
        report["verify_metrics"] = vm
        if vm["after_score"] < vm["before_score"] and report.get("run_id"):
            rb = rollback_patch(path, report["run_id"])
            report["rollback"] = {
                "done": True,
                "run_id": report["run_id"],
                "restored": rb.get("restored", []),
                "errors": rb.get("errors", []),
                "reason": "metrics_worsened",
            }
            report["verify"]["success"] = False
    except Exception as e:
        report["rescan_diff"] = {"error": "diff failed"}
        report["verify_metrics"] = {"success": None, "error": str(e)}


def append_fix_cycle_memory(
    path: Path,
    result: Any,
    operations: list[OperationRecord],
    report: FixReport,
    verify_success: Any,
) -> None:
    """Append learning and patch events to memory."""
    from eurika.storage import ProjectMemory, SessionMemory

    try:
        op_results = report.get("operation_results") or []
        learning_operations: list[OperationRecord] = []
        for idx, op in enumerate(operations):
            op2 = dict(op)
            if idx < len(op_results) and isinstance(op_results[idx], dict):
                op_result = op_results[idx]
                op2["execution_outcome"] = op_result.get("execution_outcome")
                op2["execution_reason"] = op_result.get("skipped_reason")
                op2["applied"] = op_result.get("applied", False)
            learning_operations.append(op2)

        memory = ProjectMemory(path)
        summary = result.output.get("summary", {}) or {}
        risks = list(summary.get("risks", []))
        modified = report.get("modified", [])
        modules_for_learning = modified or [
            str(op.get("target_file"))
            for op in operations
            if op.get("target_file")
        ]
        if verify_success is False and operations:
            SessionMemory(path).record_verify_failure(operations)
        if verify_success is True and operations:
            SessionMemory(path).record_verify_success(operations)
        if operations:
            memory.learning.append(
                project_root=path,
                modules=modules_for_learning,
                operations=learning_operations,
                risks=risks,
                verify_success=verify_success,
            )
            from eurika.storage.global_memory import append_learn_to_global
            append_learn_to_global(
                path,
                modules_for_learning,
                learning_operations,
                risks,
                verify_success,
            )
        memory.events.append_event(
            type="patch",
            input={"operations_count": len(operations)},
            output={
                "modified": modified,
                "skipped": report.get("skipped", []),
                "run_id": report.get("run_id"),
                "verify_success": verify_success,
                "verify_duration_ms": report.get("verify_duration_ms"),
            },
            result=verify_success,
        )
    except Exception:
        pass


def write_fix_report(path: Path, report: FixReport, quiet: bool) -> None:
    """Persist eurika_fix_report.json report."""
    try:
        report_path = path / "eurika_fix_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if not quiet:
            _LOG.info(f"eurika_fix_report.json written to {report_path}")
    except Exception:
        pass


def _median_verify_time_ms(path: Path, current_ms: int) -> int | None:
    """Compute median verify_duration_ms from last 10 patch events (ROADMAP 2.7.8)."""
    try:
        from eurika.storage import ProjectMemory

        memory = ProjectMemory(path)
        events = memory.events.recent_events(limit=10, types=("patch",))
        durations = []
        for e in events:
            out = (e.output or {}) if hasattr(e, "output") else {}
            ms = out.get("verify_duration_ms")
            if isinstance(ms, (int, float)) and ms is not None:
                durations.append(int(ms))
        durations.append(current_ms)
        if not durations:
            return None
        durations.sort()
        mid = len(durations) // 2
        return int(durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2)
    except Exception:
        return None


def attach_fix_telemetry(report: FixReport, operations: list[OperationRecord], path: Path | None = None) -> None:
    """Attach operational telemetry and safety-gate summary to fix report (ROADMAP 2.7.8)."""
    policy_total = len(report.get("policy_decisions", []) or [])
    ops_total = len(operations) or policy_total
    modified = report.get("modified", []) or []
    skipped = report.get("skipped", []) or []
    rollback_done = bool((report.get("rollback") or {}).get("done"))
    verify_payload = report.get("verify")
    verify_success_raw = (
        verify_payload.get("success")
        if isinstance(verify_payload, dict)
        else None
    )
    verify_ran = verify_success_raw is not None
    verify_required = verify_ran
    verify_duration_ms = report.get("verify_duration_ms")
    if verify_duration_ms is None:
        verify_duration_ms = 0
    if not skipped and isinstance(report.get("message"), str):
        if report["message"].startswith("All operations rejected by user/policy."):
            skipped = [d.get("target_file") for d in (report.get("policy_decisions") or []) if d.get("target_file")]
    campaign_skipped = int(report.get("campaign_skipped") or 0)
    session_skipped = int(report.get("session_skipped") or 0)
    skipped_count = len(skipped) + campaign_skipped + session_skipped
    apply_rate = (len(modified) / ops_total) if ops_total else 0.0
    no_op_rate = (skipped_count / ops_total) if ops_total else 0.0
    rollback_rate = (1.0 if rollback_done else 0.0) if verify_required else 0.0
    telemetry: TelemetryPayload = {
        "operations_total": ops_total,
        "modified_count": len(modified),
        "skipped_count": skipped_count,
        "apply_rate": round(apply_rate, 4),
        "no_op_rate": round(no_op_rate, 4),
        "rollback_rate": rollback_rate,
        "verify_duration_ms": int(verify_duration_ms),
    }
    if path is not None:
        median_ms = _median_verify_time_ms(path, int(verify_duration_ms))
        if median_ms is not None:
            telemetry["median_verify_time_ms"] = median_ms
    report["telemetry"] = telemetry
    safety_gates: SafetyGatesPayload = {
        "verify_required": verify_required,
        "auto_rollback_enabled": verify_required,
        "verify_ran": verify_ran,
        "verify_passed": (bool(verify_success_raw) if verify_ran else None),
        "rollback_done": rollback_done,
    }
    report["safety_gates"] = safety_gates


def execute_fix_apply_stage(
    path: Path,
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    *,
    session_id: str | None,
    quiet: bool,
    verify_cmd: str | None,
    verify_timeout: int | None,
    backup_dir: str,
    apply_and_verify: Any,
    run_scan: Any,
    build_snapshot_from_self_map: Any,
    diff_architecture_snapshots: Any,
    metrics_from_graph: Any,
    rollback_patch: Any,
    result: Any,
) -> tuple[FixReport, list[str], Any]:
    """Apply patch plan, enrich with rescan metrics, append memory, and persist report.

    Safety (ROADMAP 2.7.7): mandatory verify-gate, auto_rollback on verify fail,
    backup=True so no partially-applied invalid sessions.
    """
    if not quiet:
        _LOG.info("--- Step 3/4: patch & verify ---")
    rescan_before = prepare_rescan_before(path, backup_dir)
    checkpoint = None
    checkpoint_id = None
    try:
        from eurika.storage.campaign_checkpoint import create_campaign_checkpoint

        checkpoint = create_campaign_checkpoint(path, operations=operations, session_id=session_id)
        checkpoint_id = str((checkpoint or {}).get("checkpoint_id") or "")
        if checkpoint_id:
            _LOG.debug("campaign checkpoint created: %s", checkpoint_id)
    except Exception:
        checkpoint = None
        checkpoint_id = None
    from patch_engine_verify_patch import get_verify_timeout

    resolved_timeout = get_verify_timeout(path, override=verify_timeout)
    report = apply_and_verify(path, patch_plan, backup=True, verify=True, verify_timeout=resolved_timeout, verify_cmd=verify_cmd, auto_rollback=True)
    verify_outcome = report["verify"].get("success")
    expls = []
    op_results = []
    modified_set = set(report.get("modified") or [])
    skipped_reasons = report.get("skipped_reasons") or {}
    for op in operations:
        target_file = str(op.get("target_file") or "")
        skipped_reason = skipped_reasons.get(target_file)
        applied = bool(target_file and target_file in modified_set and skipped_reason is None)
        if not applied:
            execution_outcome = "not_applied"
        elif verify_outcome is True:
            execution_outcome = "verify_success"
        elif verify_outcome is False:
            execution_outcome = "verify_fail"
        else:
            execution_outcome = "verify_unknown"

        expl = dict(op.get("explainability") or {})
        expl["verify_outcome"] = verify_outcome
        expl["execution_outcome"] = execution_outcome
        expls.append(expl)
        op_results.append(
            {
                "target_file": target_file,
                "kind": op.get("kind"),
                "approval_state": op.get("approval_state", "approved"),
                "critic_verdict": op.get("critic_verdict", "allow"),
                "applied": applied,
                "execution_outcome": execution_outcome,
                "skipped_reason": (skipped_reason or ("not_modified" if not applied else None)),
            }
        )
    report["operation_explanations"] = expls
    report["operation_results"] = op_results
    report["policy_decisions"] = result.output.get("policy_decisions", [])
    report["critic_decisions"] = result.output.get("critic_decisions", [])
    report["context_sources"] = result.output.get("context_sources")
    report["llm_hint_runtime"] = result.output.get("llm_hint_runtime")
    if checkpoint_id:
        report["campaign_checkpoint"] = {
            "checkpoint_id": checkpoint_id,
            "reused": bool((checkpoint or {}).get("reused")),
        }
    attach_fix_telemetry(report, operations, path)
    enrich_report_with_rescan(
        path, report, rescan_before, quiet, run_scan,
        build_snapshot_from_self_map, diff_architecture_snapshots,
        metrics_from_graph, rollback_patch,
    )
    modified = report.get("modified", [])
    verify_success = report["verify"]["success"]
    if checkpoint_id:
        try:
            from eurika.storage.campaign_checkpoint import attach_run_to_checkpoint

            cp = attach_run_to_checkpoint(
                path,
                checkpoint_id,
                run_id=report.get("run_id"),
                verify_success=verify_success,
                modified=modified,
            )
            if isinstance(cp, dict):
                report["campaign_checkpoint"] = {
                    "checkpoint_id": checkpoint_id,
                    "status": cp.get("status"),
                    "run_ids": cp.get("run_ids", []),
                    "reused": bool(cp.get("reused")),
                }
        except Exception:
            pass
    append_fix_cycle_memory(path, result, operations, report, verify_success)
    write_fix_report(path, report, quiet)
    return report, modified, verify_success


def build_fix_cycle_result(
    report: FixReport,
    operations: list[OperationRecord],
    modified: list[str],
    verify_success: Any,
    result: Any,
) -> dict[str, Any]:
    """Build final run_fix_cycle result payload."""
    return_code = 1 if report.get("errors") or not report["verify"].get("success") else 0
    return with_cycle_state(
        {
            "return_code": return_code,
            "report": report,
            "operations": operations,
            "modified": modified,
            "verify_success": verify_success,
            "agent_result": result,
            "dry_run": False,
        },
        is_error=(return_code != 0),
    )
