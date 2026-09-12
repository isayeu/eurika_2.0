"""CR-H2: one Chat entry. Pre-LLM is HITL/evidence/run-now; else one agent runtime."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

AgentChat = Callable[..., dict[str, Any]]
CoreChat = Callable[..., dict[str, Any]]

_FIX_ERRORS_RE = re.compile(
    r"исправ.{0,32}ошиб|поправ.{0,32}ошиб|fix.{0,32}error",
    re.I,
)


def is_pre_llm_turn(message: str) -> bool:
    """HITL, already-ran Terminal review, and run-now rituals.

    Run-now uses detectors that already exist (``прогони release check``).
    That is command execution, not a new domain phrase-book. Dogfood
    2026-09-12: sending the imperative to the agent and hoping for
    ``tool=skill`` produced a lecture and a 600s ``/chat`` timeout.
    """
    from eurika.api.chat_direct import (
        is_apply_confirmation,
        is_git_commit_and_push_request,
        is_git_commit_request,
        is_git_push_request,
        is_os_env_check_request,
        is_read_terminal_request,
        is_reject_confirmation,
        is_release_check_request,
        is_ritual_request,
        is_scan_request,
    )

    text = (message or "").strip()
    if not text:
        return False
    if is_apply_confirmation(text) or is_reject_confirmation(text):
        return True
    if is_read_terminal_request(text):
        return True
    if (
        is_git_commit_and_push_request(text)
        or is_git_commit_request(text)
        or is_git_push_request(text)
    ):
        return True
    return (
        is_release_check_request(text)
        or is_scan_request(text)
        or is_ritual_request(text)
        or is_os_env_check_request(text)
    )


def dispatch_chat_turn(
    root: Path,
    message: str,
    *,
    history: Optional[list] = None,
    client_terminal_text: Optional[str] = None,
    run_command_with_result: Optional[Callable[[str], tuple[str, int]]] = None,
    privilege_prompt: Any = None,
    persist_history: bool = True,
    agent_chat: Optional[AgentChat] = None,
    core_chat: Optional[CoreChat] = None,
) -> dict[str, Any]:
    """Route one user Send: HITL/already-ran/run-now → core; else agent."""
    msg = (message or "").strip()
    if not msg:
        return {"text": "", "error": "message is empty", "ok": False}

    def _as_chat_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"text": str(result or ""), "error": None, "ok": True}
        out = dict(result)
        if "text" not in out:
            out["text"] = ""
        if "error" not in out:
            out["error"] = None if out.get("ok", True) else "chat failed"
        return out

    def _core() -> dict[str, Any]:
        if core_chat is not None:
            return core_chat(
                message=msg,
                history=history,
                client_terminal_text=client_terminal_text,
                run_command_with_result=run_command_with_result,
                privilege_prompt=privilege_prompt,
                persist_history=persist_history,
            )
        from eurika.api.chat import chat_send

        return chat_send(
            Path(root),
            msg,
            history=history,
            run_command_with_result=run_command_with_result,
            privilege_prompt=privilege_prompt,
            client_terminal_text=client_terminal_text,
            persist_history=persist_history,
        )

    try:
        from eurika.api.last_check import try_park_last_check_import_fixes

        if _FIX_ERRORS_RE.search(msg):
            parked = try_park_last_check_import_fixes(Path(root))
            if parked:
                return _as_chat_result(parked)
    except Exception:
        pass

    if agent_chat is not None:
        try:
            from eurika.api.chat_direct import is_short_backlog_request, resolve_direct_handler

            hid, _extra = resolve_direct_handler(Path(root), msg)
            if hid in {"roadmap_next", "continue_dev"} and is_short_backlog_request(msg):
                return _as_chat_result(_core())
        except Exception:
            pass

    if is_pre_llm_turn(msg) or agent_chat is None:
        return _as_chat_result(_core())

    try:
        return _as_chat_result(agent_chat(msg, client_terminal_text=client_terminal_text))
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "text": "",
            "error": (
                "Local agent HTTP недоступен "
                f"({exc}). Запустите Qt/Desktop с gateway "
                "или поднимите agent HTTP; запрос не уходит в обычный chat втихую."
            ),
            "pendingToolCalls": [],
            "approvalsQueued": 0,
        }


def agent_chat_from_runtime(runtime: Any) -> AgentChat:
    """In-process session/chat — no HTTP hop (avoids single-thread deadlock)."""

    def _agent(msg: str, client_terminal_text: Optional[str] = None) -> dict[str, Any]:
        import threading

        ctx: dict[str, Any] = {"client": "http"}
        try:
            from eurika.api.last_check import docs_plan_is_the_task

            if not docs_plan_is_the_task(msg):
                ctx["reviewInApprovals"] = True
        except Exception:
            ctx["reviewInApprovals"] = True
        if client_terminal_text:
            ctx["terminalText"] = client_terminal_text
        return runtime.dispatch(
            "session/chat",
            {"message": msg, "context": ctx},
            cancel=threading.Event(),
            emit=lambda *_a, **_k: None,
        )

    return _agent


def handle_http_chat(
    root: Path,
    message: str,
    *,
    history: Optional[list] = None,
    client_terminal_text: Optional[str] = None,
    persist_history: bool = True,
    agent_runtime: Any = None,
) -> dict[str, Any]:
    """POST /api/chat: same dispatch as Qt Send and Desktop ``chat/send``."""
    agent = agent_chat_from_runtime(agent_runtime) if agent_runtime is not None else None
    return dispatch_chat_turn(
        Path(root),
        message,
        history=history,
        client_terminal_text=client_terminal_text,
        persist_history=persist_history,
        agent_chat=agent,
    )
