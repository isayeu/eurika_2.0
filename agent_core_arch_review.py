"""
Experimental thin AgentCore for architecture review (v0.2 draft).

Re-exports ArchReviewAgentCore from the extracted implementation module.
"""
from __future__ import annotations

from agent_core_arch_review_archreviewagentcore import ArchReviewAgentCore

__all__ = ["ArchReviewAgentCore"]

# TODO: Refactor agent_core_arch_review.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: agent_core_arch_review_archreviewagentcore.py.
# - Consider grouping callers: tests/test_agent_core_arch_review.py, cli/agent_handlers.py, cli/agent_handlers_handle_agent_patch_apply.py.
# - Introduce facade for callers: cli/agent_handlers.py, cli/agent_handlers_handle_agent_patch_apply.py, cli/orchestration/prepare.py....
# - Extract orchestration logic into `module_orchestration`
# - Group CLI handlers related to agent patching into `module_agent_patch_cli`
# - Separate advisor and reasoning modules for better clarity
