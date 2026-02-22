"""CLI handlers facade.

v0.9: thin wrapper that re-exports concrete handler implementations from:
- cli.core_handlers    — core commands (scan/summary/history/diff/self-check/report/explain)
- cli.agent_handlers   — AgentCore-related commands

This keeps the public `cli.handlers.handle_*` API stable while reducing
this module's fan-in/fan-out and aligning with the target Architecture.md
layout (separate cli/core vs agent responsibilities).
"""
from __future__ import annotations
from .core_handlers import handle_arch_history, handle_arch_summary, handle_arch_diff, handle_architect, handle_campaign_undo, handle_clean_imports, handle_cycle, handle_doctor, handle_explain, handle_fix, handle_help, handle_learn_github, handle_report, handle_report_snapshot, handle_scan, handle_self_check, handle_serve, handle_suggest_plan, handle_watch
from .agent_handlers import handle_agent_action_apply, handle_agent_action_dry_run, handle_agent_action_simulate, handle_agent_arch_evolution, handle_agent_arch_review, handle_agent_cycle, handle_agent_feedback_summary, handle_agent_learning_summary, handle_agent_patch_apply, handle_agent_patch_rollback, handle_agent_patch_plan, handle_agent_prioritize_modules
__all__ = ['handle_help', 'handle_scan', 'handle_self_check', 'handle_arch_summary', 'handle_arch_history', 'handle_report', 'handle_report_snapshot', 'handle_campaign_undo', 'handle_explain', 'handle_arch_diff', 'handle_architect', 'handle_doctor', 'handle_fix', 'handle_cycle', 'handle_watch', 'handle_suggest_plan', 'handle_clean_imports', 'handle_learn_github', 'handle_serve', 'handle_agent_arch_review', 'handle_agent_arch_evolution', 'handle_agent_prioritize_modules', 'handle_agent_feedback_summary', 'handle_agent_action_dry_run', 'handle_agent_action_simulate', 'handle_agent_action_apply', 'handle_agent_patch_plan', 'handle_agent_patch_apply', 'handle_agent_patch_rollback', 'handle_agent_cycle', 'handle_agent_learning_summary']