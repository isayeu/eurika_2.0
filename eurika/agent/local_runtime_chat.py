"""Chat tool-loop for LocalAgentRuntime (extracted for P0.4 file-size)."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any, Callable

from .approvals_bridge import (
    flush_agent_pending_plan,
    try_review_in_approvals_call,
    with_approvals_ready,
)
from .contracts import TOOL_CONTRACTS
from .local_runtime_ground import grounded_fallback
from .protocol import ERR_INVALID_PARAMS, RpcError

RuntimeEmitter = Callable[[str, str | None, dict[str, Any]], None]
_IMPLEMENT_REQUEST = re.compile(
    r"(?is)\b("
    r"implement|create|write|replace|patch|refactor|"
    r"реализуй|исправ(?:ь|ить)|поправ(?:ь|ить)|внеси правк|напиши код|"
    r"добавь тест|"
    r"mypy"
    r")\b"
)
# Layout/ergonomics asks often say «сделай удобнее» without IMPLEMENT/исправь.
_UI_LAYOUT_REQUEST = re.compile(
    r"(?is)("
    r"эргоном|"
    r"переверст|"
    r"(?:вкладк\w*|layout).{0,240}(?:сделай|улучш|компакт|прокрут)|"
    r"(?:сделай|улучш).{0,80}(?:компакт|layout|вкладк)|"
    r"боков\w*\s+панел|"
    r"sidebar|"
    r"сворач\w*.{0,80}(?:панел|кнопк)|"
    r"сверн\w*.{0,80}(?:панел|кнопк)|"
    r"воркспейс|"
    r"воркспес|"
    r"фиксирован|"
    r"поднимается вверх|"
    r"новый\s+чат|"
    r"переимен|"
    r"правой\s+кнопк"
    r")"
)
_IMPLEMENT_NUDGE = "IMPLEMENT_REQUIRED"


def _wants_code_mutation(messages: list[dict[str, str]]) -> bool:
    for item in reversed(messages or []):
        if item.get("role") != "user":
            continue
        text = str(item.get("content") or "")
        return bool(_IMPLEMENT_REQUEST.search(text) or _UI_LAYOUT_REQUEST.search(text))
    return False


def _already_nudged_edit(observations: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(item, dict) and item.get("error") == _IMPLEMENT_NUDGE
        for item in observations
    )


def _observations_have_edit(observations: list[dict[str, Any]]) -> bool:
    for item in observations:
        if not isinstance(item, dict) or item.get("tool") != "edit":
            continue
        if item.get("error") == _IMPLEMENT_NUDGE:
            continue
        return True
    return False


def _nudge_implement() -> dict[str, Any]:
    return {
        "tool": "edit",
        "error": _IMPLEMENT_NUDGE,
        "hint": (
            "Emit tool_calls with tool=edit now. Do not type:final with a plan. "
            "Do not list project files. Do not say toolCalls are forbidden."
        ),
    }


def _should_reject_plan_only_final(
    messages: list[dict[str, str]],
    observations: list[dict[str, Any]],
    pending_calls: list[dict[str, Any]],
    session: Any,
) -> bool:
    return bool(
        _wants_code_mutation(messages)
        and not pending_calls
        and not getattr(session, "staged_after", None)
        and not _observations_have_edit(observations)
    )


def _observation_edit_path(item: dict[str, Any]) -> str | None:
    args = item.get("arguments")
    if isinstance(args, dict):
        path = args.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
        edits = args.get("edits")
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    nested = edit.get("path")
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
    result = item.get("result")
    if isinstance(result, dict):
        outcome = result.get("outcome")
        if isinstance(outcome, dict):
            applied = outcome.get("applied")
            if isinstance(applied, list) and applied:
                first = applied[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
                if isinstance(first, dict):
                    nested = first.get("path")
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
        path = result.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    return None


def _fill_missing_edit_path(
    arguments: dict[str, Any], observations: list[dict[str, Any]]
) -> dict[str, Any]:
    filled = dict(arguments)
    if isinstance(filled.get("path"), str) and filled["path"].strip():
        return filled
    inferred = None
    for item in reversed(observations):
        if isinstance(item, dict):
            inferred = _observation_edit_path(item)
            if inferred:
                break
    if not inferred:
        return filled
    edits = filled.get("edits")
    if isinstance(edits, list) and edits:
        filled["edits"] = [
            {**item, "path": inferred}
            if isinstance(item, dict) and not (isinstance(item.get("path"), str) and item["path"].strip())
            else item
            for item in edits
        ]
        return filled
    filled["path"] = inferred
    return filled


def _dispatch_tool_calls(
    runtime: Any,
    session: Any,
    calls: list[Any],
    *,
    observations: list[dict[str, Any]],
    pending_calls: list[dict[str, Any]],
    review_in_approvals: bool,
    cancel: threading.Event,
    emit: RuntimeEmitter,
) -> int:
    tool_errors = 0
    for call in calls[:8]:
        if not isinstance(call, dict):
            continue
        name = str(call.get("tool") or "")
        arguments = call.get("arguments", {})
        if name not in TOOL_CONTRACTS or not isinstance(arguments, dict):
            observations.append({"tool": name, "error": "invalid tool call"})
            continue
        if name == "edit":
            arguments = _fill_missing_edit_path(arguments, observations)
        call_id = str(call.get("callId") or uuid.uuid4())
        normalized = {"callId": call_id, "tool": name, "arguments": arguments}
        if review_in_approvals and name in {
            "read",
            "edit",
            "git_commit",
            "git_push",
        }:
            try:
                handled = try_review_in_approvals_call(
                    runtime.tools,
                    session,
                    name=name,
                    arguments=arguments,
                    call_id=call_id,
                )
            except RpcError as exc:
                tool_errors += 1
                observations.append(
                    {
                        "callId": call_id,
                        "tool": name,
                        "error": exc.as_dict(),
                        "hint": (
                            "edit.path must be workspace-relative "
                            "(e.g. qt_app/ui/tabs/models_tab.py)."
                        ),
                    }
                )
                continue
            if handled is not None:
                observations.append(handled)
                continue
        if TOOL_CONTRACTS[name].get("requiresApproval"):
            if name == "edit":
                try:
                    normalized["proposal"] = runtime.proposals.prepare(arguments)
                except RpcError as exc:
                    tool_errors += 1
                    observations.append(
                        {
                            "callId": call_id,
                            "tool": name,
                            "error": exc.as_dict(),
                            "hint": (
                                "edit.path must be workspace-relative "
                                "(e.g. qt_app/ui/tabs/models_tab.py)."
                            ),
                        }
                    )
                    continue
            pending_calls.append(normalized)
            break
        try:
            result = runtime._call_tool(
                {
                    "sessionId": session.id,
                    "callId": call_id,
                    "tool": name,
                    "arguments": arguments,
                },
                cancel=cancel,
                emit=emit,
            )
        except RpcError as exc:
            tool_errors += 1
            result = {
                "callId": call_id,
                "tool": name,
                "error": exc.as_dict(),
            }
        observations.append(result)
    return tool_errors


def run_chat(
    runtime: Any,
    params: dict[str, Any],
    *,
    cancel: threading.Event,
    emit: RuntimeEmitter,
) -> dict[str, Any]:
    from .local_runtime import LocalSession

    message = params.get("message")
    tool_results = params.get("toolResults")
    session_id = params.get("sessionId")
    if tool_results is not None:
        if not session_id:
            raise RpcError(ERR_INVALID_PARAMS, "sessionId is required with toolResults")
        if not isinstance(tool_results, list):
            raise RpcError(ERR_INVALID_PARAMS, "toolResults must be an array")
        session = runtime._session(session_id)
    else:
        if not isinstance(message, str) or not message.strip():
            raise RpcError(ERR_INVALID_PARAMS, "message must be a non-empty string")
        if session_id:
            session = runtime._session(session_id)
        else:
            session = LocalSession(
                id=str(uuid.uuid4()),
                metadata={"client": "chat"},
                messages=runtime.history.load(),
            )
            with runtime._lock:
                runtime._sessions[session.id] = session
    context = params.get("context", {})
    if not isinstance(context, dict):
        raise RpcError(ERR_INVALID_PARAMS, "context must be an object")
    if tool_results is None:
        assert isinstance(message, str)
        user_message = message.strip()
        session.messages.append({"role": "user", "content": user_message})
        runtime.history.append("user", user_message)
    emit("message_start", session.id, {})

    started = time.monotonic()
    calls_before = session.tool_calls
    tool_errors = 0
    observations: list[dict[str, Any]] = list(tool_results or [])
    pending_calls: list[dict[str, Any]] = []
    text = ""
    notice = ""
    review_in_approvals = bool(context.get("reviewInApprovals"))
    max_tool_rounds = 8 if review_in_approvals else 5
    if _wants_code_mutation(session.messages):
        max_tool_rounds += 3
    for _ in range(max_tool_rounds):
        runtime.tools._check_cancel(cancel)
        prompt = runtime._chat_prompt(session, context, observations)
        raw, error = runtime._call_model(prompt)
        if error:
            text = runtime._format_model_failure(error)
            break
        body, found = runtime._split_model_notice(raw)
        if found:
            notice = found
        parsed = runtime._parse_model_response(body)
        if parsed.get("type") == "final":
            text = runtime._accept_grounded_final(
                str(parsed.get("text") or "").strip(),
                observations,
            )
            if _should_reject_plan_only_final(
                session.messages, observations, pending_calls, session
            ):
                if not _already_nudged_edit(observations):
                    observations.append(_nudge_implement())
                text = ""
                continue
            if text:
                break
            continue
        calls = parsed.get("toolCalls")
        if not isinstance(calls, list) or not calls:
            text = runtime._accept_grounded_final(
                str(parsed.get("text") or body or "").strip(),
                observations,
            )
            if _should_reject_plan_only_final(
                session.messages, observations, pending_calls, session
            ):
                if not _already_nudged_edit(observations):
                    observations.append(_nudge_implement())
                text = ""
                continue
            if text:
                break
            continue
        errors = _dispatch_tool_calls(
            runtime,
            session,
            calls,
            observations=observations,
            pending_calls=pending_calls,
            review_in_approvals=review_in_approvals,
            cancel=cancel,
            emit=emit,
        )
        tool_errors += errors
        if pending_calls:
            text = "Prepared tool action(s) for your review."
            break
    if not text and not pending_calls:
        runtime.tools._check_cancel(cancel)
        must_edit = _should_reject_plan_only_final(
            session.messages, observations, pending_calls, session
        )
        if must_edit and not _already_nudged_edit(observations):
            observations.append(_nudge_implement())
        raw, error = runtime._call_model(
            runtime._chat_prompt(
                session, context, observations, force_final=not must_edit
            )
        )
        if error:
            text = runtime._format_model_failure(error)
        else:
            body, found = runtime._split_model_notice(raw)
            if found:
                notice = found
            parsed = runtime._parse_model_response(body)
            leftover = parsed.get("toolCalls")
            if must_edit and isinstance(leftover, list) and leftover:
                tool_errors += _dispatch_tool_calls(
                    runtime,
                    session,
                    leftover,
                    observations=observations,
                    pending_calls=pending_calls,
                    review_in_approvals=review_in_approvals,
                    cancel=cancel,
                    emit=emit,
                )
                if pending_calls:
                    text = "Prepared tool action(s) for your review."
            if not text and not pending_calls:
                candidate = ""
                if parsed.get("type") == "final":
                    candidate = str(parsed.get("text") or "").strip()
                elif not leftover:
                    candidate = str(parsed.get("text") or body or "").strip()
                text = runtime._accept_grounded_final(candidate, observations)
                if not text:
                    text = grounded_fallback(observations)
    if not text:
        text = "I could not complete the request within the local tool-loop limit."
    text = runtime._with_notice(text, notice)
    queued = 0
    if review_in_approvals:
        queued = flush_agent_pending_plan(runtime.tools.root, session)
        if queued:
            text = with_approvals_ready(text, queued)
    if not pending_calls:
        session.messages.append({"role": "assistant", "content": text})
        runtime.history.append("assistant", text)
    emit("response/chunk", session.id, {"text": text})
    emit("message_end", session.id, {"text": text, "pendingToolCalls": pending_calls})
    verified = any(
        isinstance(item, dict)
        and (
            (
                item.get("tool") == "tests"
                and isinstance(item.get("result"), dict)
                and item["result"].get("exitCode") == 0
            )
            or (
                item.get("tool") == "diagnostics"
                and isinstance(item.get("result"), dict)
                and not item["result"].get("diagnostics")
            )
        )
        for item in observations
    )
    return {
        "sessionId": session.id,
        "text": text,
        "pendingToolCalls": pending_calls,
        "approvalsQueued": queued,
        "metrics": {
            "latencyMs": int((time.monotonic() - started) * 1000),
            "toolCalls": session.tool_calls - calls_before,
            "toolCallErrors": tool_errors,
            "contextBytes": len(json.dumps(context, ensure_ascii=False, default=str).encode("utf-8")),
            "verified": verified,
        },
    }
