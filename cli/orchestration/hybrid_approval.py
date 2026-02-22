"""Interactive approve/reject helpers for hybrid runtime mode."""

from __future__ import annotations

import sys
from typing import Any

from .logging import get_logger

_LOG = get_logger("orchestration.hybrid_approval")


def read_hybrid_choice(prompt: str) -> str:
    """Read one valid interactive choice for hybrid approve/reject flow."""
    allowed = {"a", "r", "A", "R", "s"}
    while True:
        choice = input(prompt).strip() or "a"
        if choice in allowed:
            return choice
        _LOG.warning("Use one of: a, r, A, R, s")


def select_hybrid_operations(
    operations: list[dict[str, Any]],
    *,
    quiet: bool,
    non_interactive: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Interactive approval flow for hybrid mode."""
    if not operations or quiet:
        return operations, []
    if non_interactive or not sys.stdin.isatty():
        approved = [op for op in operations if str(op.get("approval_state", "approved")) == "approved"]
        rejected = [op for op in operations if str(op.get("approval_state", "approved")) == "rejected"]
        return approved, rejected
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        kind = op.get("kind", "?")
        target = op.get("target_file", "?")
        risk = (op.get("explainability") or {}).get("risk", "unknown")
        prompt = (
            f"[{idx}/{len(operations)}] {kind} -> {target} (risk={risk}) "
            "[a]pprove/[r]eject/[A]ll approve/[R]eject rest/[s]kip prompt: "
        )
        choice = read_hybrid_choice(prompt)
        if choice == "a":
            op2 = dict(op)
            op2["approval_state"] = "approved"
            op2["decision_source"] = "human"
            approved.append(op2)
        elif choice == "r":
            op2 = dict(op)
            op2["approval_state"] = "rejected"
            op2["decision_source"] = "human"
            rejected.append(op2)
        elif choice == "A":
            op2 = dict(op)
            op2["approval_state"] = "approved"
            op2["decision_source"] = "human"
            approved.append(op2)
            for tail in operations[idx:]:
                tail2 = dict(tail)
                tail2["approval_state"] = "approved"
                tail2["decision_source"] = "human"
                approved.append(tail2)
            break
        elif choice == "R":
            op2 = dict(op)
            op2["approval_state"] = "rejected"
            op2["decision_source"] = "human"
            rejected.append(op2)
            for tail in operations[idx:]:
                tail2 = dict(tail)
                tail2["approval_state"] = "rejected"
                tail2["decision_source"] = "human"
                rejected.append(tail2)
            break
        elif choice == "s":
            state = str(op.get("approval_state", "pending"))
            if state == "rejected":
                rejected.append(dict(op))
            elif state == "approved":
                approved.append(dict(op))
    return approved, rejected
