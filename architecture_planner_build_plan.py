"""Extracted from parent module to reduce complexity."""
from typing import Any, Dict, List
from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_analysis import build_steps_from_priorities, index_smells_by_node
from eurika.reasoning.planner_types import ArchitecturePlan

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