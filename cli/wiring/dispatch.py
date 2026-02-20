"""CLI command dispatch wiring extracted from eurika_cli."""

from __future__ import annotations

import argparse
from typing import Any, Callable

from cli import handlers


def dispatch_command(parser: argparse.ArgumentParser, args: Any) -> int:
    """Dispatch parsed CLI args to the matching command handler."""
    if args.command is None:
        return handlers.handle_help(parser)

    dispatch: dict[str, Callable[[], int]] = {
        "help": lambda: handlers.handle_help(parser),
        "scan": lambda: handlers.handle_scan(args),
        "arch-summary": lambda: handlers.handle_arch_summary(args),
        "arch-history": lambda: handlers.handle_arch_history(args),
        "history": lambda: handlers.handle_arch_history(args),
        "report": lambda: handlers.handle_report(args),
        "report-snapshot": lambda: handlers.handle_report_snapshot(args),
        "explain": lambda: handlers.handle_explain(args),
        "arch-diff": lambda: handlers.handle_arch_diff(args),
        "self-check": lambda: handlers.handle_self_check(args),
        "doctor": lambda: handlers.handle_doctor(args),
        "fix": lambda: handlers.handle_fix(args),
        "cycle": lambda: handlers.handle_cycle(args),
        "architect": lambda: handlers.handle_architect(args),
        "suggest-plan": lambda: handlers.handle_suggest_plan(args),
        "clean-imports": lambda: handlers.handle_clean_imports(args),
        "watch": lambda: handlers.handle_watch(args),
        "serve": lambda: handlers.handle_serve(args),
    }
    if args.command == "help":
        return dispatch["help"]()
    if args.command in dispatch:
        return dispatch[args.command]()

    if args.command == "agent":
        agent_dispatch: dict[str, Callable[[Any], int]] = {
            "arch-review": handlers.handle_agent_arch_review,
            "arch-evolution": handlers.handle_agent_arch_evolution,
            "prioritize-modules": handlers.handle_agent_prioritize_modules,
            "feedback-summary": handlers.handle_agent_feedback_summary,
            "action-dry-run": handlers.handle_agent_action_dry_run,
            "action-simulate": handlers.handle_agent_action_simulate,
            "action-apply": handlers.handle_agent_action_apply,
            "patch-plan": handlers.handle_agent_patch_plan,
            "patch-apply": handlers.handle_agent_patch_apply,
            "patch-rollback": handlers.handle_agent_patch_rollback,
            "cycle": handlers.handle_agent_cycle,
            "learning-summary": handlers.handle_agent_learning_summary,
        }
        handler = agent_dispatch.get(args.agent_command)
        if handler:
            return handler(args)

    return 0
