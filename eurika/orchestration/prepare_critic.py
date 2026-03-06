"""Critic pass for prepare stage (extracted from prepare.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import OperationRecord


def run_critic_pass(
    operations: list[OperationRecord],
    *,
    runtime_mode: str,
    project_root: Path | None = None,
) -> tuple[list[OperationRecord], list[dict[str, Any]]]:
    """Attach critic verdict to each operation before apply."""
    from eurika.agent import is_whitelisted_for_auto

    updated: list[OperationRecord] = []
    decisions: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        op2 = dict(op)
        kind = str(op2.get("kind") or "")
        target = str(op2.get("target_file") or "")
        expl = op2.get("explainability") or {}
        risk = str(expl.get("risk") or op2.get("risk") or "unknown")
        diff = str(op2.get("diff") or "")
        approval_state = str(op2.get("approval_state") or "pending")
        whitelisted_auto = is_whitelisted_for_auto(op2, project_root)

        verdict = "allow"
        reason = "passed critic checks"
        if approval_state == "rejected":
            verdict = "deny"
            reason = "rejected by policy/human"
        elif "_extracted_extracted" in target:
            verdict = "deny"
            reason = "blocked repeated extracted chain"
        elif kind == "refactor_code_smell" and "# TODO" in diff:
            verdict = "deny"
            reason = "blocked todo-only patch candidate"
        elif risk == "high" and runtime_mode in {"hybrid", "auto"}:
            if whitelisted_auto:
                pass  # whitelist bypass: keep verdict=allow (polygon drills)
            else:
                verdict = "review"
                reason = "high-risk operation requires explicit review"
        elif (
            kind in {"split_module", "refactor_module", "extract_class"}
            and risk in {"medium", "high"}
            and runtime_mode in {"hybrid", "auto"}
        ):
            if whitelisted_auto:
                pass
            else:
                verdict = "review"
                reason = "structural refactor requires review"

        op2["critic_verdict"] = verdict
        op2["critic_reason"] = reason
        op2["decision_source"] = op2.get("decision_source", "policy")
        if verdict == "deny":
            op2["approval_state"] = "rejected"
        elif verdict == "review" and op2.get("approval_state") == "approved":
            op2["approval_state"] = "pending"

        updated.append(op2)
        decisions.append(
            {
                "index": idx,
                "target_file": target,
                "kind": kind,
                "verdict": verdict,
                "reason": reason,
                "risk": risk,
            }
        )
    return updated, decisions
