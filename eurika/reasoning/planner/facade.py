"""
Planner public facade: build_plan, build_action_plan, build_patch_plan.

Consolidated from architecture_planner_build_plan (R2 reasoning engine).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from eurika.reasoning.action_plan import ActionPlan
from eurika.reasoning.planner.actions import actions_from_arch_plan
from eurika.reasoning.planner.analysis import build_steps_from_priorities, index_smells_by_node
from eurika.reasoning.planner.engine import run_patch_plan
from eurika.reasoning.planner.types import ArchitecturePlan
from eurika.smells.detector import ArchSmell
from patch_plan import PatchPlan


def build_plan(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
) -> ArchitecturePlan:
    """
    Build a minimal architecture plan from diagnostics.
    """
    generated_from = {
        "summary_risks": list(summary.get("risks", [])),
        "history_trends": dict(history_info.get("trends", {})),
        "history_regressions": list(history_info.get("regressions", [])),
        "priorities_count": len(priorities),
    }
    smells_by_node = index_smells_by_node(smells)
    steps = build_steps_from_priorities(priorities, smells_by_node)
    return ArchitecturePlan(
        project_root=project_root,
        generated_from=generated_from,
        steps=steps,
    )


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
    weights_snapshot: Optional[Dict[tuple[str, str], float]] = None,
) -> PatchPlan:
    """
    Build a PatchPlan from diagnostics.
    Delegates to run_patch_plan (collect_facts → generate → rank → output).
    RV8: weights_snapshot from ExecutionContext for deterministic ranking during cycle.
    """
    return run_patch_plan(
        project_root=project_root,
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        learning_stats=learning_stats,
        graph=graph,
        self_map=self_map,
        weights_snapshot=weights_snapshot,
    )
