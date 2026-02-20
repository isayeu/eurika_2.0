"""Action-plan conversion helpers for architecture planner."""

from __future__ import annotations

from typing import Any, Dict, Optional

from action_plan import Action, ActionPlan
from eurika.reasoning.planner_rules import SMELL_ACTION_SEP
from eurika.reasoning.planner_types import ArchitecturePlan, PlanStep


def actions_from_arch_plan(
    plan: ArchitecturePlan,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> ActionPlan:
    """Convert an ArchitecturePlan into an ActionPlan."""
    actions: list[Action] = []
    total_risk = 0.0
    total_gain = 0.0
    for step in plan.steps:
        action = _step_to_action(step, learning_stats=learning_stats)
        actions.append(action)
        total_risk += action.risk
        total_gain += action.expected_benefit
    priority = list(range(len(actions)))
    return ActionPlan(
        actions=actions,
        priority=priority,
        total_risk=round(total_risk, 3),
        expected_gain=round(total_gain, 3),
    )


def _apply_learning_bump(stats: Dict[str, Any], expected_benefit: float) -> float:
    """Return bumped expected_benefit if stats show success rate >= 0.5."""
    total = stats.get("total", 0)
    success = stats.get("success", 0)
    if total >= 1:
        rate = success / total
        if rate >= 0.5:
            return min(1.0, round(expected_benefit + 0.05, 3))
    return expected_benefit


def _step_to_action(
    step: PlanStep,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Action:
    """
    Map a PlanStep to a single high-level Action.

    If learning_stats is provided and the action type has past success rate >= 0.5
    with at least one run, expected_benefit is increased slightly (learned signal).
    """
    type_mapping = {
        "split_module": "refactor_module",
        "introduce_facade": "introduce_facade",
        "split_responsibility": "refactor_module",
        "break_cycle": "refactor_dependencies",
        "refactor_module": "refactor_module",
    }
    action_type = type_mapping.get(step.kind, "refactor_module")
    description = f"{step.kind} on {step.target}: {step.rationale}"
    base_risk = 0.3
    if step.kind in {"split_module", "break_cycle"}:
        base_risk = 0.5
    if step.kind == "introduce_facade":
        base_risk = 0.4
    expected_benefit = max(0.3, 1.0 - 0.1 * (step.priority - 1))
    if learning_stats:
        smell_type = getattr(step, "smell_type", None) or "unknown"
        pair_key = f"{smell_type}{SMELL_ACTION_SEP}{action_type}"
        if pair_key in learning_stats:
            expected_benefit = _apply_learning_bump(learning_stats[pair_key], expected_benefit)
        elif action_type in learning_stats:
            expected_benefit = _apply_learning_bump(learning_stats[action_type], expected_benefit)
    return Action(
        type=action_type,
        target=step.target,
        description=description,
        risk=round(base_risk, 3),
        expected_benefit=round(expected_benefit, 3),
    )
