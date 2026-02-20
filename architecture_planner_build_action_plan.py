"""Extracted from parent module to reduce complexity."""
from typing import Any, Dict, List, Optional
from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_actions import actions_from_arch_plan
from architecture_planner_build_plan import build_plan
from action_plan import ActionPlan

def build_action_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> ActionPlan:
    """
    Build an ActionPlan directly from diagnostics.

    If learning_stats is provided (e.g. from LearningStore.aggregate_by_action_kind
    with success_rate added), actions whose type has good past success get a small
    expected_benefit bump.
    """
    arch_plan = build_plan(project_root, summary, smells, history_info, priorities)
    return actions_from_arch_plan(arch_plan, learning_stats=learning_stats)