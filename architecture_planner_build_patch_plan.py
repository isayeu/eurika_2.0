"""Extracted from parent module to reduce complexity."""
from typing import Any, Dict, List, Optional
from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_analysis import index_smells_by_node
from eurika.reasoning.planner_patch_ops import build_patch_operations
from patch_plan import PatchPlan

def build_patch_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None, graph: Optional['ProjectGraph']=None, self_map: Optional[Dict[str, Any]]=None) -> PatchPlan:
    """
    Build a first-approximation PatchPlan from diagnostics.

    v0.1: for each top-priority module, create a textual patch operation
    that describes the intended refactor. Uses smell types and step kinds
    to support (smell_type, action_kind) learning aggregation.

    When learning_stats is provided (e.g. from LearningStore.aggregate_by_smell_action),
    operations are sorted by past success rate (higher first) so that
    historically successful (smell_type, action_kind) pairs are applied first.

    When graph is provided (ROADMAP 2.1 — Граф как инструмент), diff hints
    are enriched with graph-derived suggestions (cycle break edge, facade
    candidates, split hints).
    """
    smells_by_node = index_smells_by_node(smells)
    operations = build_patch_operations(project_root=project_root, summary=summary, smells=smells, priorities=priorities, smells_by_node=smells_by_node, learning_stats=learning_stats, graph=graph, self_map=self_map)
    return PatchPlan(project_root=project_root, operations=operations)