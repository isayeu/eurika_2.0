"""Shim: re-export from planner.heuristics (ROADMAP v3.0 Stage 1)."""
from eurika.reasoning.planner.heuristics import (  # noqa: F401
    DIFF_HINTS,
    EXTRACT_CLASS_SKIP_PATTERNS,
    FACADE_MODULES,
    SMELL_ACTION_SEP,
    STEP_KIND_TO_ACTION,
    diff_hints_for,
    disabled_smell_actions_from_env,
    fallback_kind_for_low_success,
)

__all__ = [
    "DIFF_HINTS",
    "EXTRACT_CLASS_SKIP_PATTERNS",
    "FACADE_MODULES",
    "SMELL_ACTION_SEP",
    "STEP_KIND_TO_ACTION",
    "diff_hints_for",
    "disabled_smell_actions_from_env",
    "fallback_kind_for_low_success",
]
