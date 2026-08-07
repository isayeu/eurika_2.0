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


def format_goal_reflection(state: Optional[Dict[str, Any]]) -> str:
    """Reflection over active_goal + last_execution (always shows last run if any).

    Unlike ``format_dialog_goal_block``, empty goal still surfaces last_execution —
    answer to «что получилось?» / «итог цели».
    After ``clear_goal``, last_execution is wiped too — no stale итог.
    """
    if not isinstance(state, dict) or not state:
        return (
            "Пока нет итога: ни активной цели, ни last_execution. "
            "Сначала scan / ритуал / Apply, или спроси «что дальше по развитию?»."
        )
    goal = state.get("active_goal")
    last = state.get("last_execution")
    goal_present = isinstance(goal, dict) and bool(goal)
    last_present = isinstance(last, dict) and bool(last)
    if not goal_present and not last_present:
        return (
            "Пока нет итога: цель и last_execution сброшены. "
            "Сделай scan / ритуал / Apply или спроси «что дальше по развитию?»."
        )
    lines: List[str] = []
    if goal_present:
        intent = goal.get("intent") or "-"
        target = str(goal.get("target") or "").strip()
        head = f"Цель: intent={intent}"
        if target:
            head += f", target={target}"
        source = goal.get("source")
        if source:
            head += f", source={source}"
        lines.append(head)
    else:
        lines.append("Активной цели нет.")
    if last_present:
        ok = last.get("ok")
        ver = last.get("verification_ok")
        summary = str(last.get("summary") or "-").strip() or "-"
        lines.append(f"Итог: ok={ok}, verification_ok={ver}, summary={summary}")
        changed = last.get("artifacts_changed") or []
        if isinstance(changed, list) and changed:
            preview = ", ".join(str(x) for x in changed[:5])
            more = f" (+{len(changed) - 5})" if len(changed) > 5 else ""
            lines.append(f"Артефакты: {preview}{more}")
    else:
        lines.append("Last execution ещё не записан.")
    if goal_present:
        lines.append('Дальше: «сбрось цель» или «какая цель?» / новая задача.')
    else:
        lines.append('Дальше: новая задача или «что дальше по развитию?»')
    return "\n".join(lines)


def format_goal_nudge(state: Optional[Dict[str, Any]]) -> str:
    """One-line post-run nudge when there is an active goal (empty if none)."""
    if not isinstance(state, dict):
        return ""
    goal = state.get("active_goal")
    if not isinstance(goal, dict) or not goal:
        return ""
    intent = str(goal.get("intent") or "-").strip() or "-"
    last = state.get("last_execution") if isinstance(state.get("last_execution"), dict) else {}
    ok = last.get("ok") if isinstance(last, dict) else None
    ok_bit = f" ok={ok}" if ok is not None else ""
    return (
        f"Цель `{intent}`{ok_bit}; скажи «что получилось?» или «сбрось цель»."
    )


def append_goal_nudge(text: str, state: Optional[Dict[str, Any]]) -> str:
    """Append reflection nudge under a handler reply when useful."""
    nudge = format_goal_nudge(state)
    if not nudge:
        return text
    base = (text or "").rstrip()
    if not base:
        return nudge
    return f"{base}\n\n_{nudge}_"


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
    goal_present = isinstance(goal, dict) and bool(goal)
    has_open_work = bool(
        goal_present
        or (isinstance(pending, dict) and pending)
        or (isinstance(pending_plan, dict) and pending_plan)
        or (isinstance(pending_git, dict) and pending_git.get("message"))
    )
    # Last execution is history — only attach when there is an open goal/pending,
    # otherwise «какая цель?» looks like a stuck ritual/run.
    last = state.get("last_execution")
    if has_open_work and isinstance(last, dict) and last:
        lines.append(
            "Last execution: "
            f"ok={last.get('ok')}, verification_ok={last.get('verification_ok')}, "
            f"summary={last.get('summary') or '-'}"
        )
    if not lines:
        return "Нет активной цели в контексте агента."
    if not goal_present:
        lines.insert(0, "Нет активной цели в контексте агента.")
    return "\n".join(lines)


def clear_dialog_goals(state: Dict[str, Any]) -> Dict[str, Any]:
    """Clear active goal, pending clarification, and last_execution.

    HITL pending_plan / pending_git_commit untouched. Wiping last_execution avoids
    stale «что получилось?» after explicit reset.
    """
    state["active_goal"] = {}
    state["pending_clarification"] = {}
    state["last_execution"] = {}
    return state


def release_active_goal_keep_execution(state: Dict[str, Any]) -> Dict[str, Any]:
    """Drop sticky active_goal after a finished run; keep last_execution for reflection."""
    state["active_goal"] = {}
    return state


def format_agent_context_panel(
    state: Optional[Dict[str, Any]],
    *,
    plan_valid: bool = False,
    plan_stale: bool = False,
) -> str:
    """Text for Qt Agent «Контекст» panel (goal / pending / итог).

    Shows last_execution even without active_goal (post-run release). Empty state
    hints chat phrases for reflection / roadmap.
    """
    if not isinstance(state, dict):
        state = {}
    lines: List[str] = []
    goal = state.get("active_goal")
    goal_present = isinstance(goal, dict) and bool(goal)
    if goal_present:
        lines.append("Цель:")
        intent = goal.get("intent", "-")
        target = str(goal.get("target") or "").strip()
        source = goal.get("source", "-")
        if target:
            lines.append(f"- intent={intent}, target={target}, source={source}")
        else:
            lines.append(f"- intent={intent}, source={source}")
        conf = goal.get("confidence")
        if conf is not None:
            lines.append(f"- confidence={conf}")
        risk = goal.get("risk_level")
        if risk:
            lines.append(f"- risk={risk}")
        plan_steps = goal.get("plan_steps") or goal.get("steps") or []
        if isinstance(plan_steps, list) and plan_steps:
            lines.append("- plan:")
            for step in plan_steps[:5]:
                lines.append(f"  - {step}")
    else:
        lines.append("Цель: нет (отпущена или не задана)")

    pending = state.get("pending_clarification")
    if isinstance(pending, dict) and pending:
        original = str(pending.get("original") or "").strip()
        lines.append("")
        lines.append("Ожидает уточнения:")
        lines.append(f"- {(original[:180] if original else '(без текста)')}")

    pending_plan = state.get("pending_plan")
    if not isinstance(pending_plan, dict):
        pending_plan = {}
    if plan_valid and pending_plan:
        lines.append("")
        lines.append("Pending plan (нужен Apply после Diff):")
        pending_target = str(pending_plan.get("target") or "").strip()
        if pending_target:
            lines.append(
                f"- intent={pending_plan.get('intent', '-')}, target={pending_target}, "
                f"risk={pending_plan.get('risk_level', '-')}, token={pending_plan.get('token', '-')}"
            )
        else:
            lines.append(
                f"- intent={pending_plan.get('intent', '-')}, "
                f"risk={pending_plan.get('risk_level', '-')}, "
                f"token={pending_plan.get('token', '-')}"
            )
        steps = pending_plan.get("steps") or []
        if isinstance(steps, list) and steps:
            for step in steps[:4]:
                lines.append(f"  - {step}")
        lines.append("- Diff: авто-preview ниже; Apply — после просмотра Diff")
    elif plan_stale and pending_plan:
        lines.append("")
        lines.append("Expired pending plan (Reject to clear):")
        lines.append(
            f"- intent={pending_plan.get('intent', '-')}, "
            f"target={pending_plan.get('target', '-')}"
        )

    last = state.get("last_execution")
    if isinstance(last, dict) and last:
        lines.append("")
        lines.append("Итог (last_execution):")
        lines.append(
            f"- ok={last.get('ok')}, verification_ok={last.get('verification_ok')}, "
            f"summary={last.get('summary') or '-'}"
        )
        changed = last.get("artifacts_changed") or []
        if isinstance(changed, list) and changed:
            lines.append(f"- changed={', '.join(str(x) for x in changed[:6])}")
        if not goal_present:
            lines.append("- chat: «что получилось?» / «сбрось цель»")

    pending_git = state.get("pending_git_commit")
    if isinstance(pending_git, dict) and pending_git.get("message"):
        lines.append("")
        lines.append("Pending git commit:")
        lines.append(f"- message: {pending_git.get('message', '-')}")

    has_substance = goal_present or (
        isinstance(pending, dict) and bool(pending)
    ) or plan_valid or plan_stale or (
        isinstance(last, dict) and bool(last)
    ) or (
        isinstance(pending_git, dict) and bool(pending_git.get("message"))
    )
    if not has_substance:
        return (
            "Нет активной цели и итога.\n"
            "Chat: «просканируй проект», «что получилось?», "
            "«что дальше по развитию?», «сбрось цель»."
        )
    return "\n".join(lines)


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