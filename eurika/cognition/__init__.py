"""
Cognition — meta-level strategy control (ROADMAP v4.0).

meta_controller: переключение стратегий при деградации.
"""

from .meta_controller import PolicyDecision, evaluate_policy

__all__ = ["PolicyDecision", "evaluate_policy"]
