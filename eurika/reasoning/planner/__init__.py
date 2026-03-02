"""Planner package (ROADMAP v3.0 Stage 1, §5.6). Consolidates planner_* modules."""

# Lazy facade to avoid circular import: planner_types -> planner.types -> planner (this)
# -> architecture_planner -> planner_types
__all__ = [
    "Action",
    "ActionPlan",
    "PatchOperation",
    "PatchPlan",
    "build_plan",
    "build_action_plan",
    "build_patch_plan",
]


def __getattr__(name: str):
    if name in __all__:
        if name in ("Action", "ActionPlan"):
            from action_plan import Action, ActionPlan  # noqa: F401
            return Action if name == "Action" else ActionPlan
        if name in ("PatchOperation", "PatchPlan"):
            from patch_plan import PatchOperation, PatchPlan  # noqa: F401
            return PatchOperation if name == "PatchOperation" else PatchPlan
        from architecture_planner import build_action_plan, build_patch_plan, build_plan
        return {"build_plan": build_plan, "build_action_plan": build_action_plan, "build_patch_plan": build_patch_plan}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
