"""LLM-driven portfolio cycles (holistic monitor + earn + trade).

Delegates to ``portfolio_agent``; kept for import compatibility.
"""

from __future__ import annotations

from eurika.ml.portfolio_agent import (
    PORTFOLIO_AGENT_RULES as ASSISTANT_AGENT_RULES,
    build_portfolio_prompt as build_agent_prompt,
    parse_portfolio_actions as parse_assistant_actions,
    portfolio_journal_body as agent_journal_body,
    run_portfolio_cycle as run_agent_cycle,
)

__all__ = [
    "ASSISTANT_AGENT_RULES",
    "agent_journal_body",
    "build_agent_prompt",
    "parse_assistant_actions",
    "run_agent_cycle",
]
