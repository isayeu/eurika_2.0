"""Qt Chat HITL for dialog_state pending_plan / pending_git_commit."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from ..main_window import MainWindow


def _pending_preview_fingerprint(
    pending_plan: dict[str, Any] | None,
    pending_git: dict[str, Any] | None,
) -> str:
    """Stable id for the current HITL pending item (plan or git commit)."""
    if isinstance(pending_plan, dict) and pending_plan:
        token = str(pending_plan.get("token") or "").strip()
        if token:
            return f"plan:{token}"
        intent = str(pending_plan.get("intent") or "").strip()
        target = str(pending_plan.get("target") or "").strip()
        return f"plan:{intent}:{target}"
    if isinstance(pending_git, dict) and pending_git.get("message"):
        token = str(pending_git.get("token") or "").strip()
        if token:
            return f"git:{token}"
        return f"git:{str(pending_git.get('message') or '')[:64]}"
    return ""


def _sync_pending_diff_gate(main: MainWindow, fingerprint: str) -> None:
    """Reset Diff-seen flag when pending fingerprint changes."""
    prev = str(getattr(main, "_pending_diff_gate_fp", "") or "")
    if fingerprint != prev:
        main._pending_diff_gate_fp = fingerprint
        main._pending_diff_seen_fp = ""
    if not fingerprint:
        main._pending_diff_gate_fp = ""
        main._pending_diff_seen_fp = ""


def _mark_pending_diff_seen(main: MainWindow, fingerprint: str) -> None:
    if fingerprint:
        main._pending_diff_seen_fp = fingerprint


def _pending_diff_was_seen(main: MainWindow, fingerprint: str) -> bool:
    return bool(fingerprint) and str(getattr(main, "_pending_diff_seen_fp", "") or "") == fingerprint


def _apply_allowed_for_pending(
    main: MainWindow,
    *,
    has_effective_pending: bool,
    previewable: bool,
    fingerprint: str,
) -> bool:
    """Apply only after Diff preview for this pending (fallback without preview stays allowed)."""
    if not has_effective_pending:
        return False
    if not previewable:
        return True
    return _pending_diff_was_seen(main, fingerprint)


def refresh_chat_goal_view(main: MainWindow) -> None:
    from eurika.api.chat_context import format_agent_context_panel
    from eurika.api.task_executor import is_pending_plan_valid
    from . import agent_hitl_handlers

    if agent_hitl_handlers.paint_pending(main):
        return

    state = main._api.get_chat_dialog_state()
    state_dict: dict[str, Any] = state if isinstance(state, dict) else {}
    raw_pending_plan = state_dict.get("pending_plan")
    pending_plan: dict[str, Any] = (
        raw_pending_plan if isinstance(raw_pending_plan, dict) else {}
    )
    plan_valid = bool(pending_plan) and is_pending_plan_valid(pending_plan)
    plan_stale = bool(pending_plan) and not plan_valid
    if plan_valid:
        main._pending_plan_token = str(pending_plan.get("token") or "")
    main.chat_goal_view.setPlainText(
        format_agent_context_panel(
            state_dict, plan_valid=plan_valid, plan_stale=plan_stale
        )
    )
    raw_pending_git = state_dict.get("pending_git_commit")
    pending_git = raw_pending_git if isinstance(raw_pending_git, dict) else None
    has_pending_plan = plan_valid
    has_pending_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    has_effective_pending = has_pending_plan or has_pending_git or main._pending_plan_fallback_active
    can_preview = bool(pending_plan) or has_pending_git
    gate_plan = pending_plan if bool(pending_plan) else None
    gate_git = pending_git if has_pending_git and not bool(pending_plan) else None
    fingerprint = _pending_preview_fingerprint(gate_plan, gate_git)
    _sync_pending_diff_gate(main, fingerprint)
    if hasattr(main, "chat_diff_btn"):
        main.chat_diff_btn.setEnabled(can_preview)
    if can_preview:
        preview_pending_chat_plan(main)
    elif hasattr(main, "chat_diff_view"):
        main.chat_diff_view.clear()
    allow_apply = (not plan_stale) and _apply_allowed_for_pending(
        main,
        has_effective_pending=has_effective_pending,
        previewable=can_preview and not plan_stale,
        fingerprint=fingerprint,
    )
    main.chat_apply_btn.setEnabled(allow_apply)
    main.chat_reject_btn.setEnabled(has_effective_pending or plan_stale)
    if has_pending_plan:
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
            main.chat_reject_btn.setToolTip(tooltip)
        else:
            main.chat_pending_label.setToolTip("")
            main.chat_reject_btn.setToolTip("")
        if allow_apply:
            main.chat_apply_btn.setToolTip("Apply pending plan (Diff уже просмотрен)")
        else:
            main.chat_apply_btn.setToolTip("Сначала Diff — Apply откроется после preview")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить unified diff pending-плана")
    elif plan_stale:
        pending_intent = str(pending_plan.get("intent") or "-")
        main.chat_pending_label.setText(f"Pending plan: expired ({pending_intent})")
        main.chat_pending_label.setToolTip("Plan TTL expired — Reject to clear.")
        main.chat_apply_btn.setToolTip("Cannot apply: plan expired")
        main.chat_reject_btn.setToolTip("Clear expired pending plan")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить diff expired плана (только просмотр)")
    elif has_pending_git and isinstance(pending_git, dict):
        main._pending_plan_token = str(pending_git.get("token") or "")
        msg_preview = str(pending_git.get("message", ""))[:50]
        main.chat_pending_label.setText(f"Pending git commit: {msg_preview}...")
        main.chat_pending_label.setToolTip(f"Commit message: {pending_git.get('message', '-')}")
        if allow_apply:
            main.chat_apply_btn.setToolTip("Apply git commit (preview уже просмотрен)")
        else:
            main.chat_apply_btn.setToolTip("Сначала Diff — Apply откроется после preview")
        main.chat_reject_btn.setToolTip("Reject git commit")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить preview pending git commit")
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
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setEnabled(False)
            main.chat_diff_btn.setToolTip("Diff недоступен до синхронизации dialog_state")
    else:
        main._pending_plan_token = ""
        main.chat_pending_label.setText("Pending plan: none")
        main.chat_pending_label.setToolTip("")
        main.chat_apply_btn.setToolTip("")
        main.chat_reject_btn.setToolTip("")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Нет pending-плана для Diff")


def apply_pending_chat_plan(main: MainWindow) -> None:
    from . import agent_hitl_handlers, chat_handlers

    if getattr(main, "_agent_pending_call", None):
        agent_hitl_handlers.apply_pending(main)
        return
    state = main._api.get_chat_dialog_state()
    state_dict: dict[str, Any] = state if isinstance(state, dict) else {}
    raw_plan = state_dict.get("pending_plan")
    pending_plan = raw_plan if isinstance(raw_plan, dict) else {}
    raw_git = state_dict.get("pending_git_commit")
    pending_git = raw_git if isinstance(raw_git, dict) else None
    has_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    previewable = bool(pending_plan) or has_git
    gate_git = pending_git if has_git and not bool(pending_plan) else None
    fingerprint = _pending_preview_fingerprint(
        pending_plan if pending_plan else None, gate_git
    )
    if previewable and not _pending_diff_was_seen(main, fingerprint):
        preview_pending_chat_plan(main)
        if not _pending_diff_was_seen(main, fingerprint):
            QMessageBox.information(
                main,
                "Chat",
                "Сначала посмотри Diff в панели Контекст, затем Apply.",
            )
            return
    token = main._pending_plan_token.strip()
    msg = f"применяй token:{token}" if token else "применяй"
    main._pending_plan_fallback_active = False
    chat_handlers.dispatch_chat_message(main, msg)


def reject_pending_chat_plan(main: MainWindow) -> None:
    from . import agent_hitl_handlers, chat_handlers

    if getattr(main, "_agent_pending_call", None):
        agent_hitl_handlers.reject_pending(main)
        return
    main._pending_plan_fallback_active = False
    main._pending_diff_seen_fp = ""
    main._pending_diff_gate_fp = ""
    chat_handlers.dispatch_chat_message(main, "отклонить")


def preview_pending_chat_plan(main: MainWindow) -> None:
    """Show unified diff / summary for chat pending_plan in the Agent context panel."""
    from . import agent_hitl_handlers

    if getattr(main, "_agent_pending_call", None):
        agent_hitl_handlers.paint_pending(main)
        return
    if not hasattr(main, "chat_diff_view"):
        return
    state = main._api.get_chat_dialog_state()
    pending_plan = state.get("pending_plan") if isinstance(state, dict) else None
    pending_git = state.get("pending_git_commit") if isinstance(state, dict) else None
    has_plan = isinstance(pending_plan, dict) and bool(pending_plan)
    has_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    gate_git = pending_git if has_git and not has_plan else None
    fingerprint = _pending_preview_fingerprint(
        pending_plan if has_plan else None, gate_git
    )
    if isinstance(pending_git, dict) and pending_git.get("message") and not has_plan:
        msg = str(pending_git.get("message") or "")
        token = str(pending_git.get("token") or "")
        main.chat_diff_view.setPlainText(
            f"Pending git commit\ntoken={token or '-'}\n\n{msg}"
        )
        _mark_pending_diff_seen(main, fingerprint)
        if fingerprint and (
            main._pending_plan_fallback_active
            or has_git
            or bool(getattr(main, "_pending_plan_token", ""))
        ):
            main.chat_apply_btn.setEnabled(True)
            main.chat_apply_btn.setToolTip("Apply git commit (preview уже просмотрен)")
        return
    try:
        result = main._api.preview_chat_pending_plan(
            pending_plan if isinstance(pending_plan, dict) else None
        )
    except Exception as exc:
        main.chat_diff_view.setPlainText(f"Preview error: {exc}")
        _mark_pending_diff_seen(main, fingerprint)
        return
    if not isinstance(result, dict):
        main.chat_diff_view.setPlainText("Preview error: empty result")
        _mark_pending_diff_seen(main, fingerprint)
        return
    header_bits = [
        f"intent={result.get('intent') or '-'}",
        f"target={result.get('target') or '-'}",
    ]
    if result.get("expired"):
        header_bits.append("expired=yes")
    if result.get("token"):
        header_bits.append(f"token={result.get('token')}")
    body = str(result.get("unified_diff") or result.get("summary") or "").strip()
    err = result.get("error")
    parts = [" | ".join(header_bits)]
    if err:
        parts.append(f"error: {err}")
    if body:
        parts.append("")
        parts.append(body)
    elif not err:
        parts.append("(no diff)")
    main.chat_diff_view.setPlainText("\n".join(parts))
    _mark_pending_diff_seen(main, fingerprint)
    from eurika.api.task_executor import is_pending_plan_valid

    plan_ok = has_plan and is_pending_plan_valid(pending_plan)  # type: ignore[arg-type]
    if plan_ok or has_git:
        main.chat_apply_btn.setEnabled(True)
        main.chat_apply_btn.setToolTip("Apply pending (Diff уже просмотрен)")


def activate_pending_controls_from_response(main: MainWindow, text: str) -> None:
    from . import chat_handlers

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
    main.chat_reject_btn.setEnabled(True)
    main.chat_pending_label.setText(f"Pending plan: token={token}")
    refresh_chat_goal_view(main)
    chat_handlers._append_transcript(
        main,
        chat_handlers._format_chat_line(
            main,
            "assistant",
            "Доступны действия: [Reject] сразу; [Apply] после Diff в панели Контекст.",
        ),
    )


def extract_pending_token_from_text(text: str) -> str:
    match = re.search(r"token:([a-fA-F0-9]{8,32})", str(text or ""))
    if not match:
        return ""
    return str(match.group(1))


def response_requests_confirmation(text: str) -> bool:
    lowered = str(text or "").lower()
    return "применяй token:" in lowered
