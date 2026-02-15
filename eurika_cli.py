"""
Eurika CLI v0.5

Entry point: argument parsing and dispatch only.
All command logic lives in cli.handlers.
"""

import argparse
import sys
from pathlib import Path

# Load .env if present (optional: pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cli import handlers


def _build_parser() -> argparse.ArgumentParser:
    """Configure top-level CLI parser and subcommands."""
    parser = argparse.ArgumentParser(
        prog="eurika",
        description="Eurika — architecture analysis and refactoring assistant",
        epilog="Product (5 modes): scan | doctor | fix | cycle | explain. Use eurika help for full list.",
    )
    parser.add_argument("--version", "-V", action="version", version="%(prog)s 2.6.2")
    subparsers = parser.add_subparsers(dest="command")

    _add_product_commands(subparsers)   # scan, doctor, fix, explain — ROADMAP этап 5
    _add_other_commands(subparsers)
    _add_agent_commands(subparsers)

    subparsers.add_parser("help", help="Show Eurika command overview")

    return parser


def _add_product_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the 4 product commands first (ROADMAP этап 5: scan, doctor, fix, explain)."""
    scan_parser = subparsers.add_parser("scan", help="Scan project, update artifacts, report")
    scan_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    scan_parser.add_argument(
        "--format", "-f",
        choices=["text", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    scan_parser.add_argument(
        "--color",
        action="store_true",
        default=None,
        dest="color",
        help="Force color output (default: auto from TTY)",
    )
    scan_parser.add_argument(
        "--no-color",
        action="store_false",
        dest="color",
        help="Disable color output",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnostics only: report + architect (no patches)",
    )
    doctor_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    doctor_parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    doctor_parser.add_argument("--no-llm", action="store_true", help="Architect: use template only")

    fix_parser = subparsers.add_parser(
        "fix",
        help="Full cycle: scan → plan → patch → verify",
    )
    fix_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    fix_parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    fix_parser.add_argument("--dry-run", action="store_true", help="Only build patch plan, do not apply")
    fix_parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output; final JSON only")
    fix_parser.add_argument("--no-clean-imports", action="store_true", help="Skip remove-unused-imports step (default: included)")
    fix_parser.add_argument("--interval", type=int, default=0, metavar="SEC", help="Auto-run: repeat every SEC seconds (0=once, Ctrl+C to stop)")

    cycle_parser = subparsers.add_parser(
        "cycle",
        help="Full ritual: scan → doctor (report + architect) → fix. Single command.",
    )
    cycle_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    cycle_parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    cycle_parser.add_argument("--dry-run", action="store_true", help="Doctor + plan only; do not apply patches")
    cycle_parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output; final JSON only")
    cycle_parser.add_argument("--no-llm", action="store_true", help="Architect: use template only (no API key)")
    cycle_parser.add_argument("--no-clean-imports", action="store_true", help="Skip remove-unused-imports in fix (default: included)")
    cycle_parser.add_argument("--interval", type=int, default=0, metavar="SEC", help="Auto-run: repeat every SEC seconds (0=once, Ctrl+C to stop)")

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain role and risks of a module",
    )
    explain_parser.add_argument(
        "module",
        type=str,
        help="Module path or name (e.g. architecture_diff.py or cli/handlers.py)",
    )
    explain_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    explain_parser.add_argument("--window", type=int, default=5, help="History window for patch-plan (default: 5)")

    watch_parser = subparsers.add_parser(
        "watch",
        help="Watch for .py changes and run fix (ROADMAP 2.6.2)",
    )
    watch_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    watch_parser.add_argument("--poll", type=int, default=5, metavar="SEC", help="Poll interval (default: 5)")
    watch_parser.add_argument("--window", type=int, default=5, help="History window for patch-plan (default: 5)")
    watch_parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    watch_parser.add_argument("--no-clean-imports", action="store_true", help="Skip remove-unused-imports")


def _add_other_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register other (non-agent) commands: report, arch-*, self-check, serve, etc."""
    summary_parser = subparsers.add_parser(
        "arch-summary",
        help="Print architecture summary for project",
    )
    summary_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    summary_parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON (machine-readable)",
    )

    history_parser = subparsers.add_parser(
        "arch-history",
        help="Print architecture evolution report",
    )
    history_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    history_parser.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    history_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    # Alias: eurika history → eurika arch-history
    history_alias = subparsers.add_parser(
        "history",
        help="Alias for arch-history (architecture evolution report)",
    )
    history_alias.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    history_alias.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    history_alias.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    diff_parser = subparsers.add_parser(
        "arch-diff",
        help="Diff two architecture snapshots (self_map JSON files)",
    )
    diff_parser.add_argument("old", type=Path, help="Old self_map.json")
    diff_parser.add_argument("new", type=Path, help="New self_map.json")
    diff_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    self_check_parser = subparsers.add_parser(
        "self-check",
        help="Run full scan on Eurika itself (self-analysis ritual)",
    )
    self_check_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root to analyze (default: .)",
    )
    self_check_parser.add_argument(
        "--format", "-f",
        choices=["text", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    self_check_parser.add_argument(
        "--color",
        action="store_true",
        default=None,
        dest="color",
        help="Force color output (default: auto from TTY)",
    )
    self_check_parser.add_argument(
        "--no-color",
        action="store_false",
        dest="color",
        help="Disable color output",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Print architecture summary + evolution report (no rescan)",
    )
    report_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    report_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")
    report_parser.add_argument("--window", type=int, default=5, help="History window for evolution (default: 5)")

    architect_parser = subparsers.add_parser(
        "architect",
        help="Print architect's interpretation; LLM if OPENAI_API_KEY set (optional OPENAI_BASE_URL, OPENAI_MODEL for OpenRouter)",
    )
    architect_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    architect_parser.add_argument(
        "--window",
        type=int,
        default=5,
        help="History window (default: 5)",
    )
    architect_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use template only (no LLM call)",
    )

    suggest_plan_parser = subparsers.add_parser(
        "suggest-plan",
        help="Print heuristic refactoring plan from summary and risks (ROADMAP §7)",
    )
    suggest_plan_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    suggest_plan_parser.add_argument(
        "--window",
        type=int,
        default=5,
        help="History window for context (default: 5)",
    )

    clean_imports_parser = subparsers.add_parser(
        "clean-imports",
        help="Remove unused imports from Python files (Killer-feature: dead code)",
    )
    clean_imports_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    clean_imports_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to files (default: dry-run)",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run JSON API server for future UI (GET /api/summary, /api/history, /api/diff)",
    )
    serve_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Project root (default: .)",
    )
    serve_parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")


def _add_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register experimental AgentCore-related commands."""
    agent_parser = subparsers.add_parser(
        "agent",
        help="Experimental AgentCore helpers (v0.2 draft, read-only)",
    )
    agent_subparsers = agent_parser.add_subparsers(
        dest="agent_command",
        required=True,
    )

    _add_agent_arch_review_command(agent_subparsers)
    _add_agent_arch_evolution_command(agent_subparsers)
    _add_agent_prioritize_modules_command(agent_subparsers)
    _add_agent_feedback_summary_command(agent_subparsers)
    _add_agent_action_dry_run_command(agent_subparsers)
    _add_agent_action_simulate_command(agent_subparsers)
    _add_agent_action_apply_command(agent_subparsers)
    _add_agent_patch_plan_command(agent_subparsers)
    _add_agent_patch_apply_command(agent_subparsers)
    _add_agent_patch_rollback_command(agent_subparsers)
    _add_agent_cycle_command(agent_subparsers)
    _add_agent_learning_summary_command(agent_subparsers)


def _add_agent_arch_review_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser(
        "arch-review",
        help="Run experimental AgentCore arch_review over existing artifacts",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_arch_evolution_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser(
        "arch-evolution",
        help="Run experimental AgentCore arch_evolution_query over history only",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_prioritize_modules_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser(
        "prioritize-modules",
        help="Run AgentCore arch_review and print only module priorities",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_feedback_summary_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "feedback-summary",
        help="Summarize manual feedback on AgentCore proposals",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")


def _add_agent_action_dry_run_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "action-dry-run",
        help="Build ActionPlan from diagnostics and print it (no execution)",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_action_simulate_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "action-simulate",
        help="Build ActionPlan and run ExecutorSandbox dry-run (no code changes)",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_action_apply_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "action-apply",
        help="Build ActionPlan and execute; backups in .eurika_backups unless --no-backup",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    p.add_argument("--no-backup", action="store_true", help="Do not create backups")


def _add_agent_patch_plan_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "patch-plan",
        help="Build patch plan from diagnostics and print or write to file",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    p.add_argument("--output", "-o", type=Path, default=None, metavar="FILE", help="Write patch plan JSON to FILE")


def _add_agent_patch_apply_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "patch-apply",
        help="Apply patch plan (append TODO comments); default is dry-run",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window for building plan (default: 5)")
    p.add_argument("--apply", action="store_true", help="Actually write to files (default: dry-run only)")
    p.add_argument("--no-backup", action="store_true", help="Do not create backups in .eurika_backups/")
    p.add_argument("--verify", action="store_true", help="After --apply, run pytest and report success/failure")


def _add_agent_patch_rollback_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "patch-rollback",
        help="Restore files from .eurika_backups (default: latest run)",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--run-id", type=str, default=None, metavar="ID", help="Restore from this run_id (default: latest)")
    p.add_argument("--list", action="store_true", help="List available backup run_ids and exit")


def _add_agent_cycle_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "cycle",
        help="Run scan → arch-review → patch-apply --apply --verify; on test failure, hints rollback",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window for arch-review (default: 5)")
    p.add_argument("--dry-run", action="store_true", help="Run scan → arch-review → patch-plan only; do not apply or verify")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress scan/arch output; only final report JSON to stdout")


def _add_agent_learning_summary_command(
    agent_subparsers: argparse._SubParsersAction,
) -> None:
    p = agent_subparsers.add_parser(
        "learning-summary",
        help="Summarize accumulated self-refactoring outcomes",
    )
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        return handlers.handle_help(parser)

    dispatch = {
        "help": lambda: handlers.handle_help(parser),
        "scan": lambda: handlers.handle_scan(args),
        "arch-summary": lambda: handlers.handle_arch_summary(args),
        "arch-history": lambda: handlers.handle_arch_history(args),
        "history": lambda: handlers.handle_arch_history(args),
        "report": lambda: handlers.handle_report(args),
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
        agent_dispatch = {
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


if __name__ == "__main__":
    sys.exit(main())
