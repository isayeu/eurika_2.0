"""Helpers for fix cycle: operation filtering, index parsing, decision summary."""

from __future__ import annotations

from typing import Any

from .contracts import DecisionSummary, FixReport, OperationRecord
from .pipeline_model import PipelineStage


def infer_early_stages(early: dict[str, Any]) -> list[str]:
    """Infer pipeline stages completed from early-exit payload."""
    report = early.get("report") or {}
    if report.get("message") == "Patch plan has no operations. Cycle complete.":
        return [PipelineStage.INPUT.value, PipelineStage.PLAN.value]
    return [PipelineStage.INPUT.value]


def filter_executable_operations(
    operations: list[OperationRecord],
    *,
    team_override: bool = False,
) -> tuple[list[OperationRecord], list[dict[str, Any]], dict[str, str], list[str]]:
    """Apply hard decision gate: only approved + critic allow/review are executable.
    When team_override=True (apply-approved path), team approval bypasses critic verdict."""
    executable: list[OperationRecord] = []
    skipped_meta: list[dict[str, Any]] = []
    skipped_reasons: dict[str, str] = {}
    skipped_files: list[str] = []
    for op in operations:
        approval_state = str(op.get("approval_state", "approved"))
        critic_verdict = str(op.get("critic_verdict", "allow"))
        decision_source = str(op.get("decision_source") or "")
        target = str(op.get("target_file") or "")
        reason = ""
        if approval_state != "approved":
            reason = f"approval_state={approval_state}"
        elif team_override and decision_source == "team":
            pass  # team approved: bypass critic
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


def parse_operation_indexes(raw: str | None, total_ops: int, *, flag_name: str) -> tuple[set[int], str | None]:
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


def select_operations_by_indexes(
    operations: list[OperationRecord],
    *,
    approve_ops: str | None,
    reject_ops: str | None,
) -> tuple[list[OperationRecord], list[OperationRecord], str | None]:
    """Apply explicit CLI approve/reject selection by operation indexes."""
    approve_idx, err = parse_operation_indexes(approve_ops, len(operations), flag_name="--approve-ops")
    if err:
        return [], [], err
    reject_idx, err = parse_operation_indexes(reject_ops, len(operations), flag_name="--reject-ops")
    if err:
        return [], [], err
    overlap = approve_idx & reject_idx
    if overlap:
        return [], [], f"Conflicting indexes in --approve-ops and --reject-ops: {sorted(overlap)}"

    if not approve_idx and not reject_idx:
        return operations, [], None

    approved: list[OperationRecord] = []
    rejected: list[OperationRecord] = []
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


def attach_decision_summary(report: FixReport) -> None:
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
    summary: DecisionSummary = {
        "blocked_by_policy": int(policy_blocked),
        "blocked_by_critic": int(critic_blocked),
        "blocked_by_human": int(human_blocked),
    }
    report["decision_summary"] = summary
