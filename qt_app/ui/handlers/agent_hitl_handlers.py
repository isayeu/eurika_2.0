"""Qt Chat HITL for local-agent pendingToolCalls (git commit/push)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from qt_app.ui.agent_pending import (
    approval_button_label,
    approval_details,
    first_pending_hitl_call,
    format_proposal_preview,
)


class AgentDecideWorker(QThread):
    finished_payload = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, api: Any, call: dict[str, Any], approved: bool) -> None:
        super().__init__()
        self._api = api
        self._call = call
        self._approved = approved

    def cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self._call.get("proposal"):
                payload = self._api.agent_decide_proposal(
                    self._call, approved=self._approved
                )
            else:
                payload = self._api.agent_decide_tool(
                    self._call, approved=self._approved
                )
            self.finished_payload.emit(payload)
        except Exception as exc:
            self.failed.emit(str(exc))


def bind_from_payload(main: Any, payload: dict[str, Any] | None) -> None:
    call = first_pending_hitl_call((payload or {}).get("pendingToolCalls"))
    session_id = (payload or {}).get("sessionId")
    if session_id:
        main._agent_session_id = str(session_id)
        if hasattr(main, "_api"):
            main._api._agent_session_id = str(session_id)
    main._agent_pending_call = call
    main._agent_proposal_preview = None
    if call is None and hasattr(main, "chat_apply_btn"):
        main.chat_apply_btn.setText("Apply")


def clear_pending(main: Any) -> None:
    main._agent_pending_call = None
    main._agent_proposal_preview = None
    if hasattr(main, "chat_apply_btn"):
        main.chat_apply_btn.setText("Apply")


def paint_pending(main: Any) -> bool:
    call = getattr(main, "_agent_pending_call", None)
    if not isinstance(call, dict):
        if hasattr(main, "chat_apply_btn"):
            main.chat_apply_btn.setText("Apply")
        return False
    tool = str(call.get("tool") or "")
    label = approval_button_label(tool)
    details = approval_details(call)
    cached = getattr(main, "_agent_proposal_preview", None)
    if isinstance(cached, str) and cached.strip():
        details = cached
    elif tool == "edit" and hasattr(main, "_api"):
        proposal = call.get("proposal") if isinstance(call.get("proposal"), dict) else {}
        proposal_id = str(proposal.get("proposalId") or "")
        if proposal_id:
            try:
                hydrated = main._api.agent_get_proposal(proposal_id)
                files = hydrated.get("files") if isinstance(hydrated, dict) else None
                preview = format_proposal_preview(files or [])
                if preview:
                    details = preview
                    main._agent_proposal_preview = preview
            except (FileNotFoundError, OSError):
                pass
    main.chat_apply_btn.setText(label)
    main.chat_apply_btn.setEnabled(True)
    main.chat_apply_btn.setToolTip(details or f"Approve {tool}")
    main.chat_reject_btn.setEnabled(True)
    main.chat_reject_btn.setToolTip(f"Reject {tool}")
    main.chat_pending_label.setText(f"Pending agent tool: {tool}")
    main.chat_pending_label.setToolTip(details)
    if hasattr(main, "chat_diff_btn"):
        main.chat_diff_btn.setEnabled(bool(details))
        main.chat_diff_btn.setToolTip(
            "Показать diff proposal" if tool == "edit" else "Показать детали git HITL"
        )
    if hasattr(main, "chat_diff_view") and details:
        main.chat_diff_view.setPlainText(details)
    return True


def apply_pending(main: Any) -> None:
    _decide(main, approved=True)


def reject_pending(main: Any) -> None:
    _decide(main, approved=False)


def _decide(main: Any, *, approved: bool) -> None:
    from . import chat_handlers

    call = getattr(main, "_agent_pending_call", None)
    if not isinstance(call, dict):
        return
    if main._chat_worker is not None and main._chat_worker.isRunning():
        return
    chat_handlers._set_chat_busy(main, busy=True)
    worker = AgentDecideWorker(api=main._api, call=call, approved=approved)
    main._chat_worker = worker
    worker.finished_payload.connect(lambda payload: _on_decided(main, payload))
    worker.failed.connect(lambda err: chat_handlers.on_chat_error(main, err))
    worker.finished.connect(lambda: chat_handlers.on_chat_finished(main))
    worker.start()


def _on_decided(main: Any, payload: dict[str, Any]) -> None:
    from . import chat_handlers

    clear_pending(main)
    chat_handlers.on_chat_result(main, payload)
