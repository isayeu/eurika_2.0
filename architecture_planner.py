"""
Architecture Planner — backward-compatible re-export (R2 consolidation).

Implementation: eurika.reasoning.planner.facade.
"""
from __future__ import annotations

__all__ = ["build_plan", "build_action_plan", "build_patch_plan", "ArchitecturePlan"]

from eurika.reasoning.planner.facade import build_action_plan, build_patch_plan, build_plan
from eurika.reasoning.planner.types import ArchitecturePlan
