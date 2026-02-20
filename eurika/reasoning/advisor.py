"""Facade for high-level advisory logic.

Currently maps to AgentCore and related planning modules.
"""

from agent_core import (
    FORBIDDEN,
    AgentCore,
    Context,
    DecisionProposal,
    DecisionSelector,
    Executor,
    InputEvent,
    Memory,
    Reasoner,
    Result,
)

__all__ = [
    "ArchReviewAgentCore",
    "InputEvent",
    "Context",
    "DecisionProposal",
    "Result",
    "Memory",
    "Reasoner",
    "DecisionSelector",
    "Executor",
    "AgentCore",
    "FORBIDDEN",
]


def __getattr__(name: str):
    if name == "ArchReviewAgentCore":
        # Lazy import avoids cycle during package initialization:
        # eurika.reasoning -> advisor -> agent_core_arch_review -> architecture_planner
        from agent_core_arch_review import ArchReviewAgentCore

        return ArchReviewAgentCore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


