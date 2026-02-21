"""Explicit facade for architecture planning and patch planning (ROADMAP 3.1-arch.6).

Planning layer only. Builds plans (PatchPlan, ActionPlan); does NOT execute.
Execution: use patch_engine (apply_patch, apply_and_verify, rollback, list_backups).
"""

from action_plan import Action, ActionPlan
from architecture_planner import build_action_plan, build_patch_plan, build_plan
from patch_plan import PatchOperation, PatchPlan

__all__ = [
    "Action",
    "ActionPlan",
    "PatchOperation",
    "PatchPlan",
    "build_plan",
    "build_action_plan",
    "build_patch_plan",
]

