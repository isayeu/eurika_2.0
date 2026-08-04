"""Planner package (ROADMAP v3.0 Stage 1, §5.6). Consolidates planner_* modules."""

# Lazy facade for planner package. Direct imports: planner.types, planner.analysis, planner.actions, planner.llm_adapter.
__all__ = [
    "Action",
    "ActionPlan",
    "analyze",
    "ArchitectureModel",
    "ArchitectureSnapshot",
    "RefactorCandidate",
    "PatchOperation",
    "PatchPlan",
    "RefactorAction",
    "RiskProfile",
    "RiskReport",
    "SimulationResult",
    "SmellReport",
    "detect_smells",
    "propose_actions",
    "risk_report_from_plan",
    "build_plan",
    "build_action_plan",
    "build_patch_plan",
]


def __getattr__(name: str):
    if name in __all__:
        if name in ("Action", "ActionPlan"):
            from eurika.reasoning.action_plan import Action, ActionPlan  # noqa: F401
            return Action if name == "Action" else ActionPlan
        if name in ("PatchOperation", "PatchPlan"):
            from patch_plan import PatchOperation, PatchPlan  # noqa: F401
            return PatchOperation if name == "PatchOperation" else PatchPlan
        if name in ("analyze", "detect_smells", "propose_actions"):
            from eurika.reasoning.planner import core
            return {"analyze": core.analyze, "detect_smells": core.detect_smells, "propose_actions": core.propose_actions}[name]
        if name in (
            "ArchitectureModel",
            "ArchitectureSnapshot",
            "RefactorAction",
            "RefactorCandidate",
            "RiskProfile",
            "RiskReport",
            "SimulationResult",
            "SmellReport",
            "risk_report_from_plan",
        ):
            from eurika.reasoning.planner.models import (  # noqa: F401
                ArchitectureModel,
                ArchitectureSnapshot,
                RefactorAction,
                RefactorCandidate,
                RiskProfile,
                RiskReport,
                SimulationResult,
                SmellReport,
                risk_report_from_plan,
            )
            return {
                "ArchitectureModel": ArchitectureModel,
                "ArchitectureSnapshot": ArchitectureSnapshot,
                "RefactorAction": RefactorAction,
                "RefactorCandidate": RefactorCandidate,
                "RiskProfile": RiskProfile,
                "RiskReport": RiskReport,
                "SimulationResult": SimulationResult,
                "SmellReport": SmellReport,
                "risk_report_from_plan": risk_report_from_plan,
            }[name]
        from eurika.reasoning.planner.facade import build_action_plan, build_patch_plan, build_plan
        return {"build_plan": build_plan, "build_action_plan": build_action_plan, "build_patch_plan": build_patch_plan}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
