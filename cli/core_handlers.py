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


_WHITELIST_DRAFT_ALLOWED_KINDS = frozenset(
    {
        "remove_unused_import",
        "remove_cyclic_import",
        "fix_import",
        "create_module_stub",
        "split_module",
        "extract_class",
        "extract_block_to_helper",
        "extract_nested_function",
        "refactor_module",
        "refactor_code_smell",
        "introduce_facade",
    }
)


def _err(msg: str) -> None:
    """Print unified error message to stderr."""
    print(f'eurika: {msg}', file=sys.stderr)


def _clog():
    from cli.orchestration.logging import get_logger
    return get_logger("core_handlers")

def handle_help(parser: Any) -> int:
    """Print high-level command overview and detailed argparse help (ROADMAP этап 5: 4 product modes)."""
    print('Eurika — architecture analysis and refactoring assistant (v3.0.18)')
    print()
    print('Product (4 modes):')
    print('  scan [path]              full scan, update artifacts, report')
    print('  doctor [path]           diagnostics: report + architect (no patches)')
    print('  fix [path]              full cycle: scan → plan → patch → verify')
    print('  explain <module> [path] role and risks of a module')
    print()
    print('Other: report, report-snapshot, learning-kpi, campaign-undo, architect, suggest-plan, arch-summary, arch-history, history, arch-diff, self-check, clean-imports, serve')
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
    # Layer discipline (R1, Architecture.md §0)
    lf_report = _format_layer_discipline_block(path)
    if lf_report:
        print(lf_report, file=sys.stderr)
    # File size limits (ROADMAP 3.1-arch.3)
    fs_report = _format_file_size_block(path)
    if fs_report:
        print(fs_report, file=sys.stderr)
    # R5 Self-guard: aggregated health gate
    from eurika.checks.self_guard import collect_self_guard, format_self_guard_block, self_guard_pass

    guard_result = collect_self_guard(path)
    print(format_self_guard_block(guard_result), file=sys.stderr)
    if getattr(args, 'strict', False) and not self_guard_pass(guard_result):
        return 1
    return code


def _format_layer_discipline_block(path: Path) -> str:
    """Return layer discipline report for self-check (R1, Architecture.md §0.6)."""
    from eurika.checks.dependency_firewall import (
        collect_dependency_violations,
        collect_layer_violations,
    )

    root = path
    forbidden = collect_dependency_violations(root)
    layer_viol = collect_layer_violations(root)
    if not forbidden and not layer_viol:
        return "\nLAYER DISCIPLINE: OK (0 forbidden, 0 layer violations)\n"
    lines = ["", "LAYER DISCIPLINE (R1, Architecture.md §0.6)", ""]
    if forbidden:
        lines.append("Forbidden imports:")
        for v in forbidden[:10]:
            lines.append(f"  - {v.path} -> {v.forbidden_module}")
        if len(forbidden) > 10:
            lines.append(f"  ... +{len(forbidden) - 10} more")
        lines.append("")
    if layer_viol:
        lines.append("Layer violations (upward):")
        for v in layer_viol[:10]:
            lines.append(f"  - {v.path} -> {v.imported_module} (L{v.source_layer}->L{v.target_layer})")
        if len(layer_viol) > 10:
            lines.append(f"  ... +{len(layer_viol) - 10} more")
    return "\n".join(lines)


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


def handle_learning_kpi(args: Any) -> int:
    """KPI verify_success_rate by smell|action|target + recommendations (ROADMAP KPI focus)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_learning_insights

    top_n = int(getattr(args, "top_n", 5) or 5)
    insights = get_learning_insights(path, top_n=top_n)
    if getattr(args, "json", False):
        print(json.dumps(insights, indent=2, ensure_ascii=False))
        return 0
    by_smell_action = insights.get("by_smell_action") or {}
    recs = insights.get("recommendations") or {}
    whitelist = recs.get("whitelist_candidates") or []
    deny = recs.get("policy_deny_candidates") or []
    lines = ["## KPI verify_success_rate (ROADMAP)", ""]
    if by_smell_action:
        lines.append("### by_smell_action")
        lines.append("")
        for key, s in sorted(by_smell_action.items(), key=lambda x: -float(x[1].get("verify_success", 0) / max(x[1].get("total", 1), 1))):
            total = int(s.get("total", 0) or 0)
            vs = int(s.get("verify_success", 0) or 0)
            vf = int(s.get("verify_fail", 0) or 0)
            rate = round(100 * vs / total, 1) if total else 0
            lines.append(f"- **{key}** total={total}, verify_success={vs}, verify_fail={vf}, rate={rate}%")
        lines.append("")
    if whitelist:
        lines.append("### Promote (whitelist candidates)")
        lines.append("")
        for r in whitelist[:top_n]:
            tf = r.get("target_file", "?")
            pair = f"{r.get('smell_type', '?')}|{r.get('action_kind', '?')}"
            rate = float(r.get("verify_success_rate", 0) or 0) * 100
            lines.append(f"- {pair} @ {tf} (rate={rate:.1f}%)")
        lines.append("")
    if deny:
        lines.append("### Deprioritize (policy deny candidates)")
        lines.append("")
        for r in deny[:top_n]:
            tf = r.get("target_file", "?")
            pair = f"{r.get('smell_type', '?')}|{r.get('action_kind', '?')}"
            rate = float(r.get("verify_success_rate", 0) or 0) * 100
            lines.append(f"- {pair} @ {tf} (rate={rate:.1f}%)")
        lines.append("")
    lines.append("### Next steps (D)")
    lines.append("")
    rui = next((s for k, s in by_smell_action.items() if "remove_unused_import" in k), None)
    if rui and int(rui.get("total", 0) or 0) >= 5:
        rate = 100 * int(rui.get("verify_success", 0) or 0) / max(int(rui.get("total", 1) or 1), 1)
        lines.append(f"- remove_unused_import rate={rate:.1f}%: try `eurika fix . --no-code-smells --allow-low-risk-campaign`")
    lines.append("- To promote: run fix, accumulate 2+ verify_success per target, then `eurika whitelist-draft .`")
    lines.append("- Use `--apply-suggested-policy` when doctor suggests EURIKA_CAMPAIGN_ALLOW_LOW_RISK")
    lines.append("")
    print("\n".join(lines) if lines else "No learning data yet. Run eurika fix to accumulate.")
    return 0


def handle_whitelist_draft(args: Any) -> int:
    """Generate operation whitelist draft from campaign success candidates."""
    from collections import Counter
    from eurika.storage import SessionMemory

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1

    output_path = getattr(args, "output", None)
    if output_path is None:
        output_path = path / ".eurika" / "operation_whitelist.draft.json"
    elif not output_path.is_absolute():
        output_path = path / output_path

    min_success = int(getattr(args, "min_success", 2) or 2)
    allow_auto = bool(getattr(args, "allow_auto", False))
    all_kinds = bool(getattr(args, "all_kinds", False))
    raw_kinds = str(getattr(args, "kinds", "extract_block_to_helper") or "")
    kind_filter = {
        part.strip()
        for part in raw_kinds.split(",")
        if part.strip()
    }
    unknown_kinds = sorted(k for k in kind_filter if k not in _WHITELIST_DRAFT_ALLOWED_KINDS)
    if unknown_kinds:
        _err(
            "unknown --kinds values: "
            + ", ".join(unknown_kinds)
            + f". Allowed: {', '.join(sorted(_WHITELIST_DRAFT_ALLOWED_KINDS))}"
        )
        return 1

    mem = SessionMemory(path)
    raw = mem._load()
    campaign = raw.get("campaign") or {}
    success_keys = [str(k) for k in (campaign.get("verify_success_keys") or [])]
    fail_keys = [str(k) for k in (campaign.get("verify_fail_keys") or [])]
    success_counts = Counter(success_keys)
    fail_counts = Counter(fail_keys)

    candidates = sorted(mem.campaign_whitelist_candidates(min_success=min_success))
    operations: list[dict[str, Any]] = []
    for key in candidates:
        parts = key.split("|", 2)
        if len(parts) != 3:
            continue
        target_file, kind, location = parts
        if not target_file or not kind:
            continue
        if not all_kinds and kind_filter and kind not in kind_filter:
            continue
        item: dict[str, Any] = {
            "kind": kind,
            "target_file": target_file,
            "allow_in_hybrid": True,
            "allow_in_auto": allow_auto,
            "evidence": {
                "verify_success_count": int(success_counts.get(key, 0)),
                "verify_fail_count": int(fail_counts.get(key, 0)),
                "source": "campaign_memory",
            },
        }
        if location:
            item["location"] = location
        operations.append(item)

    payload = {
        "meta": {
            "generated_by": "eurika whitelist-draft",
            "min_success": min_success,
            "allow_auto": allow_auto,
            "all_kinds": all_kinds,
            "kinds": sorted(kind_filter) if kind_filter else [],
            "candidates_count": len(operations),
        },
        "operations": operations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"written": str(output_path), "operations": len(operations)}, ensure_ascii=False))
    return 0


def handle_campaign_undo(args: Any) -> int:
    """Undo campaign checkpoint (ROADMAP 3.6.4)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.storage.campaign_checkpoint import list_campaign_checkpoints, undo_campaign_checkpoint

    if getattr(args, "list", False):
        info = list_campaign_checkpoints(path)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    out = undo_campaign_checkpoint(path, checkpoint_id=getattr(args, "checkpoint_id", None))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if out.get("errors") else 0


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
            _clog().info(f"\n--- Project {i + 1}/{len(paths)}: {path} ---\n")
        if _check_path(path) != 0:
            exit_code = 1
            continue
        no_llm = getattr(args, 'no_llm', False)
        _clog().info('eurika: doctor — step 1/4: loading summary, history, architect...')
        if not no_llm:
            _clog().info('eurika: doctor — step 2/4: architect will use LLM (Ollama/OpenAI) — may take 30s–3min')
        use_rich = False
        try:
            from rich.console import Console
            _rich_console = Console(file=sys.stderr)
            use_rich = sys.stderr.isatty()
        except ImportError:
            pass
        quiet_doc = getattr(args, 'quiet', False)
        if use_rich and not no_llm:
            with _rich_console.status('[bold green]Loading architect...', spinner='dots'):
                data = run_cycle(path, mode='doctor', runtime_mode=getattr(args, 'runtime_mode', 'assist'), window=getattr(args, 'window', 5), no_llm=no_llm, online=getattr(args, 'online', False), quiet=quiet_doc)
        else:
            data = run_cycle(path, mode='doctor', runtime_mode=getattr(args, 'runtime_mode', 'assist'), window=getattr(args, 'window', 5), no_llm=no_llm, online=getattr(args, 'online', False), quiet=quiet_doc)
        if data.get('error'):
            _err(data['error'])
            exit_code = 1
            continue
        _clog().info('eurika: doctor — step 4/4: rendering report')
        summary = data['summary']
        history = data['history']
        patch_plan = data['patch_plan']
        architect_text = data['architect_text']
        suggested_policy = data.get('suggested_policy') or {}
        context_sources = data.get('context_sources') or {}
        campaign_checkpoint = data.get('campaign_checkpoint') or {}
        print(summary_to_text(summary))
        print()
        print(history.get('evolution_report', ''))
        print()
        print(architect_text)
        if context_sources:
            vfail = len(context_sources.get('recent_verify_fail_targets') or [])
            crej = len(context_sources.get('campaign_rejected_targets') or [])
            recent = len(context_sources.get('recent_patch_modified') or [])
            targets = len(context_sources.get('by_target') or {})
            print()
            print('Context sources (ROADMAP 3.6.3):')
            print(f'  targets={targets}, recent_verify_fail={vfail}, campaign_rejected={crej}, recent_patch_modified={recent}')
        ops_metrics = data.get('operational_metrics') or {}
        if ops_metrics:
            ar = ops_metrics.get('apply_rate', 'N/A')
            rr = ops_metrics.get('rollback_rate', 'N/A')
            med = ops_metrics.get('median_verify_time_ms')
            med_str = f'{med} ms' if med is not None else 'N/A'
            print()
            print('Operational metrics (last 10 fix runs):')
            print(f'  apply_rate={ar}, rollback_rate={rr}, median_verify_time={med_str}')
        if campaign_checkpoint:
            cp_id = campaign_checkpoint.get('checkpoint_id', 'N/A')
            cp_status = campaign_checkpoint.get('status', 'unknown')
            cp_runs = len(campaign_checkpoint.get('run_ids') or [])
            print()
            print('Campaign checkpoint (ROADMAP 3.6.4):')
            print(f'  checkpoint_id={cp_id}, status={cp_status}, run_ids={cp_runs}')
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
        if context_sources:
            report['context_sources'] = context_sources
        if suggested_policy:
            report['suggested_policy'] = suggested_policy
        if data.get('operational_metrics'):
            report['operational_metrics'] = data['operational_metrics']
        if campaign_checkpoint:
            report['campaign_checkpoint'] = campaign_checkpoint
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
            _clog().info(f'eurika: eurika_doctor_report.json written to {report_path}')
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
            allow_campaign_retry=getattr(args, 'allow_campaign_retry', False),
            allow_low_risk_campaign=getattr(args, 'allow_low_risk_campaign', False),
            online=getattr(args, 'online', False),
            team_mode=getattr(args, 'team_mode', False),
            apply_approved=getattr(args, 'apply_approved', False),
            approve_ops=getattr(args, 'approve_ops', None),
            reject_ops=getattr(args, 'reject_ops', None),
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
            allow_campaign_retry=getattr(args, 'allow_campaign_retry', False),
            allow_low_risk_campaign=getattr(args, 'allow_low_risk_campaign', False),
            online=getattr(args, 'online', False),
            team_mode=getattr(args, 'team_mode', False),
            apply_approved=getattr(args, 'apply_approved', False),
            approve_ops=getattr(args, 'approve_ops', None),
            reject_ops=getattr(args, 'reject_ops', None),
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
    from eurika.knowledge import CompositeKnowledgeProvider, LocalKnowledgeProvider, OfficialDocsProvider, OSSPatternProvider, PEPProvider, ReleaseNotesProvider
    cache_dir = path / '.eurika' / 'knowledge_cache'
    online = getattr(args, 'online', False)
    ttl = float(os.environ.get('EURIKA_KNOWLEDGE_TTL', '86400'))
    rate_limit = float(os.environ.get('EURIKA_KNOWLEDGE_RATE_LIMIT', '1.0' if online else '0'))
    knowledge_provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(path / 'eurika_knowledge.json'),
        OSSPatternProvider(path / '.eurika' / 'pattern_library.json'),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
    ])
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


def handle_learn_github(args: Any) -> int:
    """Clone curated OSS repos, optionally scan, build pattern library (ROADMAP 3.0.5.1, 3.0.5.2, 3.0.5.3)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.learning import load_curated_repos, ensure_repo_cloned, search_repositories
    import os

    search_query = getattr(args, "search", None)
    search_limit = getattr(args, "search_limit", 5)
    if search_query:
        try:
            token = os.environ.get("GITHUB_TOKEN", "")
            repos = search_repositories(search_query, per_page=search_limit, token=token or None)
            if not repos:
                _err("no repositories found for search query")
                return 1
            q_preview = (search_query[:50] + "…") if len(search_query) > 50 else search_query
            print(f"eurika learn-github: search '{q_preview}' -> {len(repos)} repos", file=sys.stderr)
        except RuntimeError as e:
            _err(str(e))
            return 1
    else:
        config_path = getattr(args, "config", None)
        if config_path is None:
            cfg = path / "docs" / "curated_repos.example.json"
            config_path = cfg if cfg.exists() else None
        repos = load_curated_repos(config_path)
    cache_dir = path.resolve().parent / "curated_repos"
    do_scan = getattr(args, "scan", False)
    do_patterns = getattr(args, "build_patterns", False)

    if not repos:
        _err("no curated repos found")
        return 1
    print(f"eurika learn-github: {len(repos)} repos, cache={cache_dir}", file=sys.stderr)
    ok = 0
    for repo in repos:
        name = repo.get("name", "?")
        dest, err = ensure_repo_cloned(repo, cache_dir)
        if dest:
            ok += 1
            print(f"  {name}: {dest}", file=sys.stderr)
            if do_scan:
                from runtime_scan import run_scan
                run_scan(dest)
        else:
            print(f"  {name}: clone failed — {err or 'unknown'}", file=sys.stderr)
    if do_patterns or do_scan:
        from eurika.learning.pattern_library import extract_patterns_from_repos, save_pattern_library
        lib_path = path / ".eurika" / "pattern_library.json"
        data = extract_patterns_from_repos(cache_dir)
        save_pattern_library(data, lib_path)
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        projects = {
            str(project)
            for v in data.values()
            if isinstance(v, list)
            for e in v
            if isinstance(e, dict)
            for project in [e.get("project")]
            if project
        }
        proj_str = ", ".join(sorted(projects)) if projects else "none"
        print(f"eurika learn-github: pattern library written ({total} entries from {len(projects)} repo(s): {proj_str}) -> {lib_path}", file=sys.stderr)
    print(f"eurika learn-github: {ok}/{len(repos)} repos available", file=sys.stderr)
    return 0 if ok > 0 else 1


def handle_serve(args: Any) -> int:
    """Run JSON API HTTP server for future UI."""
    from eurika.api.serve import run_server
    run_server(host=args.host, port=args.port, project_root=args.path)
    return 0


# TODO (eurika): refactor long_function 'handle_doctor' — consider extracting helper
