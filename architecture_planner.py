"""
Architecture Planner v0.3 (draft)

Turns architecture diagnostics (summary + smells + history + priorities)
into a structured, explainable engineering plan.

This is a pure planning layer — no execution, no code changes.

v0.4: graph optional — when ProjectGraph is provided, uses graph_ops
for concrete hints (cycle break edge, facade candidates, split hints).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_actions import actions_from_arch_plan
from eurika.reasoning.planner_analysis import (
    build_steps_from_priorities,
    index_smells_by_node,
)
from eurika.reasoning.planner_patch_ops import build_patch_operations
from eurika.reasoning.planner_types import ArchitecturePlan
from action_plan import ActionPlan
from patch_plan import PatchPlan
if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph

def build_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]]) -> ArchitecturePlan:
    """
    Build a minimal architecture plan from diagnostics.

    v0.3 draft:
    - builds a minimal, explainable plan:
      one high-level PlanStep per prioritized module (top-N).
    """
    generated_from = {'summary_risks': list(summary.get('risks', [])), 'history_trends': dict(history_info.get('trends', {})), 'history_regressions': list(history_info.get('regressions', [])), 'priorities_count': len(priorities)}
    smells_by_node = index_smells_by_node(smells)
    steps = build_steps_from_priorities(priorities, smells_by_node)
    return ArchitecturePlan(project_root=project_root, generated_from=generated_from, steps=steps)

def build_action_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> ActionPlan:
    """
    Build an ActionPlan directly from diagnostics.

    If learning_stats is provided (e.g. from LearningStore.aggregate_by_action_kind
    with success_rate added), actions whose type has good past success get a small
    expected_benefit bump.
    """
    arch_plan = build_plan(project_root, summary, smells, history_info, priorities)
    return actions_from_arch_plan(arch_plan, learning_stats=learning_stats)


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
    operations = build_patch_operations(
        project_root=project_root,
        summary=summary,
        smells=smells,
        priorities=priorities,
        smells_by_node=smells_by_node,
        learning_stats=learning_stats,
        graph=graph,
        self_map=self_map,
    )
    return PatchPlan(project_root=project_root, operations=operations)
