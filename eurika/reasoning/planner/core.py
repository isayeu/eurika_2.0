"""
Planner core facade (ROADMAP v3.0 §5.6).

Single entry point: analyze, detect_smells, propose_actions.
Delegates to planner submodules and architecture_planner.
"""
from __future__ import annotations
from eurika.reasoning.planner.core_extracted import detect_smells
from typing import TYPE_CHECKING, Any, Dict, List, Optional
if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph

def analyze(
    graph: 'ProjectGraph',
    *,
    summary_risks: Optional[List[str]] = None,
    trends: Optional[Dict[str, str]] = None,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    top_n: int = 8,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run planning analysis: smells + priorities from graph.

    Returns dict with: smells, priorities, targets.
    When project_root is provided, decay (failure_penalty, freshness_bonus) is applied.
    """
    from eurika.reasoning.graph_ops import priority_from_graph, targets_from_graph
    smells = detect_smells(graph)
    root = str(project_root) if project_root else None
    priorities = priority_from_graph(
        graph, smells, summary_risks, top_n,
        learning_stats=learning_stats,
        project_root=root,
    )
    targets = targets_from_graph(
        graph, smells, summary_risks, top_n,
        learning_stats=learning_stats,
        project_root=root,
    )
    return {'smells': smells, 'priorities': priorities, 'targets': targets}

def propose_actions(project_root: str, summary: Dict[str, Any], smells: List[Any], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], *, learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> Any:
    """
    Propose action plan from architecture analysis.

    Delegates to architecture_planner.build_action_plan.
    """
    from architecture_planner import build_action_plan
    return build_action_plan(project_root=str(project_root), summary=summary, smells=smells, history_info=history_info, priorities=priorities, learning_stats=learning_stats)

# TODO: Refactor eurika/reasoning/planner/core.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - OSS (django): django/template/backends/django.py — Consider splitting into smaller modules; extract coherent sub-responsibilities.
# - Extract from imports: architecture_planner.py.
# - Consider grouping callers: eurika/core/pipeline.py, eurika/core/snapshot.py, eurika/evolution/diff.py.
# - Introduce facade for callers: architecture_pipeline.py, eurika/core/pipeline.py, eurika/core/snapshot.py....
# - Extract architecture-related logic into `architecture_planner_core.py`
# - Group planning algorithms and strategies into `planning_algorithms.py`
# - Separate snapshot creation and handling logic into `snapshot_handler.py`
