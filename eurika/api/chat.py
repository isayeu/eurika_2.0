"""Chat endpoint for UI (ROADMAP 3.5.11.A, 3.5.11.B, 3.5.11.C). P0.4: split into chat_*, chat_direct."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from eurika.api.task_executor import build_task_spec, execute_spec, has_capability, is_pending_plan_valid, make_pending_plan

from .chat_context import (
    build_chat_context as _build_chat_context,
    load_dialog_state as _load_dialog_state,
    load_user_context as _load_user_context,
    save_dialog_state as _save_dialog_state,
    save_user_context as _save_user_context,
    store_last_execution as _store_last_execution,
)
from .chat_direct import (
    apply_add_empty_tab_after_chat as _apply_add_empty_tab_after_chat,
    extract_commit_message_from_request as _extract_commit_message_from_request,
    extract_confirmation_token as _extract_confirmation_token,
    is_apply_confirmation as _is_apply_confirmation,
    is_reject_confirmation as _is_reject_confirmation,
    resolve_direct_handler as _resolve_direct_handler,
    run_eurika_fix as _run_eurika_fix,
)
from .chat_prompt import (
    build_chat_prompt as _build_chat_prompt,
    fetch_knowledge_for_chat as _fetch_knowledge_for_chat,
    intent_hints_for_prompt as _intent_hints_for_prompt,
    knowledge_topics_for_chat as _knowledge_topics_for_chat,
    load_chat_feedback_for_prompt as _load_chat_feedback_for_prompt,
    load_eurika_rules_for_chat as _load_eurika_rules_for_chat,
)
from .chat_handlers import run_direct_handlers as _run_direct_handlers
from .chat_utils import (
    brief_release_check_analysis as _brief_release_check_analysis,
    enforce_eurika_persona as _enforce_eurika_persona,
    format_doctor_report_for_chat as _format_doctor_report_for_chat,
    format_execution_report as _format_execution_report,
    format_project_tree as _format_project_tree,
    format_root_ls as _format_root_ls,
    grounded_ui_tabs_text as _grounded_ui_tabs_text,
    infer_default_save_target as _infer_default_save_target,
    read_file_for_chat as _read_file_for_chat,
    safe_create_empty_file as _safe_create_empty_file,
    safe_delete_file as _safe_delete_file,
    safe_write_file as _safe_write_file,
    syntax_lang_for_path as _syntax_lang_for_path,
)

DEFAULT_SAVE_TARGET = "app.py"


def append_chat_history(project_root: Path, role: str, content: str, context_snapshot: Optional[str]=None) -> None:
    """Append one message to .eurika/chat_history/chat.jsonl (ROADMAP 3.5.11.A.3)."""
    root = Path(project_root).resolve()
    chat_dir = root / '.eurika' / 'chat_history'
    chat_dir.mkdir(parents=True, exist_ok=True)
    log_path = chat_dir / 'chat.jsonl'
    record = {'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'role': role, 'content': content[:10000], 'context_snapshot': context_snapshot[:500] if context_snapshot else None}
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

def _append_chat_history_safe(project_root: Path, role: str, content: str, context_snapshot: Optional[str]=None) -> None:
    """Best-effort history append: never break chat flow on write errors."""
    try:
        append_chat_history(project_root, role, content, context_snapshot)
    except Exception:
        pass


def save_chat_feedback(
    project_root: Path,
    user_message: str,
    assistant_message: str,
    helpful: bool,
    clarification: Optional[str] = None,
) -> None:
    """Append feedback to .eurika/chat_feedback.json (ROADMAP 3.6.8 Phase 3)."""
    root = Path(project_root).resolve()
    path = root / '.eurika' / 'chat_feedback.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entries: List[Dict[str, Any]] = []
        if path.exists():
            raw = path.read_text(encoding='utf-8')
            data = json.loads(raw) if raw.strip() else {}
            entries = list(data.get('entries') or [])
        entry = {
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'user_message': (user_message or '')[:2000],
            'assistant_message': (assistant_message or '')[:2000],
            'helpful': helpful,
            'clarification': (clarification or '').strip()[:500] or None,
        }
        entries.append(entry)
        path.write_text(json.dumps({'entries': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def chat_send(
    project_root: Path,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    on_system_action: Optional[Callable[[str], None]] = None,
    run_command_with_result: Optional[Callable[[str], tuple[str, int]]] = None,
) -> Dict[str, Any]:
    """
    Send user message through Eurika layer to LLM; return response.

    ROADMAP 3.5.11.A: enriches prompt with project context.
    ROADMAP 3.5.11.B: RAG from past exchanges.
    ROADMAP 3.5.11.C: intent refactor -> run eurika fix; intent save -> extract code, write file.
    on_system_action: optional callback for actions (e.g. for Terminal tab: rm, touch, eurika fix).
    """
    root = Path(project_root).resolve()

    def _emit(cmd: str) -> None:
        if on_system_action:
            try:
                on_system_action(cmd)
            except Exception:
                pass
    msg = (message or '').strip()
    if not msg:
        return {'text': '', 'error': 'message is empty'}
    state = _load_dialog_state(root)
    handler_id, emit_cmd = _resolve_direct_handler(root, msg)
    skip_emit = handler_id == "release_check" and run_command_with_result is not None
    if emit_cmd and "{" not in str(emit_cmd) and not skip_emit:
        _emit(emit_cmd)
    direct_result = _run_direct_handlers(
        handler_id, root, msg, state, emit_cmd, _emit, _append_chat_history_safe, run_command_with_result
    )
    if direct_result is not None:
        return direct_result
    if _is_reject_confirmation(msg):
        pending_plan = state.get('pending_plan') if isinstance(state, dict) else {}
        if isinstance(pending_plan, dict) and is_pending_plan_valid(pending_plan):
            state['pending_plan'] = {}
            _save_dialog_state(root, state)
            text = 'Отклонил pending-план. Ничего не применял.'
        else:
            text = 'Нет активного pending-плана для отклонения.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    intent, target = (None, None)
    interpretation = None
    effective_msg = msg
    pending = state.get('pending_clarification') if isinstance(state, dict) else None
    if isinstance(pending, dict):
        original = str(pending.get('original') or '').strip()
        if original and msg.lower() not in {'отмена', 'cancel', 'стоп'}:
            effective_msg = f'{original}\nУточнение: {msg}'
    try:
        from eurika.api.chat_intent import interpret_task
        interpretation = interpret_task(effective_msg, history=history)
        intent = interpretation.intent
        target = interpretation.target
    except Exception:
        pass
    if _is_apply_confirmation(msg):
        pending_git = state.get('pending_git_commit') if isinstance(state, dict) else None
        if isinstance(pending_git, dict) and pending_git.get('message'):
            from eurika.api.chat_tools import git_commit as _git_commit_tool
            msg_commit = str(pending_git.get('message') or '').strip()
            state['pending_git_commit'] = {}
            _save_dialog_state(root, state)
            ok, out = _git_commit_tool(root, msg_commit)
            text = f"Коммит выполнен: {out}" if ok else f"Ошибка: {out}"
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None if ok else out}
        pending_plan = state.get('pending_plan') if isinstance(state, dict) else {}
        if isinstance(pending_plan, dict) and is_pending_plan_valid(pending_plan):
            user_token = _extract_confirmation_token(msg)
            plan_token = str(pending_plan.get('token') or '')
            if user_token and user_token != plan_token:
                text = 'Не могу выполнить: token подтверждения не совпадает.'
                _append_chat_history_safe(root, 'user', msg, None)
                _append_chat_history_safe(root, 'assistant', text, None)
                return {'text': text, 'error': None}
            spec = build_task_spec(intent=str(pending_plan.get('intent') or ''), target=str(pending_plan.get('target') or ''), message=msg, plan_steps=list(pending_plan.get('steps') or []), entities=dict(pending_plan.get('entities') or {}))
        else:
            if isinstance(state, dict) and isinstance(pending_plan, dict) and pending_plan:
                state['pending_plan'] = {}
                _save_dialog_state(root, state)
            text = (
                'Не могу выполнить: нет активного плана на подтверждение. '
                'Сначала сформулируй задачу, затем подтвердить: `применяй`.'
            )
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        if spec is not None:
            si, st = str(spec.intent or ''), str(spec.target or '')
            if si == 'delete' and st:
                _emit(f"$ rm {st}")
            elif si == 'create' and st:
                _emit(f"$ touch {st}")
            report_obj = execute_spec(root, spec)
            report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
            state['pending_plan'] = {}
            state['active_goal'] = {'intent': spec.intent, 'target': spec.target, 'source': 'executor'}
            _store_last_execution(state, report)
            _save_dialog_state(root, state)
            text = _format_execution_report(report)
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
    if intent == 'ui_tabs':
        report_obj = execute_spec(root, build_task_spec(intent='ui_tabs', message=msg))
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        text = _grounded_ui_tabs_text()
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if interpretation is not None and interpretation.needs_clarification:
        text = interpretation.clarifying_question or 'Уточни, пожалуйста, задачу: что изменить, где именно и какой ожидаемый результат?'
        state['pending_clarification'] = {'original': msg}
        _save_dialog_state(root, state)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if isinstance(state.get('pending_clarification'), dict):
        state.pop('pending_clarification', None)
        _save_dialog_state(root, state)
    if intent:
        state['active_goal'] = {'intent': intent, 'target': target or '', 'source': 'interpreter', 'confidence': float(getattr(interpretation, 'confidence', 0.0) if interpretation else 0.0), 'risk_level': str(getattr(interpretation, 'risk_level', 'medium') if interpretation else 'medium'), 'plan_steps': list(getattr(interpretation, 'plan_steps', []) if interpretation else []), 'entities': dict(getattr(interpretation, 'entities', {}) if interpretation else {})}
        _save_dialog_state(root, state)
    if intent and has_capability(intent) and (intent != 'save'):
        spec = build_task_spec(intent=intent, target=target or '', message=msg, plan_steps=list(getattr(interpretation, 'plan_steps', []) if interpretation else []), entities=dict(getattr(interpretation, 'entities', {}) if interpretation else {}))
        if spec.requires_confirmation:
            pending = make_pending_plan(spec)
            state['pending_plan'] = pending
            _save_dialog_state(root, state)
            steps_text = '; '.join(spec.steps[:4]) if spec.steps else 'n/a'
            task_text = f'Понял задачу: `{intent}`'
            if intent == 'ui_add_empty_tab':
                task_text = 'Понял задачу: добавить пустую вкладку после `Chat` в Qt UI'
            elif intent == 'ui_remove_tab':
                task_text = 'Понял задачу: удалить вкладку `New Tab` из Qt UI'
            text = task_text + (f' (target `{spec.target}`).' if spec.target else '.') + f' Risk: `{spec.risk_level}`. ' + f'Plan: {steps_text}. ' + f"Подтверди выполнение: `применяй token:{pending.get('token')}` (или просто `применяй`)."
            _append_chat_history_safe(root, 'user', msg, None)
            _append_chat_history_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        report_obj = execute_spec(root, spec)
        report = {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}
        _store_last_execution(state, report)
        _save_dialog_state(root, state)
        text = _format_execution_report(report)
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'refactor':
        dry = 'dry-run' in msg.lower() or 'dry run' in msg.lower() or 'без применения' in msg.lower()
        _emit(f"$ eurika fix . {'--dry-run' if dry else ''}".strip())
        output = _run_eurika_fix(root, dry_run=dry)
        text = 'Запустил `eurika fix .`' + (' (dry-run)' if dry else '') + f':\n\n{output}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'delete' and target:
        _emit(f"$ rm {target}")
        ok, res = _safe_delete_file(root, target)
        if ok:
            full = (root / res).resolve()
            text = f'Удалён файл {res} ({full})'
        else:
            text = f'Не удалось удалить: {res}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'create' and target:
        _emit(f"$ touch {target}")
        ok, res = _safe_create_empty_file(root, target)
        if ok:
            full = (root / res).resolve()
            text = f'Создан пустой файл {res} ({full})'
        else:
            text = f'Не удалось создать: {res}'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'recall' and target == 'name':
        uc = _load_user_context(root)
        name = uc.get('name')
        if name:
            text = f'Тебя зовут {name}.'
        else:
            text = 'Я не знаю, как тебя зовут. Скажи «Меня зовут X» или «My name is X», и я запомню.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if intent == 'remember' and target and (':' in target):
        key, _, val = target.partition(':')
        key, val = (key.strip().lower(), val.strip())
        if key and val:
            uc = _load_user_context(root)
            uc[key] = val
            try:
                _save_user_context(root, uc)
            except Exception:
                pass
            if key == 'name':
                text = f'Запомнил: тебя зовут {val}.'
            else:
                text = f'Запомнил: {key}={val}'
        else:
            text = 'Не удалось распознать, что запомнить.'
        _append_chat_history_safe(root, 'user', msg, None)
        _append_chat_history_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    scope = None
    if interpretation is not None and interpretation.entities:
        modules = (interpretation.entities.get('scope_modules') or '').split(',')
        smells = (interpretation.entities.get('scope_smells') or '').split(',')
        if modules or smells:
            scope = {'modules': [m.strip() for m in modules if m.strip()], 'smells': [s.strip() for s in smells if s.strip()]}
    if scope is None:
        try:
            from eurika.api.chat_intent import parse_mentions
            mentions = parse_mentions(msg)
            if mentions.get('modules') or mentions.get('smells'):
                scope = mentions
        except Exception:
            pass
    context = _build_chat_context(root, scope=scope)
    rag_examples = None
    try:
        from eurika.api.chat_rag import retrieve_similar_chats, format_rag_examples
        examples = retrieve_similar_chats(root, msg, top_k=3)
        if examples:
            rag_examples = format_rag_examples(examples)
    except Exception:
        pass
    knowledge_snippet = ""
    try:
        topics = _knowledge_topics_for_chat(intent or "", scope)
        if topics:
            knowledge_snippet = _fetch_knowledge_for_chat(root, topics)
    except Exception:
        pass
    save_target = target if intent == 'save' else None
    if intent == 'save' and not save_target:
        save_target = _infer_default_save_target(msg)
        target = save_target
    feedback_snippet = _load_chat_feedback_for_prompt(root)
    rules_snippet = _load_eurika_rules_for_chat(root)
    intent_hints = _intent_hints_for_prompt(root)
    prompt = _build_chat_prompt(msg, context, history, rag_examples=rag_examples, save_target=save_target, knowledge_snippet=knowledge_snippet or None, feedback_snippet=feedback_snippet or None, rules_snippet=rules_snippet or None, intent_hints=intent_hints)
    from eurika.reasoning.architect import call_llm_with_prompt
    raw_text, err = call_llm_with_prompt(prompt, max_tokens=1024)
    text = raw_text or ""
    if err:
        _append_chat_history_safe(root, 'user', msg, context)
        _append_chat_history_safe(root, 'assistant', f'[Error] {err}', None)
        return {'text': '', 'error': err}
    if intent == 'save' and save_target:
        try:
            from eurika.api.chat_intent import extract_code_block
            code = extract_code_block(text)
            if code:
                _emit(f"# write -> {save_target}")
                ok, res = _safe_write_file(root, save_target, code)
                if ok:
                    full = (root / res).resolve()
                    state['last_saved_file_rel'] = res
                    state['last_saved_file_abs'] = str(full)
                    _save_dialog_state(root, state)
                    text = text.rstrip() + f'\n\n[Сохранено в {res} ({full})]'
        except Exception:
            pass
    text = _enforce_eurika_persona(text or '')
    _append_chat_history_safe(root, 'user', msg, context)
    _append_chat_history_safe(root, 'assistant', text or '', None)
    return {'text': text or '', 'error': None}