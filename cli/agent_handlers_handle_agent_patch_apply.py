"""Extracted from parent module to reduce complexity."""
import json
import sys
from typing import Any
from agent_core import InputEvent
from agent_core_arch_review import ArchReviewAgentCore
from eurika.storage import ProjectMemory
from patch_engine import apply_and_verify, apply_patch, apply_patch_dry_run

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