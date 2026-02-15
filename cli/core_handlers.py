"""Core CLI command handlers (scan/summary/history/diff/self-check/report/explain).

Extracted from cli.handlers to reduce its fan-out and move towards the
target cli layout described in Architecture.md.

Public surface is re-exported via cli.handlers to keep backward
compatibility for any external imports.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any
from cli.orchestrator import _knowledge_topics_from_env_or_summary
from eurika.smells.detector import get_remediation_hint, severity_to_level
from architecture_pipeline import print_arch_diff, print_arch_history, print_arch_summary
from eurika.core.pipeline import run_full_analysis
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

def handle_scan(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    fmt = getattr(args, 'format', 'text')
    color = getattr(args, 'color', None)
    return run_scan(path, format=fmt, color=color)

def handle_self_check(args: Any) -> int:
    """Run full scan on the project (self-analysis ritual: Eurika analyzes itself)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    print('eurika: self-check — analyzing project architecture...', file=sys.stderr)
    fmt = getattr(args, 'format', 'text')
    color = getattr(args, 'color', None)
    return run_scan(path, format=fmt, color=color)

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

def handle_explain(args: Any) -> int:
    """Explain role and risks of a given module."""
    module_arg = getattr(args, 'module', None)
    if not module_arg:
        _err('module path or name is required')
        return 1
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    try:
        snapshot = run_full_analysis(path, update_artifacts=False)
    except Exception as exc:
        _err(f'failed to build snapshot: {exc}')
        return 1
    graph = snapshot.graph
    smells = snapshot.smells
    summary = snapshot.summary or {}
    mod = module_arg
    from pathlib import Path as _P
    m_path = _P(module_arg)
    if m_path.is_absolute():
        try:
            mod = str(m_path.relative_to(path))
        except ValueError:
            mod = m_path.name
    nodes = list(graph.nodes)
    target = None
    if mod in nodes:
        target = mod
    else:
        candidates = [n for n in nodes if n.endswith('/' + mod) or n.endswith(mod)]
        if len(candidates) == 1:
            target = candidates[0]
        elif len(candidates) > 1:
            _err(f"ambiguous module '{module_arg}'; candidates: {', '.join(candidates)}")
            return 1
    if not target:
        _err(f"module '{module_arg}' not in graph (run 'eurika scan .' to refresh self_map.json)")
        return 1
    fan = graph.fan_in_out()
    fi, fo = fan.get(target, (0, 0))
    central = {c['name'] for c in summary.get('central_modules') or []}
    is_central = target in central
    module_smells = [s for s in smells if target in s.nodes]
    risks = summary.get('risks') or []
    module_risks = [r for r in risks if target in r]
    print(f'MODULE EXPLANATION: {target}')
    print()
    print('Role:')
    print(f'- fan-in : {fi}')
    print(f'- fan-out: {fo}')
    print(f"- central: {('yes' if is_central else 'no')}")
    print()
    print('Smells:')
    if not module_smells:
        print('- none detected for this module')
    else:
        for s in module_smells:
            level = severity_to_level(s.severity)
            print(f'- [{s.type}] ({level}) severity={s.severity:.2f} — {s.description}')
            print(f'  → {get_remediation_hint(s.type)}')
    print()
    print('Risks (from summary):')
    if not module_risks:
        print('- none highlighted in summary')
    else:
        for r in module_risks:
            print(f'- {r}')
    from eurika.api import get_patch_plan
    patch_plan = get_patch_plan(path, window=getattr(args, 'window', 5))
    if patch_plan and patch_plan.get('operations'):
        module_ops = [o for o in patch_plan['operations'] if o.get('target_file') == target]
        if module_ops:
            print()
            print('Planned operations (from patch-plan):')
            for i, op in enumerate(module_ops[:5], start=1):
                kind = op.get('kind', '?')
                raw = op.get('description', '')
                max_len = 200
                if len(raw) <= max_len:
                    desc = raw
                else:
                    truncated = raw[:max_len]
                    cut = truncated.rfind(' ')
                    desc = (truncated[:cut] if cut >= 0 else truncated) + '...'
                print(f'- [{kind}] {desc}')
        else:
            print()
            print('Planned operations: none targeting this module')
    return 0

def handle_doctor(args: Any) -> int:
    """Diagnostics only: report + architect (no patches). Saves to eurika_doctor_report.json."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from cli.orchestrator import run_cycle
    from eurika.smells.rules import summary_to_text
    data = run_cycle(path, mode='doctor', window=getattr(args, 'window', 5), no_llm=getattr(args, 'no_llm', False))
    if data.get('error'):
        _err(data['error'])
        return 1
    summary = data['summary']
    history = data['history']
    patch_plan = data['patch_plan']
    architect_text = data['architect_text']
    print(summary_to_text(summary))
    print()
    print(history.get('evolution_report', ''))
    print()
    print(architect_text)
    report = {'summary': summary, 'history': history, 'architect': architect_text, 'patch_plan': patch_plan}
    try:
        report_path = path / 'eurika_doctor_report.json'
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'\neurika: eurika_doctor_report.json written to {report_path}', file=sys.stderr)
    except Exception:
        pass
    return 0

def handle_fix(args: Any) -> int:
    """Full cycle: scan → plan → patch-apply --apply --verify."""
    from types import SimpleNamespace
    from cli.agent_handlers import handle_agent_cycle
    fix_args = SimpleNamespace(
        path=args.path, window=getattr(args, 'window', 5), dry_run=getattr(args, 'dry_run', False),
        quiet=getattr(args, 'quiet', False), no_clean_imports=getattr(args, 'no_clean_imports', False),
        interval=getattr(args, 'interval', 0),
    )
    return handle_agent_cycle(fix_args)

def handle_cycle(args: Any) -> int:
    """Full ritual: scan → doctor (report + architect) → fix. Single command."""
    from cli.agent_handlers import _run_cycle_with_mode
    return _run_cycle_with_mode(args, mode='full')

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
    """Print heuristic refactoring plan from summary and optional build_recommendations."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_summary, get_history
    from eurika.reasoning.refactor_plan import suggest_refactor_plan
    summary = get_summary(path)
    if summary.get('error'):
        _err(summary.get('error', 'unknown'))
        return 1
    window = getattr(args, 'window', 5)
    history = get_history(path, window=window)
    recommendations = None
    self_map_path = path / 'self_map.json'
    if self_map_path.exists():
        try:
            from eurika.analysis.self_map import build_graph_from_self_map
            from eurika.smells.detector import detect_architecture_smells
            from eurika.smells.advisor import build_recommendations
            graph = build_graph_from_self_map(self_map_path)
            smells = detect_architecture_smells(graph)
            recommendations = build_recommendations(graph, smells)
        except Exception:
            pass
    plan = suggest_refactor_plan(summary, recommendations=recommendations, history_info=history)
    print(plan)
    return 0

def handle_clean_imports(args: Any) -> int:
    """Remove unused imports from Python files (Killer-feature: dead code)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    apply_changes = getattr(args, 'apply', False)
    from code_awareness import CodeAwareness
    from eurika.refactor.remove_unused_import import remove_unused_imports
    aw = CodeAwareness(root=path)
    files = aw.scan_python_files()
    files = [f for f in files if f.name != '__init__.py' and (not f.name.endswith('_api.py'))]
    modified: list[str] = []
    for fpath in files:
        new_content = remove_unused_imports(fpath)
        if new_content is None:
            continue
        if apply_changes:
            try:
                fpath.write_text(new_content, encoding='utf-8')
                rel = fpath.relative_to(path) if path in fpath.parents else fpath.name
                modified.append(str(rel))
            except OSError as e:
                print(f'eurika: failed to write {fpath}: {e}', file=sys.stderr)
        else:
            rel = fpath.relative_to(path) if path in fpath.parents else fpath.name
            modified.append(str(rel))
    if not modified:
        print('eurika: no unused imports found.', file=sys.stderr)
        return 0
    if apply_changes:
        print(f'eurika: removed unused imports from {len(modified)} file(s).', file=sys.stderr)
        for m in modified[:10]:
            print(f'  {m}', file=sys.stderr)
        if len(modified) > 10:
            print(f'  ... and {len(modified) - 10} more', file=sys.stderr)
    else:
        print(f'eurika: would remove unused imports from {len(modified)} file(s) (use --apply to write):', file=sys.stderr)
        for m in modified[:10]:
            print(f'  {m}', file=sys.stderr)
        if len(modified) > 10:
            print(f'  ... and {len(modified) - 10} more', file=sys.stderr)
    print(json.dumps({'modified': modified}, indent=2, ensure_ascii=False))
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
                    interval=0,
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