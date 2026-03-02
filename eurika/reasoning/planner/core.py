"""
Planner core facade (ROADMAP v3.0 §5.6).

Single entry point: analyze, detect_smells, propose_actions.
Delegates to planner submodules and architecture_planner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def detect_smells(graph: "ProjectGraph") -> List[Any]:
    """
    Detect architectural smells from project graph.

    Delegates to eurika.smells.models.detect_smells.
    """
    from eurika.smells.models import detect_smells as _detect

    return _detect(graph)


def analyze(
    graph: "ProjectGraph",
    *,
    summary_risks: Optional[List[str]] = None,
    trends: Optional[Dict[str, str]] = None,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    top_n: int = 8,
) -> Dict[str, Any]:
    """
    Run planning analysis: smells + priorities from graph.

    Returns dict with: smells, priorities, targets.
    """
    from eurika.reasoning.graph_ops import priority_from_graph, targets_from_graph

    smells = detect_smells(graph)
    priorities = priority_from_graph(
        graph, smells, summary_risks, top_n, learning_stats=learning_stats
    )
    targets = targets_from_graph(
        graph, smells, summary_risks, top_n, learning_stats=learning_stats
    )
    return {
        "smells": smells,
        "priorities": priorities,
        "targets": targets,
    }


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
    from architecture_planner import build_action_plan

    return build_action_plan(
        project_root=str(project_root),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        learning_stats=learning_stats,
    )
