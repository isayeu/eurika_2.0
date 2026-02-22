"""AgentCore-related CLI handlers.

Extracted from cli.handlers to reduce its size and fan-out.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any
from action_plan import ActionPlan
from agent_core import InputEvent
from agent_core_arch_review import ArchReviewAgentCore
from eurika.storage import ProjectMemory
from executor_sandbox import ExecutorSandbox
from patch_engine import apply_and_verify, apply_patch, apply_patch_dry_run, list_backups, rollback

def handle_agent_arch_review(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_review', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1

def handle_agent_arch_evolution(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_evolution_query', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1

def handle_agent_prioritize_modules(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_review', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1
    proposals = result.output.get('proposals', [])
    prioritized = next((p for p in proposals if p.get('action') == 'prioritize_modules'), None)
    if not prioritized:
        print('No prioritize_modules proposal available in AgentCore response.', file=sys.stderr)
        return 1
    modules = prioritized.get('arguments', {}).get('modules', [])
    print(json.dumps({'modules': modules}, indent=2, ensure_ascii=False))
    return 0

def handle_agent_feedback_summary(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    memory = ProjectMemory(path)
    stats = memory.feedback.aggregate_by_action()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0

def handle_agent_action_dry_run(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_action_dry_run', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1

def handle_agent_action_simulate(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_action_simulate', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    print(json.dumps(result.output, indent=2, ensure_ascii=False))
    return 0 if result.success else 1

def handle_agent_action_apply(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_action_dry_run', payload={'path': str(path), 'window': getattr(args, 'window', 5)}, source='cli')
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1
    proposals = result.output.get('proposals', [])
    action_plan_proposal = next((p for p in proposals if p.get('action') == 'suggest_action_plan'), None)
    if not action_plan_proposal:
        print('No suggest_action_plan in response.', file=sys.stderr)
        return 1
    plan_dict = action_plan_proposal.get('arguments', {}).get('action_plan', {})
    if not plan_dict.get('actions'):
        print('Action plan has no actions.', file=sys.stderr)
        return 0
    plan = ActionPlan.from_dict(plan_dict)
    backup = not getattr(args, 'no_backup', False)
    report = ExecutorSandbox(project_root=path).execute(plan, backup=backup)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report.get('errors') else 1

def handle_agent_patch_plan(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_review', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1
    proposals = result.output.get('proposals', [])
    patch_proposal = next((p for p in proposals if p.get('action') == 'suggest_patch_plan'), None)
    if not patch_proposal:
        print('No suggest_patch_plan proposal in AgentCore response.', file=sys.stderr)
        return 1
    patch_plan = patch_proposal.get('arguments', {}).get('patch_plan', {})
    out_path = getattr(args, 'output', None)
    if out_path is not None:
        out_path = Path(out_path).resolve()
        out_path.write_text(json.dumps(patch_plan, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Patch plan written to {out_path}', file=sys.stderr)
    else:
        print(json.dumps({'patch_plan': patch_plan}, indent=2, ensure_ascii=False))
    return 0

def handle_agent_patch_apply(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_review', payload={'path': str(path), 'window': args.window}, source='cli')
    result = agent.handle(event)
    if not result.success:
        print(json.dumps(result.output, indent=2, ensure_ascii=False))
        return 1
    proposals = result.output.get('proposals', [])
    patch_proposal = next((p for p in proposals if p.get('action') == 'suggest_patch_plan'), None)
    if not patch_proposal:
        print('No suggest_patch_plan proposal in AgentCore response.', file=sys.stderr)
        return 1
    patch_plan = patch_proposal.get('arguments', {}).get('patch_plan', {})
    dry_run = not getattr(args, 'apply', False)
    backup = not getattr(args, 'no_backup', False)
    if dry_run:
        report = apply_patch_dry_run(path, patch_plan, backup=backup)
    elif getattr(args, 'verify', False):
        report = apply_and_verify(path, patch_plan, backup=backup, verify=True)
        try:
            memory = ProjectMemory(path)
            summary = result.output.get('summary', {}) if result.success else {}
            risks = list(summary.get('risks', []))
            modules = list(report.get('modified', []))
            operations = list(patch_plan.get('operations', []))
            verify_success = report['verify']['success']
            if modules:
                memory.learning.append(project_root=path, modules=modules, operations=operations, risks=risks, verify_success=verify_success)
            memory.events.append_event(type='patch', input={'operations_count': len(operations)}, output={'modified': report.get('modified', []), 'run_id': report.get('run_id'), 'verify_success': verify_success}, result=verify_success)
        except Exception:
            pass
    else:
        report = apply_patch(path, patch_plan, backup=backup)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get('errors'):
        return 1
    if report.get('verify') and (not report['verify'].get('success')):
        return 1
    return 0

def _print_fix_summary(operations: list, modified: list, verify_success: bool | None, dry_run: bool=False) -> None:
    """Print human-readable fix summary (Killer UX)."""
    kind_counts: dict[str, int] = {}
    for op in operations:
        k = op.get('kind') or 'refactor_module'
        kind_counts[k] = kind_counts.get(k, 0) + 1
    parts = [f'{n} {k}' for k, n in sorted(kind_counts.items())]
    ops_str = ', '.join(parts) if parts else '0'
    print('--- Eurika fix complete ---', file=sys.stderr)
    if dry_run:
        print(f'Would apply: {ops_str}', file=sys.stderr)
        targets = [op.get('target_file', '?') for op in operations if op.get('target_file')]
        if targets:
            print(f"Targets: {', '.join(targets[:5])}{('...' if len(targets) > 5 else '')}", file=sys.stderr)
    else:
        print(f"Modified: {len(modified)} file(s) — {', '.join(modified[:5])}{('...' if len(modified) > 5 else '')}", file=sys.stderr)
        print(f'Operations: {ops_str}', file=sys.stderr)
        if kind_counts.get('remove_cyclic_import', 0) > 0:
            print(f"  → Broke {kind_counts['remove_cyclic_import']} cyclic dependency(ies)", file=sys.stderr)
        status = '✓ passed' if verify_success else '✗ failed'
        print(f'Verify: {status}', file=sys.stderr)
    print(file=sys.stderr)


def _decision_summary_from_report(report: dict[str, Any]) -> dict[str, int]:
    """Extract decision-gate counters for concise CLI output."""
    ds = report.get("decision_summary")
    if isinstance(ds, dict):
        return {
            "blocked_by_policy": int(ds.get("blocked_by_policy") or 0),
            "blocked_by_critic": int(ds.get("blocked_by_critic") or 0),
            "blocked_by_human": int(ds.get("blocked_by_human") or 0),
        }
    # Fallback for partial/legacy payloads.
    policy_blocked = sum(
        1
        for d in (report.get("policy_decisions") or [])
        if isinstance(d, dict) and str(d.get("decision") or "").lower() == "deny"
    )
    critic_blocked = sum(
        1
        for d in (report.get("critic_decisions") or [])
        if isinstance(d, dict) and str(d.get("verdict") or "").lower() == "deny"
    )
    human_blocked = 0
    for r in (report.get("skipped_reasons") or {}).values():
        if str(r) == "rejected_in_hybrid":
            human_blocked += 1
    return {
        "blocked_by_policy": int(policy_blocked),
        "blocked_by_critic": int(critic_blocked),
        "blocked_by_human": int(human_blocked),
    }


def _print_decision_summary(report: dict[str, Any], *, quiet: bool) -> None:
    """Print concise decision summary for operator UX."""
    if quiet:
        return
    summary = _decision_summary_from_report(report)
    if not any(summary.values()):
        return
    print(
        (
            "Decision summary: "
            f"blocked by policy={summary['blocked_by_policy']}, "
            f"critic={summary['blocked_by_critic']}, "
            f"human={summary['blocked_by_human']}"
        ),
        file=sys.stderr,
    )

def _print_verify_failure_help(
    report: dict[str, Any],
    *,
    dry_run: bool,
    verify_success: bool,
) -> None:
    """Print user-facing help when verify failed and changes were not rolled back automatically."""
    if report.get("verify", {}).get("success") or dry_run or verify_success:
        return
    stderr = (report.get("verify") or {}).get("stderr") or ""
    rollback_info = report.get("rollback") or {}
    vm = report.get("verify_metrics") or {}
    print(file=sys.stderr)
    if rollback_info.get("reason") == "metrics_worsened":
        print(
            f"Metrics worsened (health {vm.get('before_score')} → {vm.get('after_score')}); changes rolled back.",
            file=sys.stderr,
        )
    elif rollback_info.get("done"):
        print("Tests failed; changes rolled back automatically.", file=sys.stderr)
    else:
        run_id = report.get("run_id")
        print("Tests failed. To restore files from backup:", file=sys.stderr)
        if run_id:
            print(f"  eurika agent patch-rollback --run-id {run_id} .", file=sys.stderr)
        else:
            print("  eurika agent patch-rollback .", file=sys.stderr)
    if "No module named pytest" in stderr or "pytest: command not found" in stderr:
        print("To run verification after fix, install pytest: pip install pytest", file=sys.stderr)


def _run_cycle_with_mode(args: Any, mode: str='fix') -> int:
    """Run cycle with given mode (fix or full) and print output."""
    import time
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    from cli.orchestrator import run_cycle
    quiet = getattr(args, 'quiet', False)
    interval = int(getattr(args, 'interval', 0) or 0)
    run_count = 0
    last_code = 0
    try:
        while True:
            run_count += 1
            if interval > 0 and run_count > 1 and not quiet:
                print(f'\neurika: run #{run_count} (interval={interval}s)', file=sys.stderr)
            out = run_cycle(path, mode=mode, runtime_mode=getattr(args, 'runtime_mode', 'assist'), non_interactive=getattr(args, 'non_interactive', False), session_id=getattr(args, 'session_id', None), window=getattr(args, 'window', 5), dry_run=getattr(args, 'dry_run', False), quiet=quiet, no_llm=getattr(args, 'no_llm', False), no_clean_imports=getattr(args, 'no_clean_imports', False), no_code_smells=getattr(args, 'no_code_smells', False), verify_cmd=getattr(args, 'verify_cmd', None), verify_timeout=getattr(args, 'verify_timeout', None), allow_campaign_retry=getattr(args, 'allow_campaign_retry', False), online=getattr(args, 'online', False), team_mode=getattr(args, 'team_mode', False), apply_approved=getattr(args, 'apply_approved', False))
            return_code = out['return_code']
            report = out['report']
            operations = out['operations']
            modified = out['modified']
            verify_success = out['verify_success']
            dry_run = out.get('dry_run', False)
            if not quiet and (operations or dry_run):
                _print_fix_summary(operations, modified=modified, verify_success=verify_success, dry_run=dry_run)
                _print_decision_summary(report, quiet=quiet)
            if dry_run:
                print(json.dumps({'patch_plan': report.get('patch_plan', {})}, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            _print_verify_failure_help(
                report, dry_run=dry_run, verify_success=verify_success
            )
            last_code = return_code
            if interval <= 0:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        if interval > 0 and not quiet:
            print('\neurika: interrupted (Ctrl+C)', file=sys.stderr)
    return last_code

def handle_agent_cycle(args: Any) -> int:
    """Run full cycle via orchestrator: scan → diagnose → plan → patch → verify."""
    return _run_cycle_with_mode(args, mode='fix')

def handle_agent_patch_rollback(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    if getattr(args, 'list', False):
        info = list_backups(path)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    run_id = getattr(args, 'run_id', None)
    report = rollback(path, run_id=run_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get('errors'):
        return 1
    return 0

def handle_agent_learning_summary(args: Any) -> int:
    path = args.path.resolve()
    if not path.exists():
        print(f'Error: path does not exist: {path}', file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f'Error: path is not a directory: {path}', file=sys.stderr)
        return 1
    memory = ProjectMemory(path)
    by_action = memory.learning.aggregate_by_action_kind()
    by_smell_action = memory.learning.aggregate_by_smell_action()
    out = {'by_action_kind': by_action, 'by_smell_action': by_smell_action}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0
