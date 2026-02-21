"""Core CLI command handlers (scan/summary/history/diff/self-check/report/explain).

Extracted from cli.handlers to reduce its fan-out and move towards the
target cli layout described in Architecture.md.

Public surface is re-exported via cli.handlers to keep backward
compatibility for any external imports.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from cli.orchestrator import _knowledge_topics_from_env_or_summary
from architecture_pipeline import print_arch_diff, print_arch_history, print_arch_summary
from runtime_scan import run_scan

def _err(msg: str) -> None:
    """Print unified error message to stderr."""
    print(f'eurika: {msg}', file=sys.stderr)

def handle_help(parser: Any) -> int:
    """Print high-level command overview and detailed argparse help (ROADMAP этап 5: 4 product modes)."""
    print('Eurika — architecture analysis and refactoring assistant (v1.2.6)')
    print()
    print('Product (4 modes):')
    print('  scan [path]              full scan, update artifacts, report')
    print('  doctor [path]           diagnostics: report + architect (no patches)')
    print('  fix [path]              full cycle: scan → plan → patch → verify')
    print('  explain <module> [path] role and risks of a module')
    print()
    print('Other: report, architect, suggest-plan, arch-summary, arch-history, history, arch-diff, self-check, clean-imports, serve')
    print('Advanced: eurika agent <cmd>  (patch-plan, patch-apply, patch-rollback, cycle, ...)')
    print()
    print('  --help after any command for details.')
    print()
    parser.print_help()
    return 0

def _paths_from_args(args: Any) -> list[Path]:
    """Normalize path(s) from args (ROADMAP 3.0.1 multi-repo). Returns list of resolved Paths."""
    raw = getattr(args, 'path', None)
    if not raw:
        return [Path(".").resolve()]
    if isinstance(raw, Path):
        return [raw.resolve()]
    return [Path(p).resolve() for p in raw]


def handle_scan(args: Any) -> int:
    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            print(f"\n--- Project {i + 1}/{len(paths)}: {path} ---\n", file=sys.stderr)
        if _check_path(path) != 0:
            exit_code = 1
            continue
        fmt = getattr(args, 'format', 'text')
        color = getattr(args, 'color', None)
        if run_scan(path, format=fmt, color=color) != 0:
            exit_code = 1
    return exit_code

def handle_self_check(args: Any) -> int:
    """Run full scan on the project (self-analysis ritual: Eurika analyzes itself)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    print('eurika: self-check — analyzing project architecture...', file=sys.stderr)
    fmt = getattr(args, 'format', 'text')
    color = getattr(args, 'color', None)
    code = run_scan(path, format=fmt, color=color)
    # File size limits (ROADMAP 3.1-arch.3)
    fs_report = _format_file_size_block(path)
    if fs_report:
        print(fs_report, file=sys.stderr)
    return code


def _format_file_size_block(path: Path) -> str:
    """Return file size limits report for self-check (3.1-arch.3)."""
    from eurika.checks import check_file_size_limits

    candidates, must_split = check_file_size_limits(path, include_tests=True)
    if not candidates and not must_split:
        return ""
    lines = ["", "FILE SIZE LIMITS (ROADMAP 3.1-arch.3)", "  >400 LOC = candidate; >600 LOC = must split", ""]
    if must_split:
        lines.append("Must split (>600):")
        for rel, count in must_split[:10]:
            lines.append(f"  - {rel} ({count})")
        if len(must_split) > 10:
            lines.append(f"  ... +{len(must_split) - 10} more")
        lines.append("")
    if candidates:
        lines.append("Candidates (>400):")
        for rel, count in candidates[:5]:
            lines.append(f"  - {rel} ({count})")
        if len(candidates) > 5:
            lines.append(f"  ... +{len(candidates) - 5} more")
    return "\n".join(lines)

def _check_path(path: Path, must_be_dir: bool=True) -> int:
    """Return 0 if path is valid, 1 and print error otherwise."""
    if not path.exists():
        _err(f'path does not exist: {path}')
        return 1
    if must_be_dir and (not path.is_dir()):
        _err(f'not a directory: {path}')
        return 1
    return 0

def handle_arch_summary(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    if getattr(args, 'json', False):
        from eurika.api import get_summary
        data = get_summary(path)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    return print_arch_summary(path)

def handle_arch_history(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    window = getattr(args, 'window', 5)
    if getattr(args, 'json', False):
        from eurika.api import get_history
        data = get_history(path, window=window)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    return print_arch_history(path, window=window)

def handle_arch_diff(args: Any) -> int:
    old = args.old.resolve()
    new = args.new.resolve()
    if not old.exists():
        _err(f'old self_map not found: {old}')
        return 1
    if not new.exists():
        _err(f'new self_map not found: {new}')
        return 1
    if getattr(args, 'json', False):
        from eurika.api import get_diff
        data = get_diff(old, new)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    return print_arch_diff(old, new)

def handle_report(args: Any) -> int:
    """Print architecture summary + evolution report (no rescan)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    window = getattr(args, 'window', 5)
    if getattr(args, 'json', False):
        from eurika.api import get_summary, get_history
        data = {'summary': get_summary(path), 'history': get_history(path, window=window)}
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    code1 = print_arch_summary(path)
    code2 = print_arch_history(path, window=window)
    return 0 if code1 == 0 and code2 == 0 else 1


def handle_report_snapshot(args: Any) -> int:
    """Print CYCLE_REPORT-style markdown from doctor/fix artifacts for pasting into CYCLE_REPORT.md (3.1-arch.5 thin)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from report.report_snapshot import format_report_snapshot

    print(format_report_snapshot(path))
    return 0


def handle_explain(args: Any) -> int:
    """Explain role and risks of a given module (3.1-arch.5 thin)."""
    module_arg = getattr(args, "module", None)
    if not module_arg:
        _err("module path or name is required")
        return 1
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import explain_module

    text, err = explain_module(path, module_arg, window=getattr(args, "window", 5))
    if err:
        _err(err)
        return 1
    print(text)
    return 0

def handle_doctor(args: Any) -> int:
    """Diagnostics only: report + architect (no patches). Saves to eurika_doctor_report.json (3.0.1: multi-repo)."""
    paths = _paths_from_args(args)
    exit_code = 0
    from cli.orchestrator import run_cycle
    from eurika.smells.rules import summary_to_text
    for i, path in enumerate(paths):
        if len(paths) > 1:
            print(f"\n--- Project {i + 1}/{len(paths)}: {path} ---\n", file=sys.stderr)
        if _check_path(path) != 0:
            exit_code = 1
            continue
        data = run_cycle(path, mode='doctor', runtime_mode=getattr(args, 'runtime_mode', 'assist'), window=getattr(args, 'window', 5), no_llm=getattr(args, 'no_llm', False))
        if data.get('error'):
            _err(data['error'])
            exit_code = 1
            continue
        summary = data['summary']
        history = data['history']
        patch_plan = data['patch_plan']
        architect_text = data['architect_text']
        suggested_policy = data.get('suggested_policy') or {}
        print(summary_to_text(summary))
        print()
        print(history.get('evolution_report', ''))
        print()
        print(architect_text)
        if suggested_policy.get('suggested'):
            sugg = suggested_policy['suggested']
            telemetry = suggested_policy.get('telemetry') or {}
            apply_rate = telemetry.get('apply_rate', 'N/A')
            rollback_rate = telemetry.get('rollback_rate', 'N/A')
            print()
            print('Suggested policy (ROADMAP 2.9.4):')
            print(f'  (apply_rate={apply_rate}, rollback_rate={rollback_rate})')
            for k, v in sugg.items():
                print(f'  export {k}={v}')
            print('  # Or run fix/cycle with --apply-suggested-policy')
        report = {'summary': summary, 'history': history, 'architect': architect_text, 'patch_plan': patch_plan}
        if suggested_policy:
            report['suggested_policy'] = suggested_policy
        fix_path = path / 'eurika_fix_report.json'
        if fix_path.exists():
            try:
                fix = json.loads(fix_path.read_text(encoding='utf-8'))
                if fix.get('telemetry'):
                    report['last_fix_telemetry'] = fix['telemetry']
            except Exception:
                pass
        try:
            report_path = path / 'eurika_doctor_report.json'
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'\neurika: eurika_doctor_report.json written to {report_path}', file=sys.stderr)
        except Exception:
            pass
    return exit_code

def handle_fix(args: Any) -> int:
    """Full cycle: scan → plan → patch-apply --apply --verify (3.0.1: multi-repo)."""
    from types import SimpleNamespace
    from cli.agent_handlers import handle_agent_cycle
    from cli.orchestration.doctor import load_suggested_policy_for_apply
    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            print(f"\n--- Project {i + 1}/{len(paths)}: {path} ---\n", file=sys.stderr)
        if getattr(args, 'apply_suggested_policy', False):
            sugg = load_suggested_policy_for_apply(path)
            if sugg:
                os.environ.update(sugg)
            os.environ["EURIKA_IGNORE_CAMPAIGN"] = "1"  # bypass campaign skip so ops get a chance
        fix_args = SimpleNamespace(
            path=path, window=getattr(args, 'window', 5), dry_run=getattr(args, 'dry_run', False),
            quiet=getattr(args, 'quiet', False), no_clean_imports=getattr(args, 'no_clean_imports', False),
            no_code_smells=getattr(args, 'no_code_smells', False), verify_cmd=getattr(args, 'verify_cmd', None),
            verify_timeout=getattr(args, 'verify_timeout', None), interval=getattr(args, 'interval', 0),
            runtime_mode=getattr(args, 'runtime_mode', 'assist'),
            non_interactive=getattr(args, 'non_interactive', False),
            session_id=getattr(args, 'session_id', None),
        )
        if handle_agent_cycle(fix_args) != 0:
            exit_code = 1
    return exit_code

def handle_cycle(args: Any) -> int:
    """Full ritual: scan → doctor → fix (3.0.1: multi-repo)."""
    from types import SimpleNamespace
    from cli.agent_handlers import _run_cycle_with_mode
    from cli.orchestration.doctor import load_suggested_policy_for_apply
    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            print(f"\n--- Project {i + 1}/{len(paths)}: {path} ---\n", file=sys.stderr)
        if getattr(args, 'apply_suggested_policy', False):
            sugg = load_suggested_policy_for_apply(path)
            if sugg:
                os.environ.update(sugg)
            os.environ["EURIKA_IGNORE_CAMPAIGN"] = "1"  # bypass campaign skip so ops get a chance
        cycle_args = SimpleNamespace(
            path=path, window=getattr(args, 'window', 5), dry_run=getattr(args, 'dry_run', False),
            quiet=getattr(args, 'quiet', False), no_llm=getattr(args, 'no_llm', False),
            no_clean_imports=getattr(args, 'no_clean_imports', False), no_code_smells=getattr(args, 'no_code_smells', False),
            verify_cmd=getattr(args, 'verify_cmd', None), verify_timeout=getattr(args, 'verify_timeout', None),
            interval=getattr(args, 'interval', 0),
            runtime_mode=getattr(args, 'runtime_mode', 'assist'),
            non_interactive=getattr(args, 'non_interactive', False),
            session_id=getattr(args, 'session_id', None),
        )
        if _run_cycle_with_mode(cycle_args, mode='full') != 0:
            exit_code = 1
    return exit_code

def handle_architect(args: Any) -> int:
    """Print architect's interpretation (template or optional LLM), with patch-plan context."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_summary, get_history, get_patch_plan, get_recent_events
    from eurika.reasoning.architect import interpret_architecture
    summary = get_summary(path)
    if summary.get('error'):
        _err(summary.get('error', 'unknown'))
        return 1
    window = getattr(args, 'window', 5)
    history = get_history(path, window=window)
    patch_plan = get_patch_plan(path, window=window)
    recent_events = get_recent_events(path, limit=5, types=('patch', 'learn'))
    use_llm = not getattr(args, 'no_llm', False)
    from eurika.knowledge import CompositeKnowledgeProvider, LocalKnowledgeProvider, OfficialDocsProvider, ReleaseNotesProvider
    cache_dir = path / '.eurika' / 'knowledge_cache'
    knowledge_provider = CompositeKnowledgeProvider([LocalKnowledgeProvider(path / 'eurika_knowledge.json'), OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=86400), ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=86400)])
    knowledge_topic = _knowledge_topics_from_env_or_summary(summary)
    text = interpret_architecture(summary, history, use_llm=use_llm, patch_plan=patch_plan, knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic, recent_events=recent_events)
    print(text)
    return 0

def handle_suggest_plan(args: Any) -> int:
    """Print heuristic refactoring plan (3.1-arch.5 thin)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_suggest_plan_text

    plan = get_suggest_plan_text(path, window=getattr(args, "window", 5))
    if plan.startswith("Error:"):
        _err(plan)
        return 1
    print(plan)
    return 0

def handle_clean_imports(args: Any) -> int:
    """Remove unused imports from Python files (3.1-arch.5 thin)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import clean_imports_scan_apply

    apply_changes = getattr(args, "apply", False)
    modified = clean_imports_scan_apply(path, apply_changes=apply_changes)
    if not modified:
        print("eurika: no unused imports found.", file=sys.stderr)
        return 0
    if apply_changes:
        print(f"eurika: removed unused imports from {len(modified)} file(s).", file=sys.stderr)
    else:
        print(f"eurika: would remove unused imports from {len(modified)} file(s) (use --apply to write):", file=sys.stderr)
    for m in modified[:10]:
        print(f"  {m}", file=sys.stderr)
    if len(modified) > 10:
        print(f"  ... and {len(modified) - 10} more", file=sys.stderr)
    print(json.dumps({"modified": modified}, indent=2, ensure_ascii=False))
    return 0

def handle_watch(args: Any) -> int:
    """Watch for .py file changes and run fix when detected (ROADMAP 2.6.2)."""
    import time
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    poll_sec = int(getattr(args, 'poll', 5) or 5)
    quiet = getattr(args, 'quiet', False)
    skip_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", ".eurika_backups", ".eurika"}

    def _collect_mtimes() -> dict:
        out: dict = {}
        for f in path.rglob("*.py"):
            if any(s in f.parts for s in skip_dirs):
                continue
            try:
                out[str(f.relative_to(path))] = f.stat().st_mtime
            except (OSError, ValueError):
                pass
        return out

    prev = _collect_mtimes()
    if not quiet:
        print(f"eurika watch: monitoring {len(prev)} .py files (poll every {poll_sec}s, Ctrl+C to stop)", file=sys.stderr)
    run_count = 0
    try:
        while True:
            time.sleep(poll_sec)
            curr = _collect_mtimes()
            if curr != prev:
                run_count += 1
                if not quiet:
                    print(f"\neurika watch: changes detected, running fix (#{run_count})...", file=sys.stderr)
                from types import SimpleNamespace
                fix_args = SimpleNamespace(
                    path=path, window=getattr(args, 'window', 5), dry_run=False,
                    quiet=quiet, no_clean_imports=getattr(args, 'no_clean_imports', False),
                    no_code_smells=getattr(args, 'no_code_smells', False), interval=0,
                )
                from cli.agent_handlers import handle_agent_cycle
                handle_agent_cycle(fix_args)
                prev = _collect_mtimes()
            else:
                prev = curr
    except KeyboardInterrupt:
        if not quiet:
            print("\neurika watch: stopped (Ctrl+C)", file=sys.stderr)
    return 0


def handle_serve(args: Any) -> int:
    """Run JSON API HTTP server for future UI."""
    from eurika.api.serve import run_server
    run_server(host=args.host, port=args.port, project_root=args.path)
    return 0
