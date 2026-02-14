"""
Dummy Reasoner v0.1

Produces deterministic, explainable decision proposals.
No AI. No learning. No heuristics.
Uses memory_snapshot to avoid repeating same input (anti-loop).
Handles "analyze"/"scan" for Code Awareness (refactor proposals).
"""

from typing import List
from agent_core import Context, DecisionProposal


REPEAT_WINDOW = 3  # If same payload in last N records -> noop
ANALYZE_TRIGGERS = ("analyze", "scan")


class DummyReasoner:
    """
    A placeholder reasoner used to validate the agent loop.
    Returns noop if the same payload was seen recently (loop avoidance).
    Produces suggest_refactor when user types analyze/scan.
    """

    def propose(self, context: Context) -> List[DecisionProposal]:
        event = context.event

        if event.type == "noop":
            return []

        text = event.payload if isinstance(event.payload, str) else str(event.payload)
        text_lower = text.strip().lower()

        # Code Awareness: analyze project, propose refactoring
        if text_lower in ANALYZE_TRIGGERS:
            from code_awareness import CodeAwareness

            analyzer = CodeAwareness()
            analysis = analyzer.analyze_project()
            return [
                DecisionProposal(
                    action="suggest_refactor",
                    arguments={"analysis": analysis},
                    confidence=0.9,
                    rationale="Read-only code analysis completed. Proposing findings.",
                )
            ]

        # Use memory to avoid repeating same input
        recent = context.memory_snapshot[-REPEAT_WINDOW:]
        payload_key = str(event.payload)
        for rec in recent:
            if str(rec.event_payload) == payload_key:
                return []  # Seen recently -> noop, no echo

        proposal = DecisionProposal(
            action="echo",
            arguments={"payload": event.payload},
            confidence=0.5,
            rationale=f"Echo input event of type '{event.type}'",
        )
        return [proposal]


"""
End of reasoner_dummy.py v0.1
"""
