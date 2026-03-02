"""
Architecture Planner v0.3 (draft)

Turns architecture diagnostics (summary + smells + history + priorities)
into a structured, explainable engineering plan.

This is a pure planning layer — no execution, no code changes.

v0.4: graph optional — when ProjectGraph is provided, uses graph_ops
for concrete hints (cycle break edge, facade candidates, split hints).
"""
from __future__ import annotations

__all__ = ["build_plan", "build_action_plan", "build_patch_plan", "ArchitecturePlan"]

from architecture_planner_build_plan import build_action_plan, build_patch_plan, build_plan
from eurika.reasoning.planner.types import ArchitecturePlan
# TODO: Further consolidation — architecture_planner_build_plan could move to eurika.reasoning.planner
