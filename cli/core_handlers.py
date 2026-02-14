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

from eurika.smells.detector import get_remediation_hint, severity_to_level
from architecture_pipeline import print_arch_diff, print_arch_history, print_arch_summary
from eurika.core.pipeline import run_full_analysis
from runtime_scan import run_scan


def _err(msg: str) -> None:
    """Print unified error message to stderr."""
    print(f"eurika: {msg}", file=sys.stderr)


def handle_help(parser: Any) -> int:
    """Print high-level command overview and detailed argparse help."""
    print("Eurika — architecture analysis and refactoring assistant (v1.2.1)")
    print()
    print("Product commands (recommended):")
    print("  scan [path]       full scan + report + history update")
    print("  doctor [path]     diagnostics: report + architect, no patches")
    print("  fix [path]        full cycle: scan → plan → patch → verify")
    print("  clean-imports [path]  remove unused imports (--apply to write)")
    print()
    print("Other commands:")
    print("  explain <module> [path]   role and risks of a module")
    print("  report [path]            summary + evolution (no rescan)")
    print("  architect [path]         architect's interpretation (--no-llm for template only)")
    print("  suggest-plan [path]      heuristic refactoring plan")
    print("  arch-summary, arch-history, arch-diff, self-check, serve")
    print("  history [path]           alias for arch-history")
    print()
    print("Advanced (eurika agent <cmd>):")
    print("  patch-plan, patch-apply, patch-rollback, cycle, arch-review, ...")
    print()
    print("  --json with report/history/arch-summary/arch-diff for machine output.")
    print("  --help after any command for details.")
    print()
    parser.print_help()
    return 0


def handle_scan(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    fmt = getattr(args, "format", "text")
    color = getattr(args, "color", None)
    return run_scan(path, format=fmt, color=color)


def handle_self_check(args: Any) -> int:
    """Run full scan on the project (self-analysis ritual: Eurika analyzes itself)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    print("eurika: self-check — analyzing project architecture...", file=sys.stderr)
    fmt = getattr(args, "format", "text")
    color = getattr(args, "color", None)
    return run_scan(path, format=fmt, color=color)


def _check_path(path: Path, must_be_dir: bool = True) -> int:
    """Return 0 if path is valid, 1 and print error otherwise."""
    if not path.exists():
        _err(f"path does not exist: {path}")
        return 1
    if must_be_dir and not path.is_dir():
        _err(f"not a directory: {path}")
        return 1
    return 0


def handle_arch_summary(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    if getattr(args, "json", False):
        from eurika.api import get_summary
        data = get_summary(path)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    return print_arch_summary(path)


def handle_arch_history(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    window = getattr(args, "window", 5)
    if getattr(args, "json", False):
        from eurika.api import get_history
        data = get_history(path, window=window)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    return print_arch_history(path, window=window)


def handle_arch_diff(args: Any) -> int:
    old = args.old.resolve()
    new = args.new.resolve()
    if not old.exists():
        _err(f"old self_map not found: {old}")
        return 1
    if not new.exists():
        _err(f"new self_map not found: {new}")
        return 1
    if getattr(args, "json", False):
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
    window = getattr(args, "window", 5)
    if getattr(args, "json", False):
        from eurika.api import get_summary, get_history
        data = {"summary": get_summary(path), "history": get_history(path, window=window)}
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    code1 = print_arch_summary(path)
    code2 = print_arch_history(path, window=window)
    return 0 if code1 == 0 and code2 == 0 else 1


def handle_explain(args: Any) -> int:
    """Explain role and risks of a given module."""
    module_arg = getattr(args, "module", None)
    if not module_arg:
        _err("module path or name is required")
        return 1

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1

    # Read existing artifacts only; do not rescan.
    try:
        snapshot = run_full_analysis(path, update_artifacts=False)
    except Exception as exc:  # pragma: no cover - defensive
        _err(f"failed to build snapshot: {exc}")
        return 1

    graph = snapshot.graph
    smells = snapshot.smells
    summary = snapshot.summary or {}

    # Normalize module name: allow bare name or relative path.
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
        # Fallback: match by suffix (e.g. "architecture_diff.py" or "cli/handlers.py").
        candidates = [n for n in nodes if n.endswith("/" + mod) or n.endswith(mod)]
        if len(candidates) == 1:
            target = candidates[0]
        elif len(candidates) > 1:
            _err(f"ambiguous module '{module_arg}'; candidates: {', '.join(candidates)}")
            return 1

    if not target:
        _err(
            f"module '{module_arg}' not in graph (run 'eurika scan .' to refresh self_map.json)"
        )
        return 1

    fan = graph.fan_in_out()
    fi, fo = fan.get(target, (0, 0))

    central = {c["name"] for c in (summary.get("central_modules") or [])}
    is_central = target in central

    module_smells = [s for s in smells if target in s.nodes]
    risks = summary.get("risks") or []
    module_risks = [r for r in risks if target in r]

    print(f"MODULE EXPLANATION: {target}")
    print()
    print("Role:")
    print(f"- fan-in : {fi}")
    print(f"- fan-out: {fo}")
    print(f"- central: {'yes' if is_central else 'no'}")
    print()

    print("Smells:")
    if not module_smells:
        print("- none detected for this module")
    else:
        for s in module_smells:
            level = severity_to_level(s.severity)
            print(
                f"- [{s.type}] ({level}) severity={s.severity:.2f} — {s.description}"
            )
            print(f"  → {get_remediation_hint(s.type)}")
    print()

    print("Risks (from summary):")
    if not module_risks:
        print("- none highlighted in summary")
    else:
        for r in module_risks:
            print(f"- {r}")

    return 0


def handle_doctor(args: Any) -> int:
    """Diagnostics only: report + architect (no patches)."""
    if _check_path(args.path.resolve()) != 0:
        return 1
    code1 = handle_report(args)
    code2 = handle_architect(args)
    return 0 if (code1 == 0 and code2 == 0) else 1


def handle_fix(args: Any) -> int:
    """Full cycle: scan → plan → patch-apply --apply --verify."""
    from types import SimpleNamespace
    from cli.agent_handlers import handle_agent_cycle
    fix_args = SimpleNamespace(
        path=args.path,
        window=getattr(args, "window", 5),
        dry_run=getattr(args, "dry_run", False),
        quiet=getattr(args, "quiet", False),
    )
    return handle_agent_cycle(fix_args)


def handle_architect(args: Any) -> int:
    """Print architect's interpretation (template or optional LLM)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_summary, get_history
    from eurika.reasoning.architect import interpret_architecture

    summary = get_summary(path)
    if summary.get("error"):
        _err(summary.get("error", "unknown"))
        return 1
    window = getattr(args, "window", 5)
    history = get_history(path, window=window)
    use_llm = not getattr(args, "no_llm", False)
    text = interpret_architecture(summary, history, use_llm=use_llm)
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
    if summary.get("error"):
        _err(summary.get("error", "unknown"))
        return 1
    window = getattr(args, "window", 5)
    history = get_history(path, window=window)
    recommendations = None
    self_map_path = path / "self_map.json"
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
    apply_changes = getattr(args, "apply", False)

    from code_awareness import CodeAwareness
    from eurika.refactor.remove_unused_import import remove_unused_imports

    aw = CodeAwareness(root=path)
    files = aw.scan_python_files()
    # Skip __init__.py and *_api.py: imports there are re-exports (facades)
    files = [
        f for f in files
        if f.name != "__init__.py" and not f.name.endswith("_api.py")
    ]
    modified: list[str] = []

    for fpath in files:
        new_content = remove_unused_imports(fpath)
        if new_content is None:
            continue
        if apply_changes:
            try:
                fpath.write_text(new_content, encoding="utf-8")
                rel = fpath.relative_to(path) if path in fpath.parents else fpath.name
                modified.append(str(rel))
            except OSError as e:
                print(f"eurika: failed to write {fpath}: {e}", file=sys.stderr)
        else:
            rel = fpath.relative_to(path) if path in fpath.parents else fpath.name
            modified.append(str(rel))

    if not modified:
        print("eurika: no unused imports found.", file=sys.stderr)
        return 0

    if apply_changes:
        print(f"eurika: removed unused imports from {len(modified)} file(s).", file=sys.stderr)
        for m in modified[:10]:
            print(f"  {m}", file=sys.stderr)
        if len(modified) > 10:
            print(f"  ... and {len(modified) - 10} more", file=sys.stderr)
    else:
        print(f"eurika: would remove unused imports from {len(modified)} file(s) (use --apply to write):", file=sys.stderr)
        for m in modified[:10]:
            print(f"  {m}", file=sys.stderr)
        if len(modified) > 10:
            print(f"  ... and {len(modified) - 10} more", file=sys.stderr)
    print(json.dumps({"modified": modified}, indent=2, ensure_ascii=False))
    return 0


def handle_serve(args: Any) -> int:
    """Run JSON API HTTP server for future UI."""
    from eurika.api.serve import run_server

    run_server(host=args.host, port=args.port, project_root=args.path)
    return 0  # unreachable when serve_forever() is used


