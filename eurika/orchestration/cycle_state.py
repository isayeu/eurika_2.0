"""Formal cycle execution state model (idle/thinking/error/done) for R2."""

from __future__ import annotations

from enum import Enum
from typing import Any


class CycleState(str, Enum):
    """Formal runtime state for doctor/fix cycle execution."""

    IDLE = "idle"
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"


# Allowed terminal transitions: thinking -> done | error
# (idle is pre-execution; result only carries terminal state)
_ALLOWED_HISTORY: tuple[tuple[str, ...], ...] = (
    (CycleState.THINKING.value, CycleState.DONE.value),
    (CycleState.THINKING.value, CycleState.ERROR.value),
)


def with_cycle_state(result: dict[str, Any], *, is_error: bool) -> dict[str, Any]:
    """Add state and state_history to cycle result. Call once when cycle terminates."""
    state = CycleState.ERROR if is_error else CycleState.DONE
    history = [CycleState.THINKING.value, state.value]
    out = dict(result)
    out["state"] = state.value
    out["state_history"] = history
    return out


def is_valid_state_history(history: list[str]) -> bool:
    """Validate that state_history reflects an allowed transition."""
    if len(history) != 2:
        return False
    return tuple(history) in _ALLOWED_HISTORY


def is_error_result(result: dict[str, Any]) -> bool:
    """Infer error from fix/doctor result shape."""
    if result.get("error"):
        return True
    if result.get("return_code", 0) != 0:
        return True
    report = result.get("report")
    if isinstance(report, dict) and report.get("error"):
        return True
    if isinstance(report, dict):
        verify = report.get("verify") or {}
        if verify.get("success") is False:
            return True
    return False
