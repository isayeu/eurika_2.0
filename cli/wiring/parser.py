"""Parser wiring extracted from eurika_cli entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser(*, version: str) -> argparse.ArgumentParser:
    """Configure top-level CLI parser and subcommands."""
    parser = argparse.ArgumentParser(
        prog="eurika",
        description="Eurika — architecture analysis and refactoring assistant",
        epilog="Product (5 modes): scan | doctor | fix | cycle | explain. Use eurika help for full list.",
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {version}")
    subparsers = parser.add_subparsers(dest="command")

    _add_product_commands(subparsers)  # scan, doctor, fix, explain — ROADMAP этап 5
    _add_other_commands(subparsers)
    _add_ml_market_commands(subparsers)
    _add_agent_commands(subparsers)

    subparsers.add_parser("help", help="Show Eurika command overview")

    return parser


def _add_fix_cycle_common_args(parser: argparse.ArgumentParser, *, include_no_llm: bool = False) -> None:
    """Add arguments shared by fix and cycle commands."""
    parser.add_argument("path", nargs="*", type=Path, default=[Path(".")], metavar="PATH", help="Project root(s); default: .")
    parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Only build patch plan, do not apply")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output; final JSON only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose progress (DEBUG)")
    if include_no_llm:
        parser.add_argument("--no-llm", action="store_true", help="Architect: use template only (no API key)")
    parser.add_argument("--no-clean-imports", action="store_true", help="Skip remove-unused-imports step (default: included)")
    parser.add_argument("--no-code-smells", action="store_true", help="Skip refactor_code_smell (long_function, deep_nesting) ops (default: included)")
    parser.add_argument("--verify-cmd", type=str, default=None, metavar="CMD", help="Override verify command (e.g. 'python manage.py test'); else [tool.eurika] verify_cmd or pytest")
    parser.add_argument("--verify-timeout", type=int, default=None, metavar="SEC", help="Verify step timeout in seconds (default: 300 or EURIKA_VERIFY_TIMEOUT or [tool.eurika] verify_timeout)")
    parser.add_argument("--interval", type=int, default=0, metavar="SEC", help="Auto-run: repeat every SEC seconds (0=once, Ctrl+C to stop)")
    parser.add_argument("--runtime-mode", choices=["assist", "hybrid", "auto"], default="assist", help="Agent runtime mode (default: assist)")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt for approvals in hybrid mode")
    parser.add_argument("--session-id", type=str, default=None, help="Session key for reusing approval/rejection memory")
    parser.add_argument("--allow-campaign-retry", action="store_true", help="Allow retry of operations skipped by campaign memory for this run only")
    parser.add_argument("--allow-low-risk-campaign", action="store_true", help="Allow low-risk ops (e.g. remove_unused_import) through campaign skip")
    parser.add_argument("--online", action="store_true", help="Force fresh Knowledge fetch in doctor stage (ROADMAP 3.0.3)")
    parser.add_argument("--apply-suggested-policy", action="store_true", help="Apply suggested policy from last doctor/fix telemetry (ROADMAP 2.9.4)")
    parser.add_argument("--team-mode", action="store_true", help="Propose only: save plan to .eurika/pending_plan.json and exit (ROADMAP 3.0.4)")
    parser.add_argument("--apply-approved", action="store_true", help="Apply only ops with team_decision=approve from pending_plan.json (ROADMAP 3.0.4)")
    parser.add_argument("--apply-from-report", action="store_true", help="Apply patch_plan from last dry-run (eurika_fix_report.json); skips scan+diagnose")
    parser.add_argument("--approve-ops", type=str, default=None, metavar="IDX[,IDX...]", help="Explicitly approve operation indexes (1-based), e.g. --approve-ops 1,3,5")
    parser.add_argument("--reject-ops", type=str, default=None, metavar="IDX[,IDX...]", help="Explicitly reject operation indexes (1-based), e.g. --reject-ops 2,4")


def _add_product_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register product commands first (ROADMAP этап 5)."""
    scan_parser = subparsers.add_parser("scan", help="Scan project(s), update artifacts, report (ROADMAP 3.0.1: multi-repo)")
    scan_parser.add_argument("path", nargs="*", type=Path, default=[Path(".")], metavar="PATH", help="Project root(s); default: .")
    scan_parser.add_argument("--format", "-f", choices=["text", "markdown"], default="text", help="Output format (default: text)")
    scan_parser.add_argument("--color", action="store_true", default=None, dest="color", help="Force color output (default: auto from TTY)")
    scan_parser.add_argument("--no-color", action="store_false", dest="color", help="Disable color output")

    doctor_parser = subparsers.add_parser("doctor", help="Diagnostics only: report + architect (no patches) (3.0.1: multi-repo)")
    doctor_parser.add_argument("path", nargs="*", type=Path, default=[Path(".")], metavar="PATH", help="Project root(s); default: .")
    doctor_parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    doctor_parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output; JSON report only")
    doctor_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose progress (DEBUG)")
    doctor_parser.add_argument("--no-llm", action="store_true", help="Architect: use template only")
    doctor_parser.add_argument("--online", action="store_true", help="Force fresh fetch of Knowledge (bypass cache) (ROADMAP 3.0.3)")
    doctor_parser.add_argument("--runtime-mode", choices=["assist", "hybrid", "auto"], default="assist", help="Agent runtime mode (default: assist)")

    fix_parser = subparsers.add_parser("fix", help="Full cycle: scan → plan → patch → verify (3.0.1: multi-repo)")
    _add_fix_cycle_common_args(fix_parser, include_no_llm=True)

    cycle_parser = subparsers.add_parser("cycle", help="Full ritual: scan → doctor → fix (3.0.1: multi-repo)")
    _add_fix_cycle_common_args(cycle_parser, include_no_llm=True)

    explain_parser = subparsers.add_parser("explain", help="Explain role and risks of a module")
    explain_parser.add_argument("module", type=str, help="Module path or name (e.g. architecture_diff.py or cli/handlers.py)")
    explain_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    explain_parser.add_argument("--window", type=int, default=5, help="History window for patch-plan (default: 5)")

    watch_parser = subparsers.add_parser("watch", help="Watch for .py changes and run fix (ROADMAP 2.6.2)")
    watch_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    watch_parser.add_argument("--poll", type=int, default=5, metavar="SEC", help="Poll interval (default: 5)")
    watch_parser.add_argument("--window", type=int, default=5, help="History window for patch-plan (default: 5)")
    watch_parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    watch_parser.add_argument("--no-clean-imports", action="store_true", help="Skip remove-unused-imports")
    watch_parser.add_argument("--no-code-smells", action="store_true", help="Skip refactor_code_smell ops")


def _add_other_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register other (non-agent) commands: report, arch-*, self-check, serve, etc."""
    summary_parser = subparsers.add_parser("arch-summary", help="Print architecture summary for project")
    summary_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    summary_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    history_parser = subparsers.add_parser("arch-history", help="Print architecture evolution report")
    history_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    history_parser.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    history_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    history_alias = subparsers.add_parser("history", help="Alias for arch-history (architecture evolution report)")
    history_alias.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    history_alias.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    history_alias.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    diff_parser = subparsers.add_parser("arch-diff", help="Diff two architecture snapshots (self_map JSON files)")
    diff_parser.add_argument("old", type=Path, help="Old self_map.json")
    diff_parser.add_argument("new", type=Path, help="New self_map.json")
    diff_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")

    self_check_parser = subparsers.add_parser("self-check", help="Run full scan on Eurika itself (self-analysis ritual)")
    self_check_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root to analyze (default: .)")
    self_check_parser.add_argument("--format", "-f", choices=["text", "markdown"], default="text", help="Output format (default: text)")
    self_check_parser.add_argument("--color", action="store_true", default=None, dest="color", help="Force color output (default: auto from TTY)")
    self_check_parser.add_argument("--no-color", action="store_false", dest="color", help="Disable color output")
    self_check_parser.add_argument("--strict", action="store_true", help="R5: exit 1 if self-guard violations (layer, file size)")

    report_parser = subparsers.add_parser("report", help="Print architecture summary + evolution report (no rescan)")
    report_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    report_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")
    report_parser.add_argument("--window", type=int, default=5, help="History window for evolution (default: 5)")

    snapshot_parser = subparsers.add_parser("report-snapshot", help="Print CYCLE_REPORT-style markdown from doctor/fix artifacts (for updating CYCLE_REPORT.md)")
    snapshot_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")

    learning_kpi_parser = subparsers.add_parser("learning-kpi", help="KPI verify_success_rate by smell|action|target + recommendations (ROADMAP)")
    learning_kpi_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    learning_kpi_parser.add_argument("--json", action="store_true", help="Output JSON (machine-readable)")
    learning_kpi_parser.add_argument("--top-n", type=int, default=5, metavar="N", help="Top N for promote/deprioritize (default: 5)")
    learning_kpi_parser.add_argument("--polygon", action="store_true", help="Filter to eurika/polygon/ targets only (drill view)")

    whitelist_draft_parser = subparsers.add_parser(
        "whitelist-draft",
        help="Generate operation whitelist draft from campaign verify_success candidates",
    )
    whitelist_draft_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    whitelist_draft_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: .eurika/operation_whitelist.draft.json)",
    )
    whitelist_draft_parser.add_argument(
        "--min-success",
        type=int,
        default=2,
        metavar="N",
        help="Minimum verify_success count to include candidate (default: 2)",
    )
    whitelist_draft_parser.add_argument(
        "--allow-auto",
        action="store_true",
        help="Set allow_in_auto=true in generated draft entries",
    )
    whitelist_draft_parser.add_argument(
        "--kinds",
        type=str,
        default="extract_block_to_helper",
        metavar="K1,K2,...",
        help="Comma-separated operation kinds to include (default: extract_block_to_helper)",
    )
    whitelist_draft_parser.add_argument(
        "--all-kinds",
        action="store_true",
        help="Disable kind filter and include all candidate kinds",
    )

    campaign_undo_parser = subparsers.add_parser("campaign-undo", help="Undo applied campaign from checkpoint (ROADMAP 3.6.4)")
    campaign_undo_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    campaign_undo_parser.add_argument("--checkpoint-id", type=str, default=None, help="Undo a specific campaign checkpoint id")
    campaign_undo_parser.add_argument("--list", action="store_true", help="List recent campaign checkpoints and exit")

    architect_parser = subparsers.add_parser("architect", help="Print architect's interpretation; LLM if OPENAI_API_KEY set (optional OPENAI_BASE_URL, OPENAI_MODEL for OpenRouter)")
    architect_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    architect_parser.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    architect_parser.add_argument("--no-llm", action="store_true", help="Use template only (no LLM call)")
    architect_parser.add_argument("--online", action="store_true", help="Force fresh Knowledge fetch (bypass cache) (ROADMAP 3.0.3)")

    suggest_plan_parser = subparsers.add_parser("suggest-plan", help="Print heuristic refactoring plan from summary and risks (ROADMAP §7)")
    suggest_plan_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    suggest_plan_parser.add_argument("--window", type=int, default=5, help="History window for context (default: 5)")

    clean_imports_parser = subparsers.add_parser("clean-imports", help="Remove unused imports from Python files (Killer-feature: dead code)")
    clean_imports_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    clean_imports_parser.add_argument("--apply", action="store_true", help="Write changes to files (default: dry-run)")

    prove_cycle_parser = subparsers.add_parser(
        "prove-cycle",
        help=(
            "Deterministic patch→verify→learning on synthetic drill (no LLM). "
            "With --propose: seed polygon drill into Approvals (HITL), no apply."
        ),
    )
    prove_cycle_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    prove_cycle_parser.add_argument("--dry-run", action="store_true", help="Simulate only; do not apply")
    prove_cycle_parser.add_argument(
        "--propose",
        action="store_true",
        help=(
            "C.14 HITL: seed a polygon drill into .eurika/pending_plan.json; "
            "do not apply (approve in Approvals). See --drill."
        ),
    )
    prove_cycle_parser.add_argument(
        "--drill",
        default="imports",
        metavar="NAME",
        help=(
            "With --propose: imports (default), extractable_block, "
            "long_function, or llm_extract"
        ),
    )
    prove_cycle_parser.add_argument("--quiet", "-q", action="store_true", help="JSON output only")
    prove_cycle_parser.add_argument(
        "--verify-timeout",
        type=int,
        default=60,
        metavar="SEC",
        help="Verify step timeout in seconds (default: 60)",
    )

    tg_parser = subparsers.add_parser(
        "telegram-bot",
        help="C.12: Telegram long-poll → chat_send (HITL apply stays in Approvals)",
    )
    tg_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    tg_parser.add_argument("--token", default=None, help="Bot token (else EURIKA_TELEGRAM_BOT_TOKEN)")
    tg_parser.add_argument(
        "--chat-ids",
        default=None,
        help="Allowlist chat ids, comma-separated (else EURIKA_TELEGRAM_CHAT_IDS)",
    )
    tg_parser.add_argument(
        "--allow-any",
        action="store_true",
        help="Dogfood only: accept any chat_id (or EURIKA_TELEGRAM_ALLOW_ANY=1)",
    )
    tg_parser.add_argument(
        "--once",
        action="store_true",
        help="One getUpdates poll then exit (tests / smoke)",
    )
    tg_parser.add_argument(
        "--poll-timeout",
        type=int,
        default=25,
        metavar="SEC",
        help="Long-poll timeout seconds (default: 25)",
    )

    serve_parser = subparsers.add_parser("serve", help="Run JSON API server for future UI (GET /api/summary, /api/history, /api/diff)")
    serve_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    serve_parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")

    learn_github_parser = subparsers.add_parser("learn-github", help="Clone and scan curated OSS repos for pattern library (ROADMAP 3.0.5.1, 3.0.5.2)")
    learn_github_parser.add_argument("path", nargs="?", default=".", type=Path, help="Project root; cache_dir = path/../curated_repos (default: .)")
    learn_github_parser.add_argument("--config", type=Path, default=None, help="Path to curated_repos.json (default: docs/curated_repos.example.json)")
    learn_github_parser.add_argument("--scan", action="store_true", help="Run eurika scan on each cloned repo")
    learn_github_parser.add_argument("--build-patterns", action="store_true", help="Build pattern library from repos with self_map.json, save to .eurika/pattern_library.json")
    learn_github_parser.add_argument("--search", type=str, default=None, metavar="QUERY", help="GitHub search query (e.g. 'language:python stars:>1000'). Replaces curated list (ROADMAP 3.0.5.2)")
    learn_github_parser.add_argument("--search-limit", type=int, default=5, help="Max repos from --search (default: 5)")
    learn_github_parser.add_argument("--limit-repos", type=int, default=None, metavar="N", help="Use only first N repos (for faster pattern build). Default: all.")
    learn_github_parser.add_argument("--light", action="store_true", help="Use lightweight curated list (starlette, httpx) — faster clone/scan")


def _add_ml_market_commands(subparsers: argparse._SubParsersAction) -> None:
    """Paper ML market loop: sync klines → paper labels → train (no live orders)."""
    ml = subparsers.add_parser(
        "ml-market",
        help="Paper market ML: sync klines, paper BUY/SELL labels, train CPU policy (no live orders)",
    )
    ml_sub = ml.add_subparsers(dest="ml_market_command", required=True)

    sync_p = ml_sub.add_parser("sync", help="Fetch Binance klines into .eurika/ml/market/")
    sync_p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    sync_p.add_argument("--symbol", default="BTCUSDT", help="Symbol (default: BTCUSDT)")
    sync_p.add_argument("--interval", default="1h", help="Kline interval (default: 1h)")
    sync_p.add_argument("--limit", type=int, default=500, help="Max klines per request (default: 500)")
    sync_p.add_argument(
        "--market",
        default="spot",
        choices=["spot", "futures", "both"],
        help="Candle market: spot, USD-M futures, or both (default: spot)",
    )

    paper_p = ml_sub.add_parser("paper", help="Backfill paper trades + correct/incorrect labels")
    paper_p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    paper_p.add_argument("--symbol", default="BTCUSDT")
    paper_p.add_argument("--interval", default="1h")
    paper_p.add_argument(
        "--market",
        default="spot",
        choices=["spot", "futures"],
        help="Which candle series to label (default: spot)",
    )
    paper_p.add_argument("--window", type=int, default=32, help="Feature window bars (default: 32)")
    paper_p.add_argument("--horizon", type=int, default=4, help="Label horizon bars (default: 4)")
    paper_p.add_argument(
        "--fee",
        type=float,
        default=None,
        help="Override total round-trip fee (default: market maker/taker schedule)",
    )
    paper_p.add_argument("--thr", type=float, default=0.0, help="Edge threshold for correct (default: 0)")
    paper_p.add_argument("--replace", action="store_true", help="Overwrite paper_trades.jsonl instead of append")
    paper_p.add_argument("--use-model", action="store_true", help="Use trained weights for actions (else momentum)")

    train_p = ml_sub.add_parser("train", help="Train tiny CPU policy on paper_trades.jsonl")
    train_p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    train_p.add_argument("--epochs", type=int, default=40, help="Training epochs (default: 40)")

    status_p = ml_sub.add_parser("status", help="Show market / paper / weights status")
    status_p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")


def _add_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register experimental AgentCore-related commands."""
    agent_parser = subparsers.add_parser("agent", help="Experimental AgentCore helpers (v0.2 draft, read-only)")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)

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
    p = agent_subparsers.add_parser("arch-review", help="Run experimental AgentCore arch_review over existing artifacts")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_arch_evolution_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("arch-evolution", help="Run experimental AgentCore arch_evolution_query over history only")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_prioritize_modules_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("prioritize-modules", help="Run AgentCore arch_review and print only module priorities")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_feedback_summary_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("feedback-summary", help="Summarize manual feedback on AgentCore proposals")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")


def _add_agent_action_dry_run_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("action-dry-run", help="Build ActionPlan from diagnostics and print it (no execution)")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_action_simulate_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("action-simulate", help="Build ActionPlan and run ExecutorSandbox dry-run (no code changes)")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")


def _add_agent_action_apply_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("action-apply", help="Build ActionPlan and execute; backups in .eurika_backups unless --no-backup")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window (default: 5)")
    p.add_argument("--no-backup", action="store_true", help="Do not create backups")


def _add_agent_patch_plan_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("patch-plan", help="Build patch plan from diagnostics and print or write to file")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window size (default: 5)")
    p.add_argument("--output", "-o", type=Path, default=None, metavar="FILE", help="Write patch plan JSON to FILE")


def _add_agent_patch_apply_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("patch-apply", help="Apply patch plan (append TODO comments); default is dry-run")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window for building plan (default: 5)")
    p.add_argument("--apply", action="store_true", help="Actually write to files (default: dry-run only)")
    p.add_argument("--no-backup", action="store_true", help="Do not create backups in .eurika_backups/")
    p.add_argument("--verify", action="store_true", help="After --apply, run pytest and report success/failure")


def _add_agent_patch_rollback_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("patch-rollback", help="Restore files from .eurika_backups (default: latest run)")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--run-id", type=str, default=None, metavar="ID", help="Restore from this run_id (default: latest)")
    p.add_argument("--list", action="store_true", help="List available backup run_ids and exit")


def _add_agent_cycle_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("cycle", help="Run scan → arch-review → patch-apply --apply --verify; on test failure, hints rollback")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")
    p.add_argument("--window", type=int, default=5, help="History window for arch-review (default: 5)")
    p.add_argument("--dry-run", action="store_true", help="Run scan → arch-review → patch-plan only; do not apply or verify")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress scan/arch output; only final report JSON to stdout")
    p.add_argument("--no-llm", action="store_true", help="Architect: use template only (no API call)")
    p.add_argument("--runtime-mode", choices=["assist", "hybrid", "auto"], default="assist", help="Agent runtime mode (default: assist)")
    p.add_argument("--non-interactive", action="store_true", help="Do not prompt for approvals in hybrid mode")
    p.add_argument("--session-id", type=str, default=None, help="Session key for reusing approval/rejection memory")


def _add_agent_learning_summary_command(agent_subparsers: argparse._SubParsersAction) -> None:
    p = agent_subparsers.add_parser("learning-summary", help="Summarize accumulated self-refactoring outcomes")
    p.add_argument("path", nargs="?", default=".", type=Path, help="Project root (default: .)")


