"""Facade for action_plan — stable API boundary.

Callers (candidates to switch): architecture_planner.py, agent_core_arch_review_archreviewagentcore.py, cli/agent_handlers.py, eurika/reasoning/planner.py, tests/test_executor_sandbox.py."""

from action_plan import Action, ActionPlan

__all__ = ['Action', 'ActionPlan']
