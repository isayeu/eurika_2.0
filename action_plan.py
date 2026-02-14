"""
Action Plan v0.4 (draft)

Formalizes planned architecture actions produced from higher-level plans.

This is a pure data layer:
- no direct code modifications,
- intended to be consumed by an executor sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class Action:
    """
    Single planned action over the codebase.

    The semantics are intentionally generic and high-level. Concrete
    executors may choose how to interpret them (e.g. generate patches,
    run tools, etc.) but this module itself stays execution-agnostic.
    """

    type: str
    target: str
    description: str
    risk: float
    expected_benefit: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Action":
        return Action(
            type=str(d.get("type", "")),
            target=str(d.get("target", "")),
            description=str(d.get("description", "")),
            risk=float(d.get("risk", 0)),
            expected_benefit=float(d.get("expected_benefit", 0)),
        )


@dataclass
class ActionPlan:
    """
    Container for a set of planned actions.

    - actions: list of individual actions
    - priority: optional explicit ordering (indices into actions)
    - total_risk / expected_gain: coarse aggregates for quick inspection
    """

    actions: List[Action]
    priority: List[int]
    total_risk: float
    expected_gain: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actions": [a.to_dict() for a in self.actions],
            "priority": list(self.priority),
            "total_risk": self.total_risk,
            "expected_gain": self.expected_gain,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActionPlan":
        actions = [Action.from_dict(a) for a in d.get("actions", [])]
        return ActionPlan(
            actions=actions,
            priority=list(d.get("priority", [])),
            total_risk=float(d.get("total_risk", 0)),
            expected_gain=float(d.get("expected_gain", 0)),
        )


# TODO: Refactor action_plan.py (bottleneck -> introduce_facade)
# Suggested steps:
# - Introduce a facade or boundary to reduce direct fan-in.
# - Create a stable public API for this module; let internal structure evolve independently.
# - Limit the number of modules that import this file directly.

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: cli/agent_handlers.py, architecture_planner.py, agent_core_arch_review.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: eurika/reasoning/planner.py, cli/agent_handlers.py, agent_core_arch_review.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: tests/test_executor_sandbox.py, eurika/reasoning/planner.py, agent_core_arch_review.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: architecture_planner.py, eurika/reasoning/planner.py, tests/test_executor_sandbox.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: agent_core_arch_review.py, tests/test_executor_sandbox.py, cli/agent_handlers.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....

# TODO: Refactor action_plan.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: eurika/reasoning/planner.py, tests/test_executor_sandbox.py, architecture_planner.py.
# - Introduce facade for callers: agent_core_arch_review.py, architecture_planner.py, cli/agent_handlers.py....
