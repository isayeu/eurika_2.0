"""
Propose action plan from architecture analysis (ROADMAP v3.0 §5.6).

Delegates to architecture_planner.build_action_plan.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def propose_actions(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[Any],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
    *,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Any:
    """
    Propose action plan from architecture analysis.

    Delegates to architecture_planner.build_action_plan.
    """
    from eurika.reasoning.planner.facade import build_action_plan

    return build_action_plan(
        project_root=str(project_root),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        learning_stats=learning_stats,
    )
