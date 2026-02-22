"""CYCLE_REPORT-style markdown formatting (ROADMAP 3.1-arch.5).

Presentation layer: formats doctor/fix artifacts for pasting into CYCLE_REPORT.md.
CLI handlers delegate here to stay thin.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

def _try_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load JSON file returning (data, error_message)."""
    try:
        return (json.loads(path.read_text(encoding='utf-8')), None)
    except json.JSONDecodeError:
        return (None, f'invalid JSON in {path.name}')
    except OSError:
        return (None, f'cannot read {path.name}')


def _fmt_delta(current: float | None, baseline: float | None) -> str:
    """Format percentage-point delta for snapshot readability."""
    if current is None or baseline is None:
        return 'N/A'
    return f'{(current - baseline) * 100:+.1f}pp'


def _aggregate_recent_no_op_apply(path: Path, window: int = 10) -> dict[str, Any] | None:
    """Best-effort baseline from recent patch events for no_op/apply rates."""
    try:
        from eurika.storage import ProjectMemory

        memory = ProjectMemory(path)
        events = memory.events.recent_events(limit=window, types=("patch",))
    except Exception:
        return None
    if not events:
        return None

    total_ops = 0
    total_modified = 0
    total_skipped = 0
    for e in events:
        inp = getattr(e, 'input', None) or {}
        out = getattr(e, 'output', None) or {}
        ops = int(inp.get('operations_count', 0) or 0)
        modified = out.get('modified') or []
        skipped = out.get('skipped') or []
        total_ops += ops
        if isinstance(modified, list):
            total_modified += len(modified)
        if isinstance(skipped, list):
            total_skipped += len(skipped)

    if total_ops <= 0:
        return None
    return {
        'runs_count': len(events),
        'apply_rate': round(total_modified / total_ops, 4),
        'no_op_rate': round(total_skipped / total_ops, 4),
    }

def format_report_snapshot(path: Path) -> str:
    """
    Produce CYCLE_REPORT-style markdown from eurika_doctor_report.json and eurika_fix_report.json.

    Returns formatted string. Empty or missing artifacts yield a fallback message.
    """
    lines: list[str] = []
    fix_path = path / 'eurika_fix_report.json'
    doctor_path = path / 'eurika_doctor_report.json'
    load_errors: list[str] = []
    fix_telemetry: dict[str, Any] = {}
    fix_context_sources: dict[str, Any] = {}
    doctor_ops: dict[str, Any] = {}

    if fix_path.exists():
        fix, fix_err = _try_load_json(fix_path)
        if fix_err:
            load_errors.append(fix_err)
        if fix:
            v = fix.get('verify', {}) or {}
            mod = fix.get('modified', [])
            sk = fix.get('skipped', [])
            lines.append('## 1. Fix (`eurika fix .`)')
            lines.append('')
            lines.append('| Поле | Значение |')
            lines.append('|------|----------|')
            lines.append(f'| **modified** | {len(mod)} |')
            lines.append(f'| **skipped** | {len(sk)} |')
            lines.append(f"| **verify** | {v.get('success', 'N/A')} |")
            if fix.get('skipped_reasons'):
                lines.append('')
                lines.append('### Skipped — причины')
                for f, r in list(fix.get('skipped_reasons', {}).items())[:10]:
                    lines.append(f'- {f}: {r}')
            vm = fix.get('verify_metrics') or {}
            if vm:
                lines.append('')
                lines.append(f"### verify_metrics: before={vm.get('before_score')}, after={vm.get('after_score')}")
            telemetry = fix.get('telemetry') or {}
            if isinstance(telemetry, dict):
                fix_telemetry = telemetry
            if telemetry:
                lines.append('')
                lines.append('### telemetry (ROADMAP 2.7.8)')
                lines.append(f"apply_rate={telemetry.get('apply_rate')}, no_op_rate={telemetry.get('no_op_rate')}, rollback_rate={telemetry.get('rollback_rate')}, verify_duration_ms={telemetry.get('verify_duration_ms')}, median_verify_time_ms={telemetry.get('median_verify_time_ms', 'N/A')}")
            ctx = fix.get('context_sources') or {}
            if isinstance(ctx, dict):
                fix_context_sources = ctx
            lines.append('')
    if doctor_path.exists():
        doc, doc_err = _try_load_json(doctor_path)
        if doc_err:
            load_errors.append(doc_err)
        if doc:
            summary = doc.get('summary', {}) or {}
            sys = summary.get('system', {}) or {}
            modules = sys.get('modules', 'N/A')
            deps = sys.get('dependencies', 'N/A')
            risk_score = 'N/A'
            history = doc.get('history', {}) or {}
            points = history.get('points', [])
            if points:
                risk_score = points[-1].get('risk_score', 'N/A')
            lines.append('## 2. Doctor (`eurika_doctor_report.json`)')
            lines.append('')
            lines.append('| Метрика | Значение |')
            lines.append('|---------|----------|')
            lines.append(f'| **Модули** | {modules} |')
            lines.append(f'| **Зависимости** | {deps} |')
            lines.append(f'| **Risk score** | {risk_score}/100 |')
            ops = doc.get('operational_metrics') or {}
            if isinstance(ops, dict):
                doctor_ops = ops
            if ops:
                ar = ops.get('apply_rate', 'N/A')
                rr = ops.get('rollback_rate', 'N/A')
                med = ops.get('median_verify_time_ms')
                med_str = f'{med} ms' if med is not None else 'N/A'
                lines.append(f"| **apply_rate** (last {ops.get('runs_count', 10)} runs) | {ar} |")
                lines.append(f'| **rollback_rate** | {rr} |')
                lines.append(f'| **median_verify_time** | {med_str} |')
            lines.append('')
    if fix_context_sources and fix_telemetry:
        recent_baseline = _aggregate_recent_no_op_apply(path, window=10) or {}
        apply_now = fix_telemetry.get('apply_rate') if isinstance(fix_telemetry.get('apply_rate'), (int, float)) else None
        no_op_now = fix_telemetry.get('no_op_rate') if isinstance(fix_telemetry.get('no_op_rate'), (int, float)) else None
        apply_base = doctor_ops.get('apply_rate') if isinstance(doctor_ops.get('apply_rate'), (int, float)) else None
        no_op_base = recent_baseline.get('no_op_rate') if isinstance(recent_baseline.get('no_op_rate'), (int, float)) else None

        by_target = fix_context_sources.get('by_target') or {}
        lines.append('## 2.1 Context effect (ROADMAP 3.6.3)')
        lines.append('')
        lines.append(f"- context_targets={len(by_target) if isinstance(by_target, dict) else 0}, recent_verify_fail_targets={len(fix_context_sources.get('recent_verify_fail_targets') or [])}, campaign_rejected_targets={len(fix_context_sources.get('campaign_rejected_targets') or [])}")
        lines.append(f"- apply_rate: current={apply_now if apply_now is not None else 'N/A'}, baseline={apply_base if apply_base is not None else 'N/A'} (Δ {_fmt_delta(apply_now, apply_base)})")
        lines.append(f"- no_op_rate: current={no_op_now if no_op_now is not None else 'N/A'}, baseline={no_op_base if no_op_base is not None else 'N/A'} (Δ {_fmt_delta(no_op_now, no_op_base)})")
        runs_used = recent_baseline.get('runs_count') if isinstance(recent_baseline.get('runs_count'), int) else 0
        if runs_used:
            lines.append(f'- baseline_no_op_source=recent patch events ({runs_used} runs)')
        lines.append('')
    by_action: dict[str, Any] = {}
    by_smell: dict[str, Any] = {}
    try:
        from eurika.storage import ProjectMemory
        mem = ProjectMemory(path)
        by_action = mem.learning.aggregate_by_action_kind()
        by_smell = mem.learning.aggregate_by_smell_action()
    except Exception:
        pass
    if by_action or by_smell:
        lines.append('## 3. Learning')
        lines.append('')
        if by_action:
            lines.append('### by_action_kind')
            for k, v in list(by_action.items())[:8]:
                s, f = (v.get('success', 0), v.get('fail', 0))
                rate = f'{100 * s / (s + f):.0f}%' if s + f else 'N/A'
                lines.append(f'- {k}: {s} success, {f} fail ({rate})')
            lines.append('')
        if by_smell:
            lines.append('### by_smell_action')
            for k, v in list(by_smell.items())[:8]:
                lines.append(f"- {k}: total={v.get('total')}, success={v.get('success')}, fail={v.get('fail')}")
    if not lines:
        lines.append('(No eurika_doctor_report.json or eurika_fix_report.json found. Run doctor/fix first.)')
    if load_errors:
        lines.append('')
        lines.append('### Snapshot warnings')
        for e in load_errors:
            lines.append(f'- {e}')
    return '\n'.join(lines)