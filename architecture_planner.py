"""
Architecture Planner v0.3 (draft)

Turns architecture diagnostics (summary + smells + history + priorities)
into a structured, explainable engineering plan.

This is a pure planning layer — no execution, no code changes.

v0.4: graph optional — when ProjectGraph is provided, uses graph_ops
for concrete hints (cycle break edge, facade candidates, split hints).
"""
from __future__ import annotations
__all__ = ['build_plan', 'build_action_plan', 'build_patch_plan', 'ArchitecturePlan']
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_actions import actions_from_arch_plan
from eurika.reasoning.planner_analysis import build_steps_from_priorities, index_smells_by_node
from eurika.reasoning.planner_types import ArchitecturePlan
from architecture_planner_build_plan import build_plan
from action_plan import ActionPlan
if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph
from architecture_planner_build_patch_plan import build_patch_plan

def build_action_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> ActionPlan:
    """
    Build an ActionPlan directly from diagnostics.

    If learning_stats is provided (e.g. from LearningStore.aggregate_by_action_kind
    with success_rate added), actions whose type has good past success get a small
    expected_benefit bump.
    """
    arch_plan = build_plan(project_root, summary, smells, history_info, priorities)
    return actions_from_arch_plan(arch_plan, learning_stats=learning_stats)
