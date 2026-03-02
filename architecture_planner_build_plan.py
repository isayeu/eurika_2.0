"""Extracted from parent module to reduce complexity."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from eurika.reasoning.planner.actions import actions_from_arch_plan
from eurika.reasoning.planner.analysis import build_steps_from_priorities, index_smells_by_node
from eurika.reasoning.planner.types import ArchitecturePlan
from eurika.reasoning.planner_patch_ops import build_patch_operations
from eurika.smells.detector import ArchSmell
from patch_plan import PatchPlan

from eurika.reasoning.action_plan import ActionPlan


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


def build_action_plan(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> ActionPlan:
    """
    Build an ActionPlan directly from diagnostics.

    If learning_stats is provided, actions whose type has good past success get a small
    expected_benefit bump.
    """
    arch_plan = build_plan(project_root, summary, smells, history_info, priorities)
    return actions_from_arch_plan(arch_plan, learning_stats=learning_stats)


def build_patch_plan(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    graph: Optional[Any] = None,
    self_map: Optional[Dict[str, Any]] = None,
) -> PatchPlan:
    """
    Build a first-approximation PatchPlan from diagnostics.

    v0.1: for each top-priority module, create a textual patch operation
    that describes the intended refactor. Uses smell types and step kinds
    to support (smell_type, action_kind) learning aggregation.

    When learning_stats is provided, operations are sorted by past success rate.
    When graph is provided, diff hints are enriched with graph-derived suggestions.
    ROADMAP 3.0.5.4: OSS pattern library enriches diff hints when .eurika/pattern_library.json exists.
    """
    smells_by_node = index_smells_by_node(smells)
    oss_patterns: Dict[str, Any] = {}
    try:
        lib_path = Path(project_root) / ".eurika" / "pattern_library.json"
        if lib_path.exists():
            from eurika.learning.pattern_library import load_pattern_library

            oss_patterns = load_pattern_library(lib_path)
    except Exception:
        pass
    operations = build_patch_operations(
        project_root=project_root,
        summary=summary,
        smells=smells,
        priorities=priorities,
        smells_by_node=smells_by_node,
        learning_stats=learning_stats,
        graph=graph,
        self_map=self_map,
        oss_patterns=oss_patterns,
    )
    return PatchPlan(project_root=project_root, operations=operations)