"""Format suggest-plan data as text (R1 Domain vs Presentation)."""

from __future__ import annotations

from typing import Any


def format_suggest_plan(data: dict[str, Any]) -> str:
    """Format suggest-plan structure as numbered list (presentation layer)."""
    if data.get("error"):
        return f"Error: {data.get('error', 'unknown')}"
    from eurika.reasoning.refactor_plan import suggest_refactor_plan

    return suggest_refactor_plan(
        data.get("summary") or {},
        recommendations=data.get("recommendations"),
        history_info=data.get("history"),
    )
