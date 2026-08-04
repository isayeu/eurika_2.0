"""
Decision Selector v0.1

Deterministic and explainable proposal selection.
No learning. No randomness.
"""

from typing import List
from agent_core import DecisionProposal


class SimpleSelector:
    """
    Selects the proposal with the highest confidence.
    Ties are resolved deterministically by order.
    """

    def select(self, proposals: List[DecisionProposal]) -> DecisionProposal:
        if not proposals:
            raise ValueError("No proposals to select from")

        # Deterministic max by confidence
        best = proposals[0]
        for proposal in proposals[1:]:
            if proposal.confidence > best.confidence:
                best = proposal

        return best


"""
End of selector.py v0.1
"""
