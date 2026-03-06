"""
Planning analysis: graph → smells, priorities, targets (ROADMAP v3.0 §5.6).

Delegates to core_extracted.detect_smells and graph_ops.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from eurika.reasoning.planner.core_extracted import detect_smells

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def analyze(
    graph: "ProjectGraph",
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
    root = Path(project_root) if project_root else None
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
    return {"smells": smells, "priorities": priorities, "targets": targets}
