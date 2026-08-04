"""Chat context, user context and dialog state (P0.4 split from chat.py)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from eurika.utils.json_io import load_json_safe

DEFAULT_SAVE_TARGET = 'app.py'


def load_user_context(root: Path) -> Dict[str, str]:
    """Load user context (name, etc.) from .eurika/chat_history/user_context.json."""
    path = root / '.eurika' / 'chat_history' / 'user_context.json'
    data = load_json_safe(path)
    if data:
        return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
    return {}

def save_user_context(root: Path, data: Dict[str, str]) -> None:
    """Save user context to .eurika/chat_history/user_context.json."""
    path = root / '.eurika' / 'chat_history' / 'user_context.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def load_dialog_state(root: Path) -> Dict[str, Any]:
    """Load lightweight dialog state for clarification/goal continuity."""
    path = root / '.eurika' / 'chat_history' / 'dialog_state.json'
    return load_json_safe(path) or {}

def save_dialog_state(root: Path, state: Dict[str, Any]) -> None:
    """Persist lightweight dialog state (best effort)."""
    path = root / '.eurika' / 'chat_history' / 'dialog_state.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass

def store_last_execution(state: Dict[str, Any], report: Dict[str, Any]) -> None:
    """Store compact last execution block in dialog state."""
    state['last_execution'] = {'ok': bool(report.get('ok')), 'summary': str(report.get('summary') or ''), 'verification_ok': bool((report.get('verification') or {}).get('ok')), 'artifacts_changed': list(report.get('artifacts_changed') or [])}


def format_dialog_goal_block(state: Optional[Dict[str, Any]]) -> str:
    """Human-readable active goal / pending / last run for chat and LLM context."""
    if not isinstance(state, dict) or not state:
        return "Нет активной цели в контексте агента."
    lines: List[str] = []
    goal = state.get("active_goal")
    if isinstance(goal, dict) and goal:
        intent = goal.get("intent") or "-"
        target = str(goal.get("target") or "").strip()
        source = goal.get("source") or "-"
        risk = goal.get("risk_level") or ""
        conf = goal.get("confidence")
        head = f"intent={intent}"
        if target:
            head += f", target={target}"
        head += f", source={source}"
        if conf is not None:
            head += f", confidence={conf}"
        if risk:
            head += f", risk={risk}"
        lines.append(f"Активная цель: {head}")
        steps = goal.get("plan_steps") or goal.get("steps") or []
        if isinstance(steps, list) and steps:
            for step in steps[:4]:
                lines.append(f"  - {step}")
    pending = state.get("pending_clarification")
    if isinstance(pending, dict) and pending:
        original = str(pending.get("original") or "").strip()
        lines.append(
            "Ожидает уточнения: "
            + (original[:180] if original else "(без текста)")
        )
    pending_plan = state.get("pending_plan")
    if isinstance(pending_plan, dict) and pending_plan:
        lines.append(
            "Pending plan: "
            f"intent={pending_plan.get('intent') or '-'}, "
            f"token={pending_plan.get('token') or '-'}, "
            f"risk={pending_plan.get('risk_level') or '-'}"
        )
    pending_git = state.get("pending_git_commit")
    if isinstance(pending_git, dict) and pending_git.get("message"):
        msg = str(pending_git.get("message") or "")[:80]
        lines.append(f"Pending git commit: {msg}")
    last = state.get("last_execution")
    if isinstance(last, dict) and last:
        lines.append(
            "Last execution: "
            f"ok={last.get('ok')}, verification_ok={last.get('verification_ok')}, "
            f"summary={last.get('summary') or '-'}"
        )
    if not lines:
        return "Нет активной цели в контексте агента."
    goal_present = isinstance(goal, dict) and bool(goal)
    if not goal_present:
        lines.insert(0, "Нет активной цели в контексте агента.")
    return "\n".join(lines)


def clear_dialog_goals(state: Dict[str, Any]) -> Dict[str, Any]:
    """Clear active goal and pending clarification (HITL pending_plan untouched)."""
    state["active_goal"] = {}
    state["pending_clarification"] = {}
    return state


def _extracted_block_97(node, nid, details):
    fi = node.get('fan_in', 0)
    fo = node.get('fan_out', 0)
    details.append(f'{nid} (fan-in={fi}, fan-out={fo})')

def build_chat_context(root: Path, scope: Optional[Dict[str, Any]]=None) -> str:
    """Build context snippet from summary + recent_events + user context for chat prompt.

    ROADMAP 3.6.5, R5 2.3: when scope has modules/smells from @-mentions, enrich context
    with scoped module details and filtered risks.
    """
    from eurika.api import get_graph, get_recent_events, get_summary
    lines: List[str] = []
    if scope:
        scope_parts: List[str] = []
        if scope.get('modules'):
            scope_parts.append(f"Focus module(s): {', '.join(scope['modules'])}")
        if scope.get('smells'):
            scope_parts.append(f"Focus smell(s): {', '.join(scope['smells'])}")
        if scope_parts:
            lines.append('[Scope: ' + '; '.join(scope_parts) + ']. Prioritize answers regarding the focused scope when relevant.')
        if scope.get('modules'):
            try:
                graph_data = get_graph(root)
                if graph_data and (not graph_data.get('error')):
                    nodes = graph_data.get('nodes') or []
                    scope_mods = scope['modules']
                    details: List[str] = []
                    for node in nodes:
                        nid = node.get('id', '')
                        if any((m in nid or nid.endswith(m) for m in scope_mods)):
                            _extracted_block_97(node, nid, details)
                    if details:
                        lines.append('Scoped module details: ' + '; '.join(details[:5]))
            except Exception:
                pass
    try:
        uc = load_user_context(root)
        if uc:
            parts = [f'{k}={v}' for k, v in uc.items()]
            lines.append(f"[User: {'; '.join(parts)}]")
    except Exception:
        pass
    try:
        state = load_dialog_state(root)
        if isinstance(state, dict):
            goal_block = format_dialog_goal_block(state)
            if goal_block and not goal_block.startswith("Нет активной цели"):
                # Compact one-liner for LLM prompt (keep chat answers multi-line via handler).
                compact = " | ".join(
                    ln.strip() for ln in goal_block.splitlines() if ln.strip()
                )[:500]
                lines.append(f"[Agent context: {compact}]")
    except Exception:
        pass
    try:
        summary = get_summary(root)
        if summary and (not summary.get('error')):
            sys_info = summary.get('system') or {}
            modules = sys_info.get('modules', '?')
            deps = sys_info.get('dependencies', '?')
            cycles = sys_info.get('cycles', '?')
            lines.append(f'Project: {modules} modules, {deps} deps, {cycles} cycles.')
            risks = summary.get('risks') or []
            if risks:
                scope_modules = set(scope.get('modules') or []) if scope else set()
                scope_smells = set(((s or '').lower() for s in scope.get('smells') or [])) if scope else set()
                filtered = risks
                if scope_modules:
                    filtered = [r for r in filtered if any((m in str(r) for m in scope_modules))]
                if scope_smells:
                    filtered = [r for r in filtered if any((s in str(r).lower() for s in scope_smells))]
                risks_to_show = filtered[:5] if filtered else risks[:3] if not (scope_modules or scope_smells) else filtered[:5]
                if risks_to_show:
                    lines.append(f"Risks: {'; '.join((str(r) for r in risks_to_show))}.")
    except Exception:
        pass
    try:
        state = load_dialog_state(root)
        if isinstance(state, dict) and (not state.get('last_release_check_ok')) and state.get('last_release_check_output'):
            rc_out = str(state.get('last_release_check_output', ''))[:2000]
            if rc_out:
                lines.append(f'[Last release check FAILED — исправь эти ошибки]: {rc_out}...')
    except Exception:
        pass
    try:
        events = get_recent_events(root, limit=3, types=('patch', 'learn'))
        if events:
            event_parts: List[str] = []
            for e in events[:3]:
                if e.type == 'patch':
                    out = getattr(e, 'output', None) or {}
                    if isinstance(out, dict):
                        modified = out.get('modified', [])
                        event_parts.append(f'patch: {len(modified)} files')
                elif e.type == 'learn':
                    event_parts.append('learn')
            if event_parts:
                lines.append('Recent: ' + '; '.join(event_parts))
    except Exception:
        pass
    return ' '.join(lines) if lines else 'No project context (run eurika scan .)'