"""
Planner core facade (ROADMAP v3.0 §5.6).

Single entry point: analyze, detect_smells, propose_actions.
Delegates to planner submodules (graph_analysis, actions_proposal).
S4: core_extracted merged into graph_analysis.
"""
from __future__ import annotations

from eurika.reasoning.planner.actions_proposal import propose_actions
from eurika.reasoning.planner.graph_analysis import analyze, detect_smells

__all__ = ["analyze", "detect_smells", "propose_actions"]
