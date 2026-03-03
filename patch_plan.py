"""
Patch Plan v0.1 (draft)

Describes concrete, but still human-reviewable patch plans derived from
higher-level architecture actions. This module does NOT apply patches by
itself; it only formalizes what should be changed.
"""
from __future__ import annotations

from patch_plan_extracted import PatchOperation, PatchPlan

__all__ = ["PatchOperation", "PatchPlan"]
