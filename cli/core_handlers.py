"""Core CLI command handlers (scan/summary/history/diff/self-check/report/explain).

P0.4: Split from 907 LOC into submodules, each <400 LOC.
Public surface re-exported here for backward compatibility (cli.handlers, tests).
"""
from __future__ import annotations

from typing import Any

from .core_handlers_ml_market import handle_ml_market
from .core_handlers_arch import handle_arch_diff, handle_arch_history, handle_arch_summary
from .core_handlers_clean import handle_clean_imports
from .core_handlers_doctor import handle_doctor
from .core_handlers_explain import handle_architect, handle_explain, handle_suggest_plan
from .core_handlers_fix_cycle import handle_cycle, handle_fix
from .core_handlers_learn import handle_learn_github
from .core_handlers_bug_hunt import handle_bug_hunt
from .core_handlers_prove_cycle import handle_prove_cycle
from .core_handlers_idle_self_dev import handle_idle_self_dev
from .core_handlers_report import handle_learning_kpi, handle_report, handle_report_snapshot
from .core_handlers_scan import handle_scan, handle_self_check
from .core_handlers_serve import handle_serve
from .core_handlers_telegram import handle_telegram_bot
from .core_handlers_whitelist import handle_campaign_undo, handle_whitelist_draft
from .core_handlers_watch import handle_watch

__all__ = [
    "handle_arch_diff",
    "handle_arch_history",
    "handle_arch_summary",
    "handle_architect",
    "handle_bug_hunt",
    "handle_campaign_undo",
    "handle_clean_imports",
    "handle_cycle",
    "handle_doctor",
    "handle_explain",
    "handle_fix",
    "handle_help",
    "handle_idle_self_dev",
    "handle_learn_github",
    "handle_learning_kpi",
    "handle_ml_market",
    "handle_prove_cycle",
    "handle_report",
    "handle_report_snapshot",
    "handle_scan",
    "handle_self_check",
    "handle_serve",
    "handle_suggest_plan",
    "handle_telegram_bot",
    "handle_watch",
    "handle_whitelist_draft",
]

# Backward compat: tests import knowledge_topics_from_env_or_summary from core_handlers
from eurika.orchestration.doctor import knowledge_topics_from_env_or_summary  # noqa: F401


def handle_help(parser: Any) -> int:
    """Print high-level command overview and detailed argparse help."""
    print("Eurika — architecture analysis and refactoring assistant (v3.0.19)")
    print()
    print("Product (4 modes):")
    print("  scan [path]              full scan, update artifacts, report")
    print("  doctor [path]           diagnostics: report + architect (no patches)")
    print("  fix [path]              full cycle: scan → plan → patch → verify")
    print("  explain <module> [path] role and risks of a module")
    print()
    print("Other: report, report-snapshot, learning-kpi, prove-cycle, bug-hunt, idle-self-dev, telegram-bot, campaign-undo, architect, suggest-plan, arch-summary, arch-history, history, arch-diff, self-check, clean-imports, serve, ml-market")
    print("Advanced: eurika agent <cmd>  (patch-plan, patch-apply, patch-rollback, cycle, ...)")
    print("ML market (paper only): eurika ml-market sync|paper|train|status")
    print()
    print("  --help after any command for details.")
    print()
    parser.print_help()
    return 0
