"""Rule constants and helpers for architecture planner."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

SMELL_ACTION_SEP = "|"

STEP_KIND_TO_ACTION: Dict[str, str] = {
    "split_module": "split_module",
    "introduce_facade": "introduce_facade",
    "split_responsibility": "refactor_module",
    "break_cycle": "refactor_dependencies",
    "refactor_module": "refactor_module",
}

FACADE_MODULES = {"patch_engine.py", "patch_apply.py"}

# Files that break with extract_class (CYCLE_REPORT #34: static methods lose kwargs, _ok/_err)
EXTRACT_CLASS_SKIP_PATTERNS: tuple[str, ...] = ("*tool_contract*.py",)

DIFF_HINTS: Dict[tuple[str, str], List[str]] = {
    ("god_module", "split_module"): [
        "Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).",
        "Identify distinct concerns and split this module into focused units.",
        "Reduce total degree (fan-in + fan-out) via extraction.",
    ],
    ("god_module", "refactor_module"): [
        "Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).",
        "Identify distinct concerns and split this module into focused units.",
        "Reduce total degree (fan-in + fan-out) via extraction.",
    ],
    ("bottleneck", "introduce_facade"): [
        "Introduce a facade or boundary to reduce direct fan-in.",
        "Create a stable public API for this module; let internal structure evolve independently.",
        "Limit the number of modules that import this file directly.",
    ],
    ("hub", "refactor_module"): [
        "Split outgoing dependencies across clearer layers or services.",
        "Introduce intermediate abstractions to decouple from concrete implementations.",
        "Align with semantic roles and system topology.",
    ],
    ("hub", "split_module"): [
        "Split outgoing dependencies across clearer layers or services.",
        "Extract coherent sub-graphs by domain or layer.",
        "Reduce fan-out via extraction into focused modules.",
    ],
    ("cyclic_dependency", "refactor_dependencies"): [
        "Break import cycles via inversion of dependencies or adapters.",
        "Extract shared interfaces; depend on abstractions, not implementations.",
        "Consider introducing a shared-core module used by both sides.",
    ],
}


def diff_hints_for(smell_type: str, action_kind: str) -> List[str]:
    """Return tailored diff hints for (smell_type, action_kind)."""
    key = (smell_type, action_kind)
    if key in DIFF_HINTS:
        return DIFF_HINTS[key]
    if smell_type != "unknown":
        for (s, _), hints in DIFF_HINTS.items():
            if s == smell_type:
                return hints
    return [
        "Split responsibilities or introduce a facade where appropriate.",
        "Reduce excessive fan-in/fan-out.",
        "Align with semantic roles and system topology.",
    ]


def disabled_smell_actions_from_env() -> set[str]:
    """
    Parse disabled smell-action pairs from env.

    Format:
      EURIKA_DISABLE_SMELL_ACTIONS="hub|split_module,long_function|extract_nested_function"
    """
    raw = os.environ.get("EURIKA_DISABLE_SMELL_ACTIONS", "").strip()
    if not raw:
        return set()
    return {
        item.strip()
        for item in raw.split(",")
        if item.strip() and SMELL_ACTION_SEP in item
    }


def fallback_kind_for_low_success(smell_type: str, action_kind: str) -> Optional[str]:
    """Return safer fallback action for low-success smell/action pairs."""
    fallbacks = {
        ("hub", "split_module"): "refactor_module",
    }
    return fallbacks.get((smell_type, action_kind))
