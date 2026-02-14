"""
Patch Plan v0.1 (draft)

Describes concrete, but still human-reviewable patch plans derived from
higher-level architecture actions. This module does NOT apply patches by
itself; it only formalizes what should be changed.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PatchOperation:
    """
    Single patch operation over a file.

    The `diff` field intentionally stays textual (unified diff or
    high-level description) to keep this layer tool-agnostic.

    smell_type: dominant architecture smell for this module (e.g. god_module,
    bottleneck), used for learning aggregation by (smell_type, action_kind).

    params: optional dict for AST-based operations, e.g. remove_cyclic_import:
        {"target_module": str} — module name to remove from imports.
    """

    target_file: str
    kind: str  # e.g. "refactor_module", "introduce_facade", "remove_cyclic_import"
    description: str
    diff: str
    smell_type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchPlan:
    """
    Collection of patch operations for a project.

    This is a "patch-plan", not an auto-applied patch: executors are
    expected to either:
    - present it to a human, or
    - turn it into concrete edits in a controlled sandbox.
    """

    project_root: str
    operations: List[PatchOperation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": self.project_root,
            "operations": [op.to_dict() for op in self.operations],
        }

