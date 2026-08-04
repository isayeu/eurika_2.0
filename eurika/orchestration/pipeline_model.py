"""Formal pipeline model for fix cycle: Input → Plan → Validate → Apply → Verify.

P0.3 / R2: Explicit pipeline and state machine to remove reasoning «black box» effect.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    """Formal stages of the fix-cycle reasoning pipeline."""

    INPUT = "input"  # Scan + diagnose: gather observations, summary, smells
    PLAN = "plan"  # Extract patch plan, policy, memory, critic
    VALIDATE = "validate"  # Decision gate: approval + critic verdict
    APPLY = "apply"  # Write patches to disk
    VERIFY = "verify"  # Run tests / verification


# Linear transition order for valid pipeline progression
_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.INPUT,
    PipelineStage.PLAN,
    PipelineStage.VALIDATE,
    PipelineStage.APPLY,
    PipelineStage.VERIFY,
)


def next_stage(current: PipelineStage) -> PipelineStage | None:
    """Return next stage in pipeline order; None if current is last."""
    try:
        idx = _STAGE_ORDER.index(current)
        if idx + 1 < len(_STAGE_ORDER):
            return _STAGE_ORDER[idx + 1]
    except ValueError:
        pass
    return None


def is_valid_stage_sequence(stages: list[str]) -> bool:
    """Check that stages form a valid prefix of INPUT → PLAN → VALIDATE → APPLY → VERIFY."""
    order_values = [s.value for s in _STAGE_ORDER]
    last_idx = -1
    for stage_val in stages:
        if stage_val not in order_values:
            return False
        idx = order_values.index(stage_val)
        if idx <= last_idx:
            return False
        last_idx = idx
    return True


def build_pipeline_trace(stages: list[str]) -> dict[str, Any]:
    """Build observable pipeline trace for reports."""
    return {
        "pipeline_stages": list(stages),
        "pipeline_model": "Input → Plan → Validate → Apply → Verify",
    }


def attach_pipeline_trace(report: dict[str, Any], stages: list[str]) -> None:
    """Attach pipeline trace to report dict (mutates in place)."""
    trace = build_pipeline_trace(stages)
    report["pipeline_stages"] = trace["pipeline_stages"]
    report["pipeline_model"] = trace["pipeline_model"]
