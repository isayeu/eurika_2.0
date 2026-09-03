"""Direct handler execution (P0.4 split from chat.py)."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from eurika.api.task_executor import build_task_spec, execute_spec
from .chat_context import (
    append_goal_nudge,
    clear_dialog_goals,
    format_dialog_goal_block,
    format_goal_reflection,
    enrich_goal_reflection_with_llm,
    load_dialog_state,
    release_active_goal_keep_execution,
    save_dialog_state,
    store_last_execution,
)
from .chat_direct import extract_api_endpoint_from_request, extract_commit_message_from_request, extract_file_path_from_show_request, extract_module_path_from_request, generate_and_append_api_test, generate_module_test, infer_commit_message_via_llm, propose_commit_message_from_status
from .chat_utils import brief_release_check_analysis, format_capabilities_help, format_continue_dev_brief, format_doctor_report_for_chat, format_file_recount, format_project_docs, format_project_overview, format_project_tree, format_roadmap_next_steps, format_root_ls, format_self_check_for_chat, read_file_for_chat, syntax_lang_for_path

def _run_emit_with_result(
    emit_cmd: Optional[str],
    run_command_with_result: Callable[[str], tuple[str, int]],
) -> tuple[Optional[str], str, int]:
    """Run emit shell command via Qt callback; return (terminal_cmd, output, exit_code)."""
    shell_cmd = (emit_cmd or "").strip().lstrip("$ ").strip()
    if not shell_cmd:
        return None, "", -1
    out, code = run_command_with_result(shell_cmd)
    return f"$ {shell_cmd}", (out or ""), int(code)


def _shell_for_chat(
    *,
    shell_cmd: str,
    run_command_with_result: Optional[Callable[[str], tuple[str, int]]],
    fallback: Optional[Callable[[], tuple[bool, str]]] = None,
    emit_cmd: Optional[str] = None,
) -> tuple[Optional[str], str, int, bool]:
    """Prefer Qt Terminal callback; else silent fallback. Returns (term_cmd, out, code, ok)."""
    cmd = (shell_cmd or "").strip()
    if not cmd and emit_cmd:
        cmd = (emit_cmd or "").strip().lstrip("$ ").strip()
    if run_command_with_result is not None and cmd:
        term_cmd, output, code = _run_emit_with_result(emit_cmd or f"$ {cmd}", run_command_with_result)
        return term_cmd, output, code, code == 0
    if fallback is not None:
        ok, output = fallback()
        # Still expose what would have run, so Qt can mirror even without callback.
        return (f"$ {cmd}" if cmd else None), (output or ""), (0 if ok else 1), bool(ok)
    return (f"$ {cmd}" if cmd else None), "", -1, False


def _with_terminal(
    result: Dict[str, Any],
    terminal_cmd: Optional[str],
    output: str,
    exit_code: int,
) -> Dict[str, Any]:
    """Attach terminal mirror fields when a command was (or would be) run."""
    if terminal_cmd:
        result["terminal_cmd"] = terminal_cmd
        result["terminal_output"] = output or ""
        result["terminal_exit_code"] = int(exit_code)
    return result


def _extracted_block_134(emit_cmd, run_command_with_result):
    """Legacy helper: run emit and return terminal_cmd only (result discarded)."""
    terminal_cmd, _out, _code = _run_emit_with_result(emit_cmd, run_command_with_result)
    return terminal_cmd

def terminal_read_source(
    *,
    client_terminal_text: str | None,
    last_execution: dict[str, Any] | None,
) -> str:
    """Qt Terminal tab is the source of truth when the client sent a snapshot.

    Empty snapshot (restart / cleared pane) must not fall back to stale
    ``last_execution.host_log`` from an older tool-loop.
    """
    if client_terminal_text is not None:
        return str(client_terminal_text).strip()
    if isinstance(last_execution, dict):
        return str(last_execution.get("host_log") or "").strip()
    return ""


def terminal_visible_output(text: str) -> str:
    """Drop idle ``$`` prompts so an empty pane is not treated as command output."""
    kept: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped == "$":
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def run_direct_handlers(handler_id: Optional[str], root: Path, msg: str, state: Dict[str, Any], emit_cmd: Optional[str], emit: Callable[[str], None], append_safe: Callable[[Path, str, str, Optional[str]], None], run_command_with_result: Optional[Callable[[str], tuple[str, int]]], privilege_prompt: Optional[Any] = None, *, client_terminal_text: Optional[str] = None, history: Optional[list] = None) -> Optional[Dict[str, Any]]:
    """Execute direct handler; return result dict if handled, else None."""
    if not handler_id:
        return None
    if handler_id == 'host_shell':
        from eurika.api.chat_direct import is_bare_shell_request
        from eurika.api.chat_host_ops import run_host_command_with_privilege

        if not is_bare_shell_request(msg):
            return None
        lines = [
            ln.strip().lstrip("$ ").strip()
            for ln in (msg or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        log_parts: list[str] = []
        worst = 0
        for cmd in lines[:5]:
            emit(f"$ {cmd}")
            result = run_host_command_with_privilege(
                cmd,
                privilege_prompt=privilege_prompt,
                timeout=60.0,
                cwd=str(root),
            )
            display = cmd
            if result.used_sudo and not cmd.lower().startswith("sudo "):
                display = f"sudo {cmd}"
            block = f"$ {display}\n{result.output}"
            if result.privilege_note:
                block += f"\n[{result.privilege_note}]"
            log_parts.append(block)
            if result.exit_code not in (0, 127) and worst == 0:
                worst = int(result.exit_code)
        text = "\n\n".join(log_parts) if log_parts else "(empty)"
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {
            'text': text,
            'error': None,
            'terminal_cmd': f"$ {lines[0]}" if lines else "$ # host shell",
            'terminal_output': "\n\n".join(log_parts),
            'terminal_exit_code': int(worst),
        }
    if handler_id == 'identity':
        text = (
            'Я Eurika — локальный архитектурный coding-ассистент этого проекта. '
            'Создатель: Исаев Андрей Аркадьевич (ProDG). '
            'Могу помочь с анализом, рефакторингом и изменениями кода.'
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'greeting':
        text = (
            'Привет! Я Eurika — архитектурный coding-ассистент этого проекта. '
            'Могу показать структуру, scan, помочь с кодом. '
            'Например: «что за проект?», «сколько файлов?», «покажи дерево», '
            '«какая цель?», «что получилось?», «сбрось цель».'
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'capabilities':
        text = format_capabilities_help()
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'project_overview':
        text = format_project_overview(root)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'file_recount':
        text = format_file_recount(root)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'list_docs':
        text = format_project_docs(root)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'docs_audit':
        from eurika.api.docs_audit import run_docs_audit

        text, meta = run_docs_audit(root, use_llm=True)
        store_last_execution(
            state,
            {
                'ok': bool(meta.get('ok', True)),
                'summary': f"docs_audit via {meta.get('source')}",
            },
        )
        if not (isinstance(state.get('active_goal'), dict) and state.get('active_goal')):
            state['active_goal'] = {
                'intent': 'docs_audit',
                'source': 'chat_direct',
                'target': 'VISION/ROADMAP',
            }
        text = append_goal_nudge(text, state)
        release_active_goal_keep_execution(state)
        save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'roadmap_next':
        text = format_roadmap_next_steps(root)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'continue_dev':
        text = format_continue_dev_brief(root)
        store_last_execution(
            state,
            {
                'ok': True,
                'summary': 'continue_dev: VISION A1 chat UX / goals polish',
            },
        )
        state['active_goal'] = {
            'intent': 'continue_dev',
            'source': 'chat_direct',
            'target': 'VISION A1 chat UX / goals polish',
        }
        text = append_goal_nudge(text, state)
        # Keep sticky goal until user clears or finishes a concrete task.
        save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'scan_suggest':
        typo = (msg or '').strip()
        state['pending_scan_confirm'] = {
            'active': True,
            'typo': typo,
            'suggest': 'scan',
        }
        save_dialog_state(root, state)
        text = (
            f'Похоже на опечатку рядом со **scan** («{typo}»). '
            'Имел в виду «просканируй проект» / `scan`? '
            'Ответь **да** — запущу `eurika scan .`; **нет** — отменю '
            '(документацию не открываю).'
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'web_search':
        from eurika.utils.web_search import (
            extract_http_urls,
            extract_web_search_query,
            format_web_pages_for_prompt,
            format_web_search_results,
            search_web,
            web_search_enabled,
        )
        if not web_search_enabled():
            text = 'Веб-поиск отключён (`EURIKA_WEB_SEARCH=0`).'
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        urls = extract_http_urls(msg)
        if urls:
            page_text = format_web_pages_for_prompt(urls, user_query=msg)
            if page_text:
                text = page_text
                append_safe(root, 'user', msg, None)
                append_safe(root, 'assistant', text, None)
                return {'text': text, 'error': None}
        from eurika.api.chat_direct import looks_like_cursor_pricing_question

        if looks_like_cursor_pricing_question(msg):
            query = "site:cursor.com docs account pricing cheapest model Composer 2.5 GPT-5.6 Luna per million tokens"
        else:
            query = extract_web_search_query(msg)
        results, provider, note = search_web(query)
        text = format_web_search_results(query, results, provider=provider, note=note)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        err = note if not results and note else None
        return {'text': text, 'error': err}
    if handler_id == 'read_terminal':
        from eurika.reasoning.architect import call_llm_with_prompt

        last = state.get("last_execution") if isinstance(state, dict) else None
        combined = terminal_visible_output(
            terminal_read_source(
                client_terminal_text=client_terminal_text,
                last_execution=last if isinstance(last, dict) else None,
            )
        )
        if not combined:
            text = (
                "Вкладка Terminal сейчас пустая: только приглашение `$`, вывода команд нет."
            )
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        prompt = (
            "Ты Eurika. Пользователь просит прочитать вкладку Terminal как есть.\n"
            "Описывай только текст из [Terminal output]. "
            "Не упоминай темы из истории чата, если их нет в этом выводе. "
            "Не предлагай команды, которых нет в выводе.\n\n"
            f"[Terminal output]\n{combined[-12000:]}\n"
        )
        raw, err = call_llm_with_prompt(prompt, max_tokens=900)
        text = (raw or "").strip() or (
            "Не удалось разобрать вывод терминала."
            + (f" ({err})" if err else "")
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': err}
    if handler_id == 'project_ls':
        report_obj = execute_spec(root, build_task_spec(intent='project_ls', message=msg))
        report = _report_dict(report_obj)
        store_last_execution(state, report)
        save_dialog_state(root, state)
        term_cmd, listing, code, ok = _shell_for_chat(
            shell_cmd='ls -la',
            run_command_with_result=run_command_with_result,
            fallback=lambda: (True, format_root_ls(root)),
            emit_cmd=emit_cmd or '$ ls -la',
        )
        if not (listing or '').strip():
            listing = format_root_ls(root)
            ok = True
        text = f'Да. Выполнил `ls` в корне проекта `{root}`:\n\n```\n{listing}\n```'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else listing},
            term_cmd,
            listing,
            code if run_command_with_result is not None else 0,
        )
    if handler_id == 'project_tree':
        report_obj = execute_spec(root, build_task_spec(intent='project_tree', message=msg))
        report = _report_dict(report_obj)
        store_last_execution(state, report)
        save_dialog_state(root, state)
        tree_cmd = (
            "find . -maxdepth 3 "
            "\\( -name .git -o -name .venv -o -name venv -o -name __pycache__ -o -name node_modules \\) "
            "-prune -o -print 2>/dev/null | head -n 500"
        )
        term_cmd, tree, code, ok = _shell_for_chat(
            shell_cmd=tree_cmd,
            run_command_with_result=run_command_with_result,
            fallback=lambda: (True, format_project_tree(root, max_depth=3, limit=500)),
            emit_cmd=emit_cmd or f'$ {tree_cmd}',
        )
        if not (tree or '').strip():
            tree = format_project_tree(root, max_depth=3, limit=500)
            ok = True
        text = f'Показываю фактическую структуру проекта `{root}`:\n\n```\n{tree}\n```'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else tree},
            term_cmd,
            tree,
            code if run_command_with_result is not None else 0,
        )
    if handler_id == 'scan':
        from eurika.api.chat_tools import run_eurika_command
        term_cmd, output, code, ok = _shell_for_chat(
            shell_cmd='eurika scan .',
            run_command_with_result=run_command_with_result,
            fallback=lambda: run_eurika_command(root, 'scan', '.', timeout=300),
            emit_cmd=emit_cmd or '$ eurika scan .',
        )
        store_last_execution(state, {'ok': ok, 'summary': 'eurika scan completed' if ok else 'eurika scan failed'})
        save_dialog_state(root, state)
        excerpt = (output or '').strip()[-8000:]
        text = (
            f'Выполнил `eurika scan .` для `{root}`:\n\n```\n{excerpt}\n```'
            if ok
            else f'Scan завершился с ошибкой:\n\n```\n{excerpt}\n```'
        )
        # Scan itself is not always an active_goal — pin a light goal for nudge/reflection.
        if not (isinstance(state.get('active_goal'), dict) and state.get('active_goal')):
            state['active_goal'] = {'intent': 'scan', 'source': 'chat_direct', 'target': '.'}
        text = append_goal_nudge(text, state)
        # Keep last_execution for «что получилось?»; don't sticky-pin scan as active goal.
        release_active_goal_keep_execution(state)
        save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else excerpt},
            term_cmd,
            excerpt,
            code,
        )
    if handler_id == 'saved_file_path':
        last_saved_abs = str(state.get('last_saved_file_abs') or '').strip()
        text = f'Полный путь к последнему сохранённому файлу:\n{last_saved_abs}' if last_saved_abs else 'Пока не вижу сохранённого файла в текущей сессии. Сначала попроси: «напиши ... и сохрани».'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'show_report':
        text = format_doctor_report_for_chat(root)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'goal_status':
        text = format_dialog_goal_block(load_dialog_state(root))
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'goal_reflection':
        # Prefer in-memory state (same request), fall back to disk.
        st = state if isinstance(state, dict) and state else load_dialog_state(root)
        facts = format_goal_reflection(st)
        text = enrich_goal_reflection_with_llm(facts, st, use_llm=True)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'clear_goal':
        st = load_dialog_state(root)
        if not isinstance(st, dict):
            st = {}
        clear_dialog_goals(st)
        save_dialog_state(root, st)
        # Keep in-memory state in sync for this request if caller passed one.
        if isinstance(state, dict):
            state['active_goal'] = {}
            state['pending_clarification'] = {}
            state['last_execution'] = {}
            state['pending_scan_confirm'] = {}
        text = (
            'Сбросил активную цель, ожидание уточнения и last_execution. '
            'Pending Apply/Reject (plan/git) не трогал — для них «отклонить». '
            'Дальше: новая задача или «что дальше по развитию?».'
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'git_push':
        import secrets
        from eurika.api.chat_direct import is_force_push_request
        from eurika.api.chat_git import inspect_push

        if is_force_push_request(msg):
            text = (
                "Force push не делаю (ни `--force`, ни `--force-with-lease`). "
                "Обычный `git push` — напиши «запушь» без force."
            )
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        info = inspect_push(root)
        branch = str(info.get('branch') or '?')
        if not info.get('has_origin'):
            text = f"Ветка `{branch}`: нет remote `origin` — push некуда."
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        ahead = info.get('ahead')
        if info.get('upstream') and ahead == 0:
            text = (
                f"Ветка `{branch}` уже синхронна с `{info.get('upstream')}` "
                "(ahead=0). Пушить нечего."
            )
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}
        token = secrets.token_hex(4)
        cmd = "git push -u origin HEAD" if info.get('needs_upstream') else "git push"
        proposed = f"Push {branch} to origin"
        state['pending_git_commit'] = {
            'message': proposed,
            'token': token,
            'paths': [],
            'skipped_secrets': [],
            'push_after': True,
            'action': 'push',
            'branch': branch,
            'protected': bool(info.get('protected')),
        }
        save_dialog_state(root, state)
        warn = ""
        if info.get('protected'):
            warn = (
                f"\nВетка `{branch}` — основная. Обычный push после Apply разрешён; "
                "force Эврика не делает."
            )
        ahead_s = f"ahead={ahead}" if ahead is not None else "upstream ещё нет"
        text = (
            f"**git push** `{branch}` → origin ({ahead_s}).\n"
            f"Команда: `{cmd}`.{warn}\n\n"
            f"Напиши **применяй token:{token}** (или [Apply])."
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'add_api_test':
        endpoint = extract_api_endpoint_from_request(msg)
        if endpoint:
            emit(f'# + test for {endpoint} in tests/test_api_serve.py')
            _, res = generate_and_append_api_test(root, endpoint)
            text = res
        else:
            text = 'Укажи endpoint, например: добавь тест для /api/summary или добавь тест для /api/chat'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'add_module_test':
        module_path = extract_module_path_from_request(msg)
        if module_path:
            emit(f'# + test for {module_path}')
            _, res = generate_module_test(root, module_path)
            text = res
        else:
            text = 'Укажи путь к модулю, например: добавь тест для eurika/polygon/long_function.py'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'show_file':
        rel_path = extract_file_path_from_show_request(msg)
        if rel_path:
            ok, content = read_file_for_chat(root, rel_path)
            if ok:
                lang = syntax_lang_for_path(rel_path)
                text = f'**Файл:** `{rel_path}`\n\n```{lang}\n{content}\n```'
            else:
                text = content
        else:
            text = 'Укажи путь к файлу, например: покажи файл .eurika/rules/eurika.mdc'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'roadmap_verify':
        from eurika.api.roadmap_verify import run_roadmap_verify
        text, _ = run_roadmap_verify(root, msg)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'ritual':
        from eurika.api.chat_tools import run_eurika_ritual
        ritual_shell = (
            "eurika scan . && eurika doctor . && eurika report-snapshot ."
        )
        term_cmd, output, code, ok = _shell_for_chat(
            shell_cmd=ritual_shell,
            run_command_with_result=run_command_with_result,
            fallback=lambda: run_eurika_ritual(root),
            emit_cmd=emit_cmd or f"$ {ritual_shell}",
        )
        state['active_goal'] = {
            'intent': 'ritual',
            'source': 'chat_direct',
            'target': 'scan→doctor→report-snapshot',
        }
        store_last_execution(
            state,
            {'ok': ok, 'summary': 'ritual completed' if ok else 'ritual had errors'},
        )
        save_dialog_state(root, state)
        text = f'Выполнил ритуал (scan → doctor → report-snapshot):\n\n```\n{output}\n```'
        if not ok:
            text = f'Ритуал выполнен с ошибками:\n\n```\n{output}\n```'
        text = append_goal_nudge(text, state)
        release_active_goal_keep_execution(state)
        save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else output},
            term_cmd,
            output,
            code,
        )
    if handler_id == 'release_check':
        exit_code = -1
        term_cmd = None
        if run_command_with_result is not None:
            term_cmd, output, exit_code = _run_emit_with_result(
                emit_cmd or "$ ./scripts/release_check.sh",
                run_command_with_result,
            )
            ok = exit_code == 0
            if not output.strip() and not ok:
                output = f"release_check failed (exit {exit_code})"
        else:
            from eurika.api.chat_tools import run_release_check
            ok, output = run_release_check(root)
            term_cmd = "$ ./scripts/release_check.sh"
            exit_code = 0 if ok else 1
        state['last_release_check_output'] = output
        state['last_release_check_ok'] = ok
        state['active_goal'] = {'intent': 'release_check', 'source': 'chat_direct', 'target': 'release_check'}
        store_last_execution(state, {'ok': ok, 'summary': 'release_check passed' if ok else 'release_check failed'})
        save_dialog_state(root, state)
        if ok:
            text = f'{brief_release_check_analysis(output, True)}\n\n```\n{output[-8000:]}\n```'
        else:
            summary = brief_release_check_analysis(output, False)
            excerpt = output[-6000:].strip() if output.strip() else '(вывод пуст)'
            text = f'{summary}\n\n```\n{excerpt}\n```'
        text = append_goal_nudge(text, state)
        if isinstance(state.get('active_goal'), dict) and state.get('active_goal'):
            release_active_goal_keep_execution(state)
            save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None},
            term_cmd,
            output,
            exit_code,
        )
    if handler_id == 'smoke_test':
        from eurika.api.chat_tools import run_chat_smoke
        # Prefer a visible shell smoke when Terminal callback is available.
        smoke_shell = (
            "python -c \"from eurika.ml.torch_runtime import torch_status; "
            "print(torch_status(run_smoke_check=True))\" "
            "&& python -m pytest tests/test_qt_smoke.py -q --tb=line"
        )
        term_cmd, output, code, ok = _shell_for_chat(
            shell_cmd=smoke_shell,
            run_command_with_result=run_command_with_result,
            fallback=lambda: run_chat_smoke(root),
            emit_cmd=emit_cmd or f"$ {smoke_shell}",
        )
        state['last_smoke_ok'] = ok
        state['last_smoke_output'] = output
        save_dialog_state(root, state)
        text = f"**Smoke test:** {'OK' if ok else 'FAIL'}\n\n```\n{output[-8000:]}\n```"
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else output},
            term_cmd,
            output,
            code,
        )
    if handler_id == 'self_check':
        from eurika.api.chat_tools import run_self_check_capture

        term_cmd, output, code, ok = _shell_for_chat(
            shell_cmd='eurika self-check .',
            run_command_with_result=run_command_with_result,
            fallback=lambda: run_self_check_capture(root),
            emit_cmd=emit_cmd or '$ eurika self-check .',
        )
        text = format_self_check_for_chat(
            output or '',
            ok=ok,
            os_focus=False,
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None if ok else output},
            term_cmd,
            output,
            code,
        )
    if handler_id == 'host_health':
        from eurika.api.host_health import (
            enrich_host_health_with_llm,
            format_host_health_for_chat,
            run_host_health_probe,
        )

        health = run_host_health_probe()
        facts = format_host_health_for_chat(health)
        text = enrich_host_health_with_llm(facts, use_llm=True)
        store_last_execution(
            state,
            {
                "ok": health.ok,
                "summary": f"host_health level={health.level}",
                "artifacts_changed": [],
            },
        )
        save_dialog_state(root, state)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        # Chat: always expert text (never raw probe as error). Terminal: probe log.
        return _with_terminal(
            {'text': text, 'error': None},
            "$ # host-health read-only (uptime / free / df / journal / …)",
            health.output,
            0 if health.ok else 1,
        )
    if handler_id == 'ml_status':
        from eurika.utils.env import env_bool

        lines = ['**Статус ML**', '']
        # Torch
        try:
            from eurika.ml.torch_runtime import format_torch_block, torch_status

            lines.append(format_torch_block(torch_status(run_smoke_check=False)).strip())
        except Exception as exc:
            lines.append(f'PYTORCH: error {type(exc).__name__}: {exc}')
        lines.append('')
        # Chat ML intent
        on = env_bool('EURIKA_USE_ML_INTENT')
        lines.append(f'EURIKA_USE_ML_INTENT: {"1 (вкл)" if on else "0 (выкл)"}')
        vec_on = env_bool('EURIKA_USE_VECTOR_INTENT')
        lines.append(f'EURIKA_USE_VECTOR_INTENT: {"1 (вкл)" if vec_on else "0 (выкл)"}')
        try:
            from eurika.ml.intent_router import intent_meta_path

            mp = intent_meta_path(root)
            if mp.is_file():
                import json

                meta = json.loads(mp.read_text(encoding='utf-8'))
                lines.append(
                    f"intent router: samples={meta.get('samples')}, "
                    f"acc={meta.get('train_accuracy')}, arch={meta.get('arch')}"
                )
            else:
                lines.append('intent router: весов нет')
        except Exception as exc:
            lines.append(f'intent router: {type(exc).__name__}: {exc}')
        lines.append('')
        # Market paper learning
        try:
            from eurika.ml.learning_status import format_market_learning_report

            lines.append(format_market_learning_report(root))
        except Exception as exc:
            lines.append(f'Market learning: {type(exc).__name__}: {exc}')
        lines.append('')
        lines.append('Команды: «проведи smoke test» · Models→ML · Chat→Market')
        text = '\n'.join(lines)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'market_logic':
        text = (
            "**Логика Market в Eurika (paper-only, без live-ордеров)**\n\n"
            "По [VISION](docs/VISION.md): ты строишь **скелет** (данные, метки, банк, journal, verify); "
            "Eurika **учится зарабатывать** по исходам (edge / `pnl_usdt` → веса), "
            "а не по ручным правилам вроде «RSI→buy».\n\n"
            "**Цикл** (`eurika/ml/`, Chat → Market):\n"
            "1. Свечи Binance spot / USD-M futures → **24 фичи** с окна баров "
            "(ret, vol, rsi/bb/macd, структура) — **без** id тикера.\n"
            "2. **Entry** MLP → HOLD/BUY/SELL (`market_policy.pt`) — **одна** общая policy на все пары.\n"
            "3. Исполнение paper: style (market/limit/stop/oco), levels TP/SL/trail (`market_levels.pt`), "
            "банк ~1000 USDT, риск ~1% маржи/сделку, soft-fut плечо.\n"
            "4. **Exit**: TP/SL/trail/горизонт/exit-MLP (`market_exit.pt`); метка + edge → дообучение.\n"
            "5. Артефакты: `paper_trades.jsonl`, `open_paper.json`, `paper_portfolio.json`, "
            "`market_journal.jsonl`, `weights/*.pt`.\n\n"
            "Soft-entry / soft-fut / cooldown — **рычаги скелета**, не «стратегия навсегда».\n\n"
            "Сейчас на рынке (банк/opens) → «анализ рынка».\n"
            "Общая модель vs per-ticker → «одна модель или на каждый тикер?»."
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'market_learning_report':
        try:
            from eurika.ml.learning_status import format_market_learning_report

            text = format_market_learning_report(root)
        except Exception as exc:
            text = f'Market learning: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'llm_teacher_execution':
        try:
            from eurika.ml.llm_teacher_stats import format_llm_teacher_execution_report
            from eurika.ml.root import resolve_market_root

            text = format_llm_teacher_execution_report(resolve_market_root())
        except Exception as exc:
            text = f'LLM execution: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'llm_teacher_stats':
        try:
            from eurika.ml.llm_teacher_stats import format_llm_teacher_stats_report
            from eurika.ml.root import resolve_market_root

            text = format_llm_teacher_stats_report(resolve_market_root())
        except Exception as exc:
            text = f'LLM-учитель: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'llm_shadow_report':
        try:
            from eurika.ml.llm_teacher_stats import format_llm_shadow_report
            from eurika.ml.root import resolve_market_root

            text = format_llm_shadow_report(resolve_market_root())
        except Exception as exc:
            text = f'LLM shadow: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'market_ticker_brief':
        try:
            from eurika.ml.ticker_brief import format_ticker_market_brief, parse_ticker_request

            parsed = parse_ticker_request(msg)
            if not parsed:
                text = (
                    "Укажи тикер: например «разбор тикера BTCUSDT на фьючерсах» "
                    "или «анализ ETHUSDT spot»."
                )
            else:
                symbol, market = parsed
                text = format_ticker_market_brief(root, symbol, market=market, sync=True)
        except Exception as exc:
            text = f'Разбор тикера: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'portfolio_agent_status':
        try:
            from eurika.ml.portfolio_agent import format_portfolio_status

            text = format_portfolio_status(root)
        except Exception as exc:
            text = f'Portfolio статус: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'portfolio_agent_once':
        try:
            from eurika.agent.cursor_judge import cursor_key_status
            from eurika.ml.portfolio_agent import run_portfolio_cycle

            if not cursor_key_status(root).get("api_key_set"):
                text = (
                    "Portfolio цикл: нет CURSOR_API_KEY в .env — агент не вызовется. "
                    "Статус без LLM: скажи «статус portfolio»."
                )
            else:
                out = run_portfolio_cycle(root)
                digest = str(out.get("digest") or "").strip()
                body = str(out.get("body") or "").strip()
                if digest:
                    text = digest
                    if body:
                        text = f"{digest}\n\n---\n{body[:3000]}"
                else:
                    eq = out.get("holistic_equity_usdt")
                    bits = (
                        f"ok={out.get('ok')} actions={out.get('actions_n')} "
                        f"trade_place={(out.get('trade') or {}).get('place')} "
                        f"teacher={(out.get('teacher') or {}).get('stored')} "
                        f"equity={eq}"
                    )
                    text = f"Portfolio цикл:\n{bits}\n\n{body[:4000]}"
        except Exception as exc:
            text = f'Portfolio цикл: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'market_situation':
        try:
            from eurika.ml.learning_status import format_market_situation_block

            text = format_market_situation_block(root)
        except Exception as exc:
            text = f'Market сейчас: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'session_digest':
        try:
            from eurika.ml.session_digest import build_session_digest, format_session_digest

            # Chat ask: show digest but do not advance last-seen (UI open does that).
            data = build_session_digest(root, mark_seen=False)
            text = format_session_digest(data)
        except Exception as exc:
            text = f'Digest: {type(exc).__name__}: {exc}'
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'market_ml_scope':
        text = (
            "**Market ML: общая модель, не per-ticker.**\n\n"
            "По коду (`eurika/ml/market_model.py`):\n"
            "1. Свечи хранятся отдельно по парам (ADAUSDT, BTCUSDT, …).\n"
            "2. Признаки — **24** числа с окна свечей **без** id символа "
            "(ret, vol, atr_burst, range_break, rsi, bb, macd, структура…).\n"
            "3. Все paper-сделки из `paper_trades.jsonl` учат **один MLP** → HOLD/BUY/SELL "
            "(`market_policy.pt`; legacy Linear только как fallback).\n"
            "4. Предсказание для любой пары идёт через эти общие веса.\n\n"
            "Итого: учится «форма движения» рынка в целом; отдельной стратегии на каждый тикер нет.\n"
            "Per-ticker модели — пока не реализованы.\n\n"
            "Срез *что сейчас на рынке* (банк / opens / советы) — спроси: "
            "«анализ рынка» / «что сейчас на маркете?».\n"
            "Разбор одной пары (свечи TF1/TF2 + MLP + shadow) — "
            "«разбор тикера BTCUSDT на фьючерсах»."
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id in {
        'ml_intent_on',
        'ml_intent_off',
        'ml_intent_status',
        'vector_intent_on',
        'vector_intent_off',
        'vector_intent_status',
    }:
        from eurika.utils.env import env_bool, upsert_project_env_var

        is_vector = handler_id.startswith('vector_')
        flag = 'EURIKA_USE_VECTOR_INTENT' if is_vector else 'EURIKA_USE_ML_INTENT'

        if handler_id.endswith('_status'):
            on = env_bool(flag)
            env_val = (os.environ.get(flag) or '0').strip() or '0'
            env_file = root / '.env'
            in_dotenv = False
            if env_file.is_file():
                try:
                    in_dotenv = any(
                        ln.strip().startswith(f'{flag}=')
                        for ln in env_file.read_text(encoding='utf-8').splitlines()
                    )
                except OSError:
                    in_dotenv = False
            extra = ''
            if not is_vector:
                try:
                    from eurika.ml.intent_router import intent_meta_path
                    import json

                    mp = intent_meta_path(root)
                    if mp.is_file():
                        meta = json.loads(mp.read_text(encoding='utf-8'))
                        extra = (
                            f"\nРоутер: samples={meta.get('samples')}, "
                            f"acc={meta.get('train_accuracy')}, arch={meta.get('arch')}"
                        )
                except Exception:
                    extra = ''
            else:
                extra = (
                    "\nНужен Ollama embedding: `ollama pull nomic-embed-text`. "
                    "Fuzzy-match интентов по смыслу (CR-G2)."
                )
            text = (
                f"**{flag}** = `{env_val}` "
                f"({'включён' if on else 'выключен'}).\n"
                f"В процессе: `os.environ`={'1' if on else '0'}; "
                f"в `.env`: {'да' if in_dotenv else 'нет'}."
                f"{extra}\n"
                f"Вкл: «включи {flag}=1». Выкл: «выключи {flag}»."
            )
            append_safe(root, 'user', msg, None)
            append_safe(root, 'assistant', text, None)
            return {'text': text, 'error': None}

        enable = handler_id.endswith('_on')
        path = upsert_project_env_var(root, flag, '1' if enable else '0')
        extra = ''
        if enable and not is_vector:
            try:
                from eurika.ml.intent_router import train_intent_router
                from eurika.ml.torch_runtime import torch_available

                if torch_available():
                    trained = train_intent_router(root, epochs=120)
                    if trained.get('ok'):
                        acc = float(trained.get('train_accuracy') or 0)
                        extra = (
                            f"\nРоутер обучен: samples={trained.get('samples')}, "
                            f"классов={trained.get('classes')}, acc={acc:.3f}"
                        )
                        if acc < 0.5:
                            extra += "\n⚠ acc низкая — ML почти не будет перехватывать; YAML-интенты ок."
                    else:
                        extra = f"\nОбучение роутера: {trained.get('error')}"
                else:
                    extra = "\nTorch недоступен — флаг записан, роутер после `pip install -e '.[torch]'`."
            except Exception as exc:
                extra = f"\nОбучение роутера: {type(exc).__name__}: {exc}"
        elif enable and is_vector:
            extra = (
                "\nПроверь: `ollama pull nomic-embed-text` и что Ollama запущена. "
                "Перезапуск Qt не обязателен (флаг уже в os.environ)."
            )
        text = (
            f"**{flag}** = `{'1' if enable else '0'}` "
            f"({'включён' if enable else 'выключен'}).\n"
            f"Сохранено в `{path}`."
            f"{extra}\n"
            "YAML-интенты по-прежнему главнее fuzzy/ML."
        )
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return {'text': text, 'error': None}
    if handler_id == 'git_commit':
        import secrets
        from eurika.api.chat_direct import (
            is_git_commit_and_push_request,
            is_git_push_request,
        )
        from eurika.api.chat_git import (
            collect_commit_preview,
            format_commit_preview_blocks,
            inspect_push,
        )
        from eurika.api.chat_tools import git_diff, git_status
        term_parts: list[str] = []
        if run_command_with_result is not None:
            st_cmd, status_out, st_code, ok_status = _shell_for_chat(
                shell_cmd='git status',
                run_command_with_result=run_command_with_result,
            )
            if st_cmd:
                term_parts.append(f"{st_cmd}\n{status_out}")
            df_cmd, diff_out, df_code, ok_diff = _shell_for_chat(
                shell_cmd='git diff && git diff --cached',
                run_command_with_result=run_command_with_result,
            )
            if df_cmd:
                term_parts.append(f"{df_cmd}\n{diff_out}")
            term_cmd = "$ git status && git diff && git diff --cached"
            term_out = "\n\n".join(term_parts)
            term_code = st_code if st_code != 0 else df_code
        else:
            ok_status, status_out = git_status(root)
            ok_diff, diff_out = git_diff(root)
            term_cmd = "$ git status && git diff && git log -8 --oneline"
            term_out = f"{status_out or ''}\n{diff_out or ''}".strip()
            term_code = 0 if ok_status else 1
        preview = collect_commit_preview(root)
        if not preview.get('ok'):
            ok_status = False
            if not status_out:
                status_out = str(preview.get('error') or 'Не git-репозиторий или git недоступен.')
        push_after = is_git_commit_and_push_request(msg) or is_git_push_request(msg)
        push_info = inspect_push(root) if push_after else None
        include = list(preview.get('include') or [])
        if ok_status and include:
            explicit = extract_commit_message_from_request(msg)
            if explicit:
                proposed = explicit
            else:
                minimal = msg.strip().lower() in (
                    'собери коммит', 'сделай коммит', 'commit', 'коммит',
                    'закоммить и запушь', 'commit and push',
                ) or len(msg.strip()) < 20
                log_snip = str(preview.get('log') or '')
                if not minimal:
                    inferred = infer_commit_message_via_llm(
                        msg,
                        status_out,
                        (diff_out[:1500] if diff_out else ''),
                        log_snip,
                    )
                    proposed = inferred if inferred else propose_commit_message_from_status(
                        status_out, diff_out or ''
                    )
                else:
                    proposed = propose_commit_message_from_status(status_out, diff_out or '')
            token = secrets.token_hex(4)
            state['pending_git_commit'] = {
                'message': proposed,
                'token': token,
                'paths': include,
                'skipped_secrets': list(preview.get('skipped_secrets') or []),
                'push_after': push_after,
                'action': 'commit_push' if push_after else 'commit',
                'branch': preview.get('branch') or '',
                'protected': bool(preview.get('protected')),
            }
            save_dialog_state(root, state)
            blocks = format_commit_preview_blocks(
                status_out=status_out,
                diff_out=diff_out or '',
                preview=preview,
                proposed=proposed,
                token=token,
                push_after=push_after,
                push_info=push_info,
            )
        else:
            blocks = [f"**git status**\n```\n{status_out or '(пусто)'}\n```"]
            skipped = list(preview.get('skipped_secrets') or [])
            if skipped and not include:
                blocks.append(
                    'Нет безопасных файлов для коммита. Пропущены секреты:\n'
                    + '\n'.join(f'- `{p}`' for p in skipped)
                )
            else:
                blocks.append('\nНет изменений для коммита.')
        text = '\n\n'.join(blocks)
        append_safe(root, 'user', msg, None)
        append_safe(root, 'assistant', text, None)
        return _with_terminal(
            {'text': text, 'error': None},
            term_cmd,
            term_out,
            term_code,
        )
    return None

def _report_dict(report_obj: Any) -> Dict[str, Any]:
    return {'ok': report_obj.ok, 'summary': report_obj.summary, 'applied_steps': report_obj.applied_steps, 'skipped_steps': report_obj.skipped_steps, 'verification': report_obj.verification, 'artifacts_changed': report_obj.artifacts_changed, 'error': report_obj.error}