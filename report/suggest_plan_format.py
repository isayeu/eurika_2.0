"""Format suggest-plan data as text (R1 Domain vs Presentation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def get_suggest_plan_text(project_root: Path, window: int = 5) -> str:
    """
    Presentation: get suggest-plan data and format for CLI/UI.
    Domain: eurika.api.get_suggest_plan_data returns structure; this layer renders it.
    """
    from eurika.api import get_suggest_plan_data

    data = get_suggest_plan_data(project_root, window=window)
    return format_suggest_plan(data)


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
