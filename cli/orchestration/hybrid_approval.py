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
    if non_interactive or not operations or quiet or not sys.stdin.isatty():
        return operations, []
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
            approved.append(op)
        elif choice == "r":
            rejected.append(op)
        elif choice == "A":
            approved.append(op)
            approved.extend(operations[idx:])
            break
        elif choice == "R":
            rejected.append(op)
            rejected.extend(operations[idx:])
            break
        elif choice == "s":
            approved.append(op)
    return approved, rejected
