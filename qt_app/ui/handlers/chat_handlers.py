"""Chat preferences, send, apply/reject handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QInputDialog, QMessageBox

from ..main_window_helpers import ChatWorker
from ..tabs import terminal_tab

if TYPE_CHECKING:
    from ..main_window import MainWindow


def load_chat_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    provider = str(data.get("chat_provider", "auto"))
    if provider not in {"auto", "openai", "ollama"}:
        provider = "auto"
    main.chat_provider_combo.setCurrentText(provider)
    main.chat_openai_model.setText(str(data.get("chat_openai_model", "")))
    main.chat_ollama_model.setText(str(data.get("chat_ollama_model", "")))
    timeout_val = data.get("chat_timeout_sec", 30)
    try:
        timeout = int(timeout_val)
    except (TypeError, ValueError):
        timeout = 30
    main.chat_timeout_spin.setValue(min(9999, max(0, timeout)))
    main.ollama_hsa_edit.setText(str(data.get("ollama_hsa_override_gfx", "10.3.0")))
    main.ollama_rocr_edit.setText(str(data.get("ollama_rocr_visible_devices", "0")))
    main.ollama_hip_edit.setText(str(data.get("ollama_hip_visible_devices", "0")))
    main.ollama_search_edit.setText(str(data.get("ollama_search_query", "qwen")))
    main.ollama_custom_model_edit.setText(str(data.get("ollama_custom_model", "")))
    saved_available = str(data.get("ollama_available_model", "")).strip()
    main._saved_available_model = saved_available


def refresh_chat_goal_view(main: MainWindow) -> None:
    state = main._api.get_chat_dialog_state()
    goal = state.get("active_goal") if isinstance(state, dict) else {}
    pending = state.get("pending_clarification") if isinstance(state, dict) else {}
    pending_plan = state.get("pending_plan") if isinstance(state, dict) else {}
    last_execution = state.get("last_execution") if isinstance(state, dict) else {}
    lines: list[str] = []
    if isinstance(goal, dict) and goal:
        lines.append("Current interpreted goal:")
        intent = goal.get("intent", "-")
        target = goal.get("target", "")
        source = goal.get("source", "-")
        confidence = goal.get("confidence")
        risk_level = goal.get("risk_level")
        if target:
            lines.append(f"- intent={intent}, target={target}, source={source}")
        else:
            lines.append(f"- intent={intent}, source={source}")
        if confidence is not None:
            lines.append(f"- confidence={confidence}")
        if risk_level:
            lines.append(f"- risk={risk_level}")
        plan_steps = goal.get("plan_steps") or []
        if isinstance(plan_steps, list) and plan_steps:
            lines.append("- plan:")
            for step in plan_steps[:5]:
                lines.append(f"  - {step}")
    if isinstance(pending, dict) and pending:
        original = str(pending.get("original", "")).strip()
        lines.append("")
        lines.append("Pending clarification:")
        lines.append(f"- {(original[:180] if original else '(awaiting details)')}")
    if isinstance(pending_plan, dict) and pending_plan:
        main._pending_plan_token = str(pending_plan.get("token") or "")
        lines.append("")
        lines.append("Awaiting confirmation:")
        lines.append(
            f"- intent={pending_plan.get('intent', '-')}, risk={pending_plan.get('risk_level', '-')}, token={pending_plan.get('token', '-')}"
        )
        steps = pending_plan.get("steps") or []
        if isinstance(steps, list) and steps:
            for step in steps[:4]:
                lines.append(f"  - {step}")
    if isinstance(last_execution, dict) and last_execution:
        lines.append("")
        lines.append("Last execution:")
        lines.append(
            f"- ok={last_execution.get('ok')}, verification_ok={last_execution.get('verification_ok')}, summary={last_execution.get('summary', '-')}"
        )
        changed = last_execution.get("artifacts_changed") or []
        if isinstance(changed, list) and changed:
            lines.append(f"- changed={', '.join((str(x) for x in changed[:6]))}")
    if not lines:
        lines.append("No active interpreted goal yet.")
    main.chat_goal_view.setPlainText("\n".join(lines))
    has_pending_plan = isinstance(pending_plan, dict) and bool(pending_plan)
    has_effective_pending = has_pending_plan or main._pending_plan_fallback_active
    main.chat_apply_btn.setEnabled(has_effective_pending)
    main.chat_reject_btn.setEnabled(has_effective_pending)
    if has_pending_plan and isinstance(pending_plan, dict):
        pending_intent = str(pending_plan.get("intent") or "-")
        pending_target = str(pending_plan.get("target") or "").strip()
        if pending_target:
            main.chat_pending_label.setText(
                f"Pending plan: intent={pending_intent}, target={pending_target}"
            )
        else:
            main.chat_pending_label.setText(f"Pending plan: intent={pending_intent}")
        steps = pending_plan.get("steps") or []
        if isinstance(steps, list) and steps:
            tooltip = "Plan steps:\n" + "\n".join(
                (f"- {str(step)}" for step in steps[:6])
            )
            main.chat_pending_label.setToolTip(tooltip)
            main.chat_apply_btn.setToolTip(tooltip)
            main.chat_reject_btn.setToolTip(tooltip)
        else:
            main.chat_pending_label.setToolTip("")
            main.chat_apply_btn.setToolTip("")
            main.chat_reject_btn.setToolTip("")
    elif main._pending_plan_fallback_active:
        if main._pending_plan_token:
            main.chat_pending_label.setText(
                f"Pending plan: token={main._pending_plan_token}"
            )
        else:
            main.chat_pending_label.setText("Pending plan: awaiting confirmation")
        main.chat_pending_label.setToolTip("Awaiting confirmation from chat response.")
        main.chat_apply_btn.setToolTip("Apply pending action")
        main.chat_reject_btn.setToolTip("Reject pending action")
    else:
        main._pending_plan_token = ""
        main.chat_pending_label.setText("Pending plan: none")
        main.chat_pending_label.setToolTip("")
        main.chat_apply_btn.setToolTip("")
        main.chat_reject_btn.setToolTip("")


def save_chat_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    data["chat_provider"] = main.chat_provider_combo.currentText()
    data["chat_openai_model"] = main.chat_openai_model.text().strip()
    data["chat_ollama_model"] = main.chat_ollama_model.text().strip()
    data["chat_timeout_sec"] = main.chat_timeout_spin.value()
    data["ollama_hsa_override_gfx"] = main.ollama_hsa_edit.text().strip()
    data["ollama_rocr_visible_devices"] = main.ollama_rocr_edit.text().strip()
    data["ollama_hip_visible_devices"] = main.ollama_hip_edit.text().strip()
    data["ollama_search_query"] = main.ollama_search_edit.text().strip()
    data["ollama_custom_model"] = main.ollama_custom_model_edit.text().strip()
    data["ollama_available_model"] = main.ollama_available_combo.currentText().strip()
    main._settings.save(data)


def _format_chat_line(role: str, text: str, *, is_error: bool = False) -> str:
    """Format chat line with bold colored role label. Preserve newlines for QTextEdit Rich Text."""
    escaped = html.escape(text).replace("\n", "<br>")
    if role == "user":
        label = '<b><span style="color:#1e40af">You</span></b>'
    else:
        label = '<b><span style="color:#15803d">Eurika</span></b>' if not is_error else '<b><span style="color:#b91c1c">Eurika</span></b>'
    return f"{label}: {escaped}"


def dispatch_chat_message(main: MainWindow, message: str) -> None:
    if not message:
        return
    if main._chat_worker is not None and main._chat_worker.isRunning():
        QMessageBox.information(main, "Chat", "Chat request already in progress.")
        return
    save_chat_preferences(main)
    provider = main.chat_provider_combo.currentText()
    openai_model = main.chat_openai_model.text().strip()
    ollama_model = main.chat_ollama_model.text().strip()
    timeout_sec = main.chat_timeout_spin.value()
    main.chat_transcript.append(_format_chat_line("user", message))
    main._chat_history.append({"role": "user", "content": message})
    main.chat_input.clear()
    main.chat_send_btn.setEnabled(False)
    main.status_label.setText("State: chat-running")
    worker = ChatWorker(
        api=main._api,
        message=message,
        history=list(main._chat_history),
        provider=provider,
        openai_model=openai_model,
        ollama_model=ollama_model,
        timeout_sec=timeout_sec,
        run_command_with_result=lambda cmd: _run_command_subprocess(cmd, str(main._api._root())),
    )
    main._chat_worker = worker
    worker.finished_payload.connect(lambda p: on_chat_result(main, p))
    worker.failed.connect(lambda e: on_chat_error(main, e))
    worker.finished.connect(lambda: on_chat_finished(main))
    worker.system_action_occurred.connect(lambda cmd: on_system_action(main, cmd))
    worker.start()


def send_chat_message(main: MainWindow) -> None:
    message = main.chat_input.toPlainText().strip()
    dispatch_chat_message(main, message)


def apply_pending_chat_plan(main: MainWindow) -> None:
    token = main._pending_plan_token.strip()
    msg = f"применяй token:{token}" if token else "применяй"
    main._pending_plan_fallback_active = False
    dispatch_chat_message(main, msg)


def reject_pending_chat_plan(main: MainWindow) -> None:
    main._pending_plan_fallback_active = False
    dispatch_chat_message(main, "отклонить")


def _run_command_subprocess(cmd: str, project_root: str) -> tuple[str, int]:
    """Run command in worker thread (avoids blocking GUI). Returns (output, exit_code)."""
    import subprocess

    from ..main_window_helpers import strip_ansi

    try:
        r = subprocess.run(
            ["bash", "-c", cmd],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=None,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        return (strip_ansi(out), r.returncode)
    except subprocess.TimeoutExpired:
        return ("timeout", -1)
    except Exception as e:
        return (str(e), -1)


def on_system_action(main: MainWindow, cmd: str) -> None:
    """Emit Chat action to Terminal tab; if cmd starts with '$ ', also execute it."""
    if hasattr(main, "terminal_emulator_output") and main.terminal_emulator_output:
        main.terminal_emulator_output.append(f"[Chat] {cmd}")
    run_cmd = (cmd or "").strip()
    if run_cmd.startswith("$ "):
        shell_cmd = run_cmd[2:].strip()
        if shell_cmd and hasattr(main, "terminal_emulator_input"):
            if not terminal_tab.execute_command_from_chat(main, shell_cmd):
                main.terminal_emulator_output.append(
                    "[Chat] (terminal busy — run manually in input below)"
                )


def on_chat_result(main: MainWindow, payload: dict[str, Any]) -> None:
    if "terminal_output" in payload and hasattr(main, "terminal_emulator_output"):
        cmd = payload.get("terminal_cmd", "")
        out = payload.get("terminal_output", "")
        code = payload.get("terminal_exit_code", -1)
        if cmd:
            main.terminal_emulator_output.append(f"[Chat] {cmd}")
        if out:
            terminal_tab._append_stream(main, out)
        main.terminal_emulator_output.append(f"[done] exit_code={code}")
    text = str(payload.get("text", "")).strip()
    err = payload.get("error")
    if err:
        main.chat_transcript.append(_format_chat_line("assistant", f"[error]: {err}", is_error=True))
        return
    if not text:
        main.chat_transcript.append(_format_chat_line("assistant", "(empty response)"))
        refresh_chat_goal_view(main)
        return
    main.chat_transcript.append(_format_chat_line("assistant", text))
    main._chat_history.append({"role": "assistant", "content": text})
    main.chat_feedback_helpful_btn.setEnabled(True)
    main.chat_feedback_not_btn.setEnabled(True)
    refresh_chat_goal_view(main)
    activate_pending_controls_from_response(main, text)
    QTimer.singleShot(100, lambda: refresh_chat_goal_view(main))


def on_chat_error(main: MainWindow, error: str) -> None:
    main.chat_transcript.append(_format_chat_line("assistant", f"[exception]: {error}", is_error=True))
    refresh_chat_goal_view(main)


def activate_pending_controls_from_response(main: MainWindow, text: str) -> None:
    raw = str(text or "")
    if not response_requests_confirmation(raw):
        main._pending_plan_fallback_active = False
        return
    token = extract_pending_token_from_text(raw)
    if not token:
        main._pending_plan_fallback_active = False
        return
    main._pending_plan_token = token
    main._pending_plan_fallback_active = True
    main.chat_apply_btn.setEnabled(True)
    main.chat_reject_btn.setEnabled(True)
    main.chat_pending_label.setText(f"Pending plan: token={token}")
    main.chat_transcript.append(
        _format_chat_line("assistant", "Доступны действия: [Apply] или [Reject] кнопками ниже.")
    )


def extract_pending_token_from_text(text: str) -> str:
    m = re.search(r"token:([a-fA-F0-9]{8,32})", str(text or ""))
    if not m:
        return ""
    return str(m.group(1))


def response_requests_confirmation(text: str) -> bool:
    lowered = str(text or "").lower()
    return "применяй token:" in lowered


def on_chat_finished(main: MainWindow) -> None:
    main.chat_send_btn.setEnabled(True)
    main.status_label.setText("State: idle")
    if main._chat_worker is not None:
        main._chat_worker.deleteLater()
        main._chat_worker = None


def clear_chat_session(main: MainWindow) -> None:
    main._chat_history.clear()
    main.chat_transcript.clear()
    main.chat_feedback_helpful_btn.setEnabled(False)
    main.chat_feedback_not_btn.setEnabled(False)
    refresh_chat_goal_view(main)


def submit_chat_feedback(main: MainWindow, *, helpful: bool) -> None:
    """Save feedback for last user+assistant exchange (ROADMAP 3.6.8 Phase 3)."""
    history = getattr(main, "_chat_history", []) or []
    if len(history) < 2:
        return
    user_msg = ""
    assistant_msg = ""
    for i in range(len(history) - 1, -1, -1):
        role = (history[i].get("role") or "").strip()
        content = (history[i].get("content") or "").strip()
        if role == "assistant" and not assistant_msg:
            assistant_msg = content
        elif role == "user" and not user_msg:
            user_msg = content
        if user_msg and assistant_msg:
            break
    if not user_msg or not assistant_msg:
        return
    clarification: str | None = None
    if not helpful:
        text, ok = QInputDialog.getText(
            main,
            "Уточнение",
            "Что имели в виду? (необязательно):",
            text="",
        )
        if ok and text:
            clarification = text.strip()
    main._api.save_chat_feedback(
        user_message=user_msg,
        assistant_message=assistant_msg,
        helpful=helpful,
        clarification=clarification,
    )
    main.chat_feedback_helpful_btn.setEnabled(False)
    main.chat_feedback_not_btn.setEnabled(False)
