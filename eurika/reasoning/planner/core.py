"""
Planner core facade (ROADMAP v3.0 §5.6).

Single entry point: analyze, detect_smells, propose_actions.
Delegates to planner submodules (analysis, actions_proposal, core_extracted)
and architecture_planner.
"""
from __future__ import annotations

from eurika.reasoning.planner.actions_proposal import propose_actions
from eurika.reasoning.planner.core_extracted import detect_smells
from eurika.reasoning.planner.graph_analysis import analyze

__all__ = ["analyze", "detect_smells", "propose_actions"]
