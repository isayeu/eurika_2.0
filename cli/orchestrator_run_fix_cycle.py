"""Extracted from parent module to reduce complexity."""

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

def run_fix_cycle(path: Path, *, window: int=5, dry_run: bool=False, quiet: bool=False, skip_scan: bool=False, no_clean_imports: bool=False) -> dict[str, Any]:
    """Run full fix cycle: scan → diagnose → plan → patch → verify. Writes eurika_fix_report.json and appends to memory. Returns dict with return_code, report, operations, modified, verify_success, agent_result."""
    from agent_core import InputEvent
    from agent_core_arch_review import ArchReviewAgentCore
    from patch_apply import BACKUP_DIR
    from patch_engine import apply_and_verify, rollback_patch
    from runtime_scan import run_scan
    from eurika.core.pipeline import build_snapshot_from_self_map
    from eurika.evolution.diff import diff_architecture_snapshots
    from eurika.reasoning.graph_ops import metrics_from_graph
    from eurika.storage import ProjectMemory
    if not skip_scan:
        if not quiet:
            print('--- Step 1/4: scan ---', file=sys.stderr)
            print('eurika fix: scan → diagnose → plan → patch → verify', file=sys.stderr)
        if quiet:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                if run_scan(path) != 0:
                    return {'return_code': 1, 'report': {}, 'operations': [], 'modified': [], 'verify_success': False, 'agent_result': None}
        elif run_scan(path) != 0:
            return {'return_code': 1, 'report': {}, 'operations': [], 'modified': [], 'verify_success': False, 'agent_result': None}
    if not quiet:
        print('--- Step 2/4: diagnose ---', file=sys.stderr)
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(type='arch_review', payload={'path': str(path), 'window': window}, source='cli')
    result = agent.handle(event)
    if not result.success:
        return {'return_code': 1, 'report': result.output, 'operations': [], 'modified': [], 'verify_success': False, 'agent_result': result}
    proposals = result.output.get('proposals', [])
    patch_proposal = next((p for p in proposals if p.get('action') == 'suggest_patch_plan'), None)
    if not patch_proposal:
        return {'return_code': 0, 'report': {'message': 'No suggest_patch_plan proposal. Cycle complete (nothing to apply).'}, 'operations': [], 'modified': [], 'verify_success': True, 'agent_result': result}
    patch_plan = patch_proposal.get('arguments', {}).get('patch_plan', {})
    operations = patch_plan.get('operations', [])
    if not no_clean_imports:
        from eurika.api import get_clean_imports_operations
        clean_ops = get_clean_imports_operations(path)
        if clean_ops:
            operations = clean_ops + operations
            patch_plan = dict(patch_plan, operations=operations)
    if not operations:
        return {'return_code': 0, 'report': {'message': 'Patch plan has no operations. Cycle complete.'}, 'operations': [], 'modified': [], 'verify_success': True, 'agent_result': result}
    if dry_run:
        if not quiet:
            print('--- Step 3/3: plan (dry-run, no apply) ---', file=sys.stderr)
        report = {'dry_run': True, 'patch_plan': patch_plan, 'modified': [], 'verify': {'success': None}}
        try:
            (path / 'eurika_fix_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass
        return {'return_code': 0, 'report': {'dry_run': True, 'patch_plan': patch_plan, 'modified': [], 'verify': {'success': None}}, 'operations': operations, 'modified': [], 'verify_success': None, 'agent_result': result, 'dry_run': True}
    if not quiet:
        print('--- Step 3/4: patch & verify ---', file=sys.stderr)
    self_map_path = path / 'self_map.json'
    rescan_before = path / BACKUP_DIR / 'self_map_before.json'
    if self_map_path.exists():
        (path / BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        rescan_before.write_text(self_map_path.read_text(encoding='utf-8'), encoding='utf-8')
    report = apply_and_verify(path, patch_plan, backup=True, verify=True, auto_rollback=True)
    if report['verify']['success'] and rescan_before.exists():
        if not quiet:
            print('--- Step 4/4: rescan (compare before/after) ---', file=sys.stderr)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            run_scan(path)
        self_map_after = path / 'self_map.json'
        if self_map_after.exists():
            try:
                old_snap = build_snapshot_from_self_map(rescan_before)
                new_snap = build_snapshot_from_self_map(self_map_after)
                diff = diff_architecture_snapshots(old_snap, new_snap)
                report['rescan_diff'] = {'structures': diff['structures'], 'smells': diff['smells'], 'maturity': diff['maturity'], 'centrality_shifts': diff.get('centrality_shifts', [])[:10]}
                trends = {}
                metrics_before = metrics_from_graph(old_snap.graph, old_snap.smells, trends)
                metrics_after = metrics_from_graph(new_snap.graph, new_snap.smells, trends)
                health_before = {'score': metrics_before['score']}
                health_after = {'score': metrics_after['score']}
                before_score = health_before.get('score', 0)
                after_score = health_after.get('score', 0)
                report['verify_metrics'] = {'success': after_score >= before_score, 'before_score': before_score, 'after_score': after_score}
                if after_score < before_score and report.get('run_id'):
                    rb = rollback_patch(path, report['run_id'])
                    report['rollback'] = {'done': True, 'run_id': report['run_id'], 'restored': rb.get('restored', []), 'errors': rb.get('errors', []), 'reason': 'metrics_worsened'}
                    report['verify']['success'] = False
            except Exception as e:
                report['rescan_diff'] = {'error': 'diff failed'}
                report['verify_metrics'] = {'success': None, 'error': str(e)}
    modified = report.get('modified', [])
    verify_success = report['verify']['success']
    try:
        memory = ProjectMemory(path)
        summary = result.output.get('summary', {}) or {}
        risks = list(summary.get('risks', []))
        if modified:
            memory.learning.append(project_root=path, modules=modified, operations=operations, risks=risks, verify_success=verify_success)
        memory.events.append_event(type='patch', input={'operations_count': len(operations)}, output={'modified': report.get('modified', []), 'run_id': report.get('run_id'), 'verify_success': verify_success}, result=verify_success)
    except Exception:
        pass
    try:
        report_path = path / 'eurika_fix_report.json'
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        if not quiet:
            print(f'eurika_fix_report.json written to {report_path}', file=sys.stderr)
    except Exception:
        pass
    return_code = 1 if report.get('errors') or not report['verify'].get('success') else 0
    return {'return_code': return_code, 'report': report, 'operations': operations, 'modified': modified, 'verify_success': verify_success, 'agent_result': result, 'dry_run': False}
