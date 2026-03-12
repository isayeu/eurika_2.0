"""RV3: Reasoning generator — candidate generation, patch operations (TARGET_V3_STRUCTURE)."""

from __future__ import annotations

from eurika.reasoning.planner.engine import generate_candidates
from eurika.reasoning.planner.patch_ops import build_patch_operations

__all__ = [
    "generate_candidates",
    "build_patch_operations",
]
