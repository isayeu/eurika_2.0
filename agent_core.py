"""
Eurika Agent Core v0.1

This file implements the minimal deterministic agent loop.
NO intelligence, NO goals, NO self-modification.
Only orchestration and contracts.
"""

from dataclasses import dataclass, field
from typing import Any, List, Protocol
import time


# =====================
# Data contracts
# =====================

@dataclass
class InputEvent:
    type: str
    payload: dict
    source: str = "external"
    timestamp: float = field(default_factory=time.time)


@dataclass
class Context:
    event: InputEvent
    memory_snapshot: List[Any]
    system_state: dict


@dataclass
class DecisionProposal:
    action: str
    arguments: dict
    confidence: float
    rationale: str


@dataclass
class Result:
    success: bool
    output: dict
    side_effects: List[str]


# =====================
# Module protocols
# =====================

class Memory(Protocol):
    def snapshot(self) -> List[Any]: ...
    def record(self, event: InputEvent, decision: DecisionProposal, result: Result): ...


class Reasoner(Protocol):
    def propose(self, context: Context) -> List[DecisionProposal]: ...


class DecisionSelector(Protocol):
    def select(self, proposals: List[DecisionProposal]) -> DecisionProposal: ...


class Executor(Protocol):
    def execute(self, decision: DecisionProposal) -> Result: ...


# =====================
# Agent Core
# =====================

class AgentCore:
    """
    The core orchestrator.
    It knows nothing about domains, goals, tools or intelligence.
    """

    def __init__(
        self,
        memory: Memory,
        reasoner: Reasoner,
        selector: DecisionSelector,
        executor: Executor,
    ):
        self.memory = memory
        self.reasoner = reasoner
        self.selector = selector
        self.executor = executor

    def step(self, event: InputEvent) -> Result:
        """
        One atomic agent step.
        """
        # 1. Build context
        context = Context(
            event=event,
            memory_snapshot=self.memory.snapshot(),
            system_state={},
        )

        # 2. Propose decisions
        proposals = self.reasoner.propose(context)
        if not proposals:
            result = Result(
                success=False,
                output={"error": "no proposals"},
                side_effects=[],
            )
            self.memory.record(event, None, result)  # type: ignore
            return result

        # 3. Select decision
        decision = self.selector.select(proposals)

        # 4. Execute decision
        result = self.executor.execute(decision)

        # 5. Record outcome
        self.memory.record(event, decision, result)

        return result


# =====================
# Guardrails
# =====================

FORBIDDEN = [
    "self-modifying code",
    "direct file access",
    "network access",
    "autonomous loops",
]

"""
End of agent_core.py v0.1
"""

# TODO: Refactor agent_core.py (bottleneck -> introduce_facade)
# Suggested steps:
# - Introduce a facade or boundary to reduce direct fan-in.
# - Create a stable public API for this module; let internal structure evolve independently.
# - Limit the number of modules that import this file directly.

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: eurika/reasoning/advisor.py, cli/agent_handlers.py, agent_core_arch_review.py.
# - Introduce facade for callers: agent_core_arch_review.py, memory.py, cli/agent_handlers.py....

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: tests/test_agent_core_arch_review.py, agent_core_arch_review.py, cli/agent_handlers.py.
# - Introduce facade for callers: agent_core_arch_review.py, memory.py, cli/agent_handlers.py....

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: memory.py, eurika/reasoning/advisor.py, cli/agent_handlers.py.
# - Introduce facade for callers: agent_core_arch_review.py, memory.py, cli/agent_handlers.py....

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: agent_core_arch_review.py, memory.py, eurika/reasoning/advisor.py.
# - Introduce facade for callers: agent_core_arch_review.py, memory.py, cli/agent_handlers.py....

# TODO: Refactor agent_core.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: memory.py, eurika/reasoning/advisor.py, agent_core_arch_review.py.
# - Introduce facade for callers: agent_core_arch_review.py, memory.py, cli/agent_handlers.py....
