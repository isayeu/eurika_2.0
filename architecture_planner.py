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
from typing import TYPE_CHECKING
from eurika.reasoning.planner_types import ArchitecturePlan
from architecture_planner_build_plan import build_plan
from architecture_planner_build_action_plan import build_action_plan
if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph
from architecture_planner_build_patch_plan import build_patch_plan

# TODO: Refactor architecture_planner.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: architecture_planner_build_plan.py, architecture_planner_build_action_plan.py, action_plan.py.
# - Consider grouping callers: eurika/api/__init__.py, agent_core_arch_review_archreviewagentcore.py, tests/test_graph_ops.py.
