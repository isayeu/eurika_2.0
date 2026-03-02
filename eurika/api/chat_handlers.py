"""Direct handler execution (P0.4 split from chat.py)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from eurika.api.task_executor import build_task_spec, execute_spec

from .chat_context import save_dialog_state, store_last_execution
from .chat_direct import (
    extract_api_endpoint_from_request,
    extract_commit_message_from_request,
    extract_file_path_from_show_request,
    extract_module_path_from_request,
    generate_and_append_api_test,
    generate_module_test,
    infer_commit_message_via_llm,
    propose_commit_message_from_status,
)
from .chat_utils import (
    brief_release_check_analysis,
    format_doctor_report_for_chat,
    format_project_tree,
    format_root_ls,
    read_file_for_chat,
    syntax_lang_for_path,
)


def run_direct_handlers(
    handler_id: Optional[str],
    root: Path,
    msg: str,
    state: Dict[str, Any],
    emit_cmd: Optional[str],
    emit: Callable[[str], None],
    append_safe: Callable[[Path, str, str, Optional[str]], None],
    run_command_with_result: Optional[Callable[[str], tuple[str, int]]],
) -> Optional[Dict[str, Any]]:
    """Execute direct handler; return result dict if handled, else None."""
    if not handler_id:
        return None
    if handler_id == "identity":
        text = "Я Eurika — архитектурный coding-ассистент этого проекта. Могу помочь с анализом, рефакторингом и изменениями кода."
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "project_ls":
        report_obj = execute_spec(root, build_task_spec(intent="project_ls", message=msg))
        report = _report_dict(report_obj)
        store_last_execution(state, report)
        save_dialog_state(root, state)
        listing = format_root_ls(root)
        text = f"Да. Выполнил `ls` в корне проекта `{root}`:\n\n```\n{listing}\n```"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "project_tree":
        report_obj = execute_spec(root, build_task_spec(intent="project_tree", message=msg))
        report = _report_dict(report_obj)
        store_last_execution(state, report)
        save_dialog_state(root, state)
        tree = format_project_tree(root, max_depth=3, limit=500)
        text = f"Показываю фактическую структуру проекта `{root}`:\n\n```\n{tree}\n```"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "saved_file_path":
        last_saved_abs = str(state.get("last_saved_file_abs") or "").strip()
        text = f"Полный путь к последнему сохранённому файлу:\n{last_saved_abs}" if last_saved_abs else "Пока не вижу сохранённого файла в текущей сессии. Сначала попроси: «напиши ... и сохрани»."
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "show_report":
        text = format_doctor_report_for_chat(root)
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "add_api_test":
        endpoint = extract_api_endpoint_from_request(msg)
        if endpoint:
            emit(f"# + test for {endpoint} in tests/test_api_serve.py")
            _, res = generate_and_append_api_test(root, endpoint)
            text = res
        else:
            text = "Укажи endpoint, например: добавь тест для /api/summary или добавь тест для /api/chat"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "add_module_test":
        module_path = extract_module_path_from_request(msg)
        if module_path:
            emit(f"# + test for {module_path}")
            _, res = generate_module_test(root, module_path)
            text = res
        else:
            text = "Укажи путь к модулю, например: добавь тест для eurika/polygon/long_function.py"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "show_file":
        rel_path = extract_file_path_from_show_request(msg)
        if rel_path:
            ok, content = read_file_for_chat(root, rel_path)
            if ok:
                lang = syntax_lang_for_path(rel_path)
                text = f"**Файл:** `{rel_path}`\n\n```{lang}\n{content}\n```"
            else:
                text = content
        else:
            text = "Укажи путь к файлу, например: покажи файл .eurika/rules/eurika.mdc"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "roadmap_verify":
        from eurika.api.roadmap_verify import run_roadmap_verify

        text, _ = run_roadmap_verify(root, msg)
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    if handler_id == "ritual":
        from eurika.api.chat_tools import run_eurika_ritual

        ok, output = run_eurika_ritual(root)
        text = f"Выполнил ритуал (scan → doctor → report-snapshot):\n\n```\n{output}\n```"
        if not ok:
            text = f"Ритуал выполнен с ошибками:\n\n```\n{output}\n```"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None if ok else output}
    if handler_id == "release_check":
        exit_code = -1
        if run_command_with_result is not None:
            shell_cmd = (emit_cmd or "").strip().lstrip("$ ").strip()
            if shell_cmd:
                output, exit_code = run_command_with_result(shell_cmd)
                ok = exit_code == 0
            else:
                ok, output = False, "no command"
            terminal_cmd = f"$ {shell_cmd}" if shell_cmd else None
        else:
            from eurika.api.chat_tools import run_release_check

            ok, output = run_release_check(root)
            terminal_cmd = None
        state["last_release_check_output"] = output
        state["last_release_check_ok"] = ok
        save_dialog_state(root, state)
        if ok:
            text = f"{brief_release_check_analysis(output, True)}\n\n```\n{output[-8000:]}\n```"
        else:
            summary = brief_release_check_analysis(output, False)
            excerpt = output[-6000:].strip() if output.strip() else "(вывод пуст)"
            text = f"{summary}\n\n```\n{excerpt}\n```"
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        result = {"text": text, "error": None}
        if terminal_cmd is not None:
            result["terminal_cmd"] = terminal_cmd
            result["terminal_output"] = output
            result["terminal_exit_code"] = exit_code
        return result
    if handler_id == "git_commit":
        from eurika.api.chat_tools import git_diff, git_status

        ok_status, status_out = git_status(root)
        ok_diff, diff_out = git_diff(root)
        if not ok_status and not status_out:
            status_out = "Не git-репозиторий или git недоступен."
        blocks = [f"**git status**\n```\n{status_out or '(пусто)'}\n```"]
        if diff_out:
            blocks.append(f"**git diff**\n```\n{diff_out[:4000]}{'...' if len(diff_out) > 4000 else ''}\n```")
        if ok_status and status_out.strip():
            explicit = extract_commit_message_from_request(msg)
            if explicit:
                proposed = explicit
            else:
                minimal = msg.strip().lower() in ("собери коммит", "сделай коммит", "commit", "коммит") or len(msg.strip()) < 20
                if not minimal:
                    inferred = infer_commit_message_via_llm(msg, status_out, diff_out[:1500] if diff_out else "")
                    proposed = inferred if inferred else propose_commit_message_from_status(status_out)
                else:
                    proposed = propose_commit_message_from_status(status_out)
            state["pending_git_commit"] = {"message": proposed}
            save_dialog_state(root, state)
            blocks.append(f"\nПредлагаю коммит с сообщением: «{proposed}». Напиши **применяй** для подтверждения.")
        else:
            blocks.append("\nНет изменений для коммита.")
        text = "\n\n".join(blocks)
        append_safe(root, "user", msg, None)
        append_safe(root, "assistant", text, None)
        return {"text": text, "error": None}
    return None


def _report_dict(report_obj: Any) -> Dict[str, Any]:
    return {
        "ok": report_obj.ok,
        "summary": report_obj.summary,
        "applied_steps": report_obj.applied_steps,
        "skipped_steps": report_obj.skipped_steps,
        "verification": report_obj.verification,
        "artifacts_changed": report_obj.artifacts_changed,
        "error": report_obj.error,
    }
