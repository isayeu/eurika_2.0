"""
Refactoring plan generation (ROADMAP §7 — мини-AI).

Produces a short, ordered list of concrete refactoring steps from
summary, optional recommendations (from build_recommendations), and optional history.
Heuristic-only for now; LLM can be added later.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_SMELL_HINTS: Dict[str, str] = {
    "god_module": "consider splitting into smaller modules or extracting sub-responsibilities",
    "bottleneck": "introduce facade or adapter to reduce fan-in; avoid single point of failure",
    "hub": "extract coherent sub-graphs or split by domain/layer",
    "cyclic_dependency": "invert dependencies or introduce interfaces to break the cycle",
}


def _risks_to_steps(summary: Dict[str, Any]) -> List[str]:
    """Turn summary['risks'] (e.g. 'god_module @ path (severity=11)') into plan steps."""
    steps: List[str] = []
    seen: set = set()
    risks = summary.get("risks") or []
    for r in risks:
        s = r.strip()
        if " @ " not in s:
            continue
        type_part, rest = s.split(" @ ", 1)
        smell_type = type_part.strip()
        module_part = re.sub(r"\s*\(severity=[\d.]+\)\s*$", "", rest).strip()
        if not module_part:
            continue
        hint = _SMELL_HINTS.get(smell_type, "review and refactor")
        key = (module_part, smell_type)
        if key in seen:
            continue
        seen.add(key)
        steps.append(f"{module_part}: address {smell_type} — {hint}.")
    return steps


def suggest_refactor_plan(
    summary: Dict[str, Any],
    recommendations: Optional[List[str]] = None,
    history_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Return a short refactoring plan (numbered list).

    - If recommendations is provided (e.g. from build_recommendations), use those.
    - Otherwise derive steps from summary['risks'] with per-smell hints.
    - history_info is reserved for future use (e.g. prioritize by regressions).
    """
    if history_info is None:
        history_info = {}
    lines: List[str] = []
    if recommendations:
        for i, rec in enumerate(recommendations[:15], start=1):
            lines.append(f"{i}. {rec}")
    else:
        steps = _risks_to_steps(summary)
        for i, step in enumerate(steps[:15], start=1):
            lines.append(f"{i}. {step}")
    if not lines:
        return "No refactoring steps suggested (no risks or recommendations)."
    return "\n".join(lines)
