"""Apply-stage helpers for fix-cycle orchestration."""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any


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
    report: dict[str, Any],
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
        print("--- Step 4/4: rescan (compare before/after) ---", file=sys.stderr)
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
    operations: list[dict[str, Any]],
    report: dict[str, Any],
    verify_success: Any,
) -> None:
    """Append learning and patch events to memory."""
    from eurika.storage import ProjectMemory

    try:
        memory = ProjectMemory(path)
        summary = result.output.get("summary", {}) or {}
        risks = list(summary.get("risks", []))
        modified = report.get("modified", [])
        # Only record learning when we actually modified files (skip inflates success for unapplied ops)
        if modified:
            memory.learning.append(
                project_root=path,
                modules=modified,
                operations=operations,
                risks=risks,
                verify_success=verify_success,
            )
        memory.events.append_event(
            type="patch",
            input={"operations_count": len(operations)},
            output={
                "modified": modified,
                "run_id": report.get("run_id"),
                "verify_success": verify_success,
            },
            result=verify_success,
        )
    except Exception:
        pass


def write_fix_report(path: Path, report: dict[str, Any], quiet: bool) -> None:
    """Persist eurika_fix_report.json report."""
    try:
        report_path = path / "eurika_fix_report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if not quiet:
            print(f"eurika_fix_report.json written to {report_path}", file=sys.stderr)
    except Exception:
        pass


def attach_fix_telemetry(report: dict[str, Any], operations: list[dict[str, Any]]) -> None:
    """Attach operational telemetry and safety-gate summary to fix report."""
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
    apply_rate = (len(modified) / ops_total) if ops_total else 0.0
    no_op_rate = (len(skipped) / ops_total) if ops_total else 0.0
    rollback_rate = (1.0 if rollback_done else 0.0) if verify_required else 0.0
    report["telemetry"] = {
        "operations_total": ops_total,
        "modified_count": len(modified),
        "skipped_count": len(skipped),
        "apply_rate": round(apply_rate, 4),
        "no_op_rate": round(no_op_rate, 4),
        "rollback_rate": rollback_rate,
        "verify_duration_ms": int(verify_duration_ms),
    }
    report["safety_gates"] = {
        "verify_required": verify_required,
        "auto_rollback_enabled": verify_required,
        "verify_ran": verify_ran,
        "verify_passed": (bool(verify_success_raw) if verify_ran else None),
        "rollback_done": rollback_done,
    }


def execute_fix_apply_stage(
    path: Path,
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    quiet: bool,
    verify_cmd: str | None,
    backup_dir: str,
    apply_and_verify: Any,
    run_scan: Any,
    build_snapshot_from_self_map: Any,
    diff_architecture_snapshots: Any,
    metrics_from_graph: Any,
    rollback_patch: Any,
    result: Any,
) -> tuple[dict[str, Any], list[str], Any]:
    """Apply patch plan, enrich with rescan metrics, append memory, and persist report."""
    if not quiet:
        print("--- Step 3/4: patch & verify ---", file=sys.stderr)
    rescan_before = prepare_rescan_before(path, backup_dir)
    report = apply_and_verify(path, patch_plan, backup=True, verify=True, verify_cmd=verify_cmd, auto_rollback=True)
    report["operation_explanations"] = [op.get("explainability", {}) for op in operations]
    report["policy_decisions"] = result.output.get("policy_decisions", [])
    attach_fix_telemetry(report, operations)
    enrich_report_with_rescan(
        path, report, rescan_before, quiet, run_scan,
        build_snapshot_from_self_map, diff_architecture_snapshots,
        metrics_from_graph, rollback_patch,
    )
    modified = report.get("modified", [])
    verify_success = report["verify"]["success"]
    append_fix_cycle_memory(path, result, operations, report, verify_success)
    write_fix_report(path, report, quiet)
    return report, modified, verify_success


def build_fix_cycle_result(
    report: dict[str, Any],
    operations: list[dict[str, Any]],
    modified: list[str],
    verify_success: Any,
    result: Any,
) -> dict[str, Any]:
    """Build final run_fix_cycle result payload."""
    return_code = 1 if report.get("errors") or not report["verify"].get("success") else 0
    return {
        "return_code": return_code,
        "report": report,
        "operations": operations,
        "modified": modified,
        "verify_success": verify_success,
        "agent_result": result,
        "dry_run": False,
    }
