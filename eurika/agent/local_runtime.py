"""Unified session runtime for CLI, IDE, Qt, and HTTP adapters."""

from __future__ import annotations

import threading
import uuid
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .contracts import TOOL_CONTRACTS
from .protocol import (
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    RpcError,
)
from .workspace import WorkspaceTools

RuntimeEmitter = Callable[[str, str | None, dict[str, Any]], None]


@dataclass(slots=True)
class LocalSession:
    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)


class LocalAgentRuntime:
    """Transport-neutral dispatcher for structured local agent operations."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.tools = WorkspaceTools(workspace_root)
        self._sessions: dict[str, LocalSession] = {}
        self._lock = threading.RLock()

    @property
    def workspace_root(self) -> Path:
        return self.tools.root

    def capabilities(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "server": {"name": "eurika-local-agent", "version": "1"},
            "transport": {"name": "jsonrpc-stdio", "framing": "newline-delimited-json"},
            "features": {
                "sessions": True,
                "streamingEvents": True,
                "cancellation": True,
                "requestTimeouts": True,
                "structuredToolCalls": True,
                "chat": True,
            },
            "methods": [
                "initialize",
                "session/create",
                "session/close",
                "session/chat",
                "tool/call",
                "agent/run",
                "$/cancelRequest",
            ],
            "tools": TOOL_CONTRACTS,
            "models": [{"id": "auto", "label": "Auto"}],
            "workspaceRoot": str(self.workspace_root),
        }

    def _session(self, session_id: Any) -> LocalSession:
        if not isinstance(session_id, str) or not session_id:
            raise RpcError(ERR_INVALID_PARAMS, "sessionId must be a non-empty string")
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise RpcError(ERR_INVALID_PARAMS, f"Unknown session: {session_id}")
        return session

    def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: RuntimeEmitter,
    ) -> Any:
        if method == "initialize":
            requested = params.get("protocolVersion")
            if requested is not None and requested != PROTOCOL_VERSION:
                raise RpcError(
                    ERR_INVALID_PARAMS,
                    f"Unsupported protocol version: {requested}",
                    {"supported": [PROTOCOL_VERSION]},
                )
            return self.capabilities()
        if method == "session/create":
            metadata = params.get("metadata", {})
            if not isinstance(metadata, dict):
                raise RpcError(ERR_INVALID_PARAMS, "metadata must be an object")
            session = LocalSession(id=str(uuid.uuid4()), metadata=dict(metadata))
            with self._lock:
                self._sessions[session.id] = session
            return {"sessionId": session.id}
        if method == "session/close":
            session = self._session(params.get("sessionId"))
            with self._lock:
                self._sessions.pop(session.id, None)
            return {"sessionId": session.id, "closed": True}
        if method == "session/chat":
            return self._chat(params, cancel=cancel, emit=emit)
        if method == "tool/call":
            return self._call_tool(params, cancel=cancel, emit=emit)
        if method == "agent/run":
            return self._run_calls(params, cancel=cancel, emit=emit)
        raise RpcError(ERR_METHOD_NOT_FOUND, f"Method not found: {method}")

    def _chat(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: RuntimeEmitter,
    ) -> dict[str, Any]:
        message = params.get("message")
        tool_results = params.get("toolResults")
        session_id = params.get("sessionId")
        if tool_results is not None:
            if not session_id:
                raise RpcError(ERR_INVALID_PARAMS, "sessionId is required with toolResults")
            if not isinstance(tool_results, list):
                raise RpcError(ERR_INVALID_PARAMS, "toolResults must be an array")
            session = self._session(session_id)
        else:
            if not isinstance(message, str) or not message.strip():
                raise RpcError(ERR_INVALID_PARAMS, "message must be a non-empty string")
            if session_id:
                session = self._session(session_id)
            else:
                session = LocalSession(id=str(uuid.uuid4()), metadata={"client": "chat"})
                with self._lock:
                    self._sessions[session.id] = session
        context = params.get("context", {})
        if not isinstance(context, dict):
            raise RpcError(ERR_INVALID_PARAMS, "context must be an object")
        if tool_results is None:
            assert isinstance(message, str)
            session.messages.append({"role": "user", "content": message.strip()})
        emit("message_start", session.id, {})

        started = time.monotonic()
        calls_before = session.tool_calls
        tool_errors = 0
        observations: list[dict[str, Any]] = list(tool_results or [])
        pending_calls: list[dict[str, Any]] = []
        text = ""
        for _ in range(4):
            self.tools._check_cancel(cancel)
            prompt = self._chat_prompt(session, context, observations)
            raw, error = self._call_model(prompt)
            if error:
                raise RpcError(-32004, "Model call failed", {"detail": error})
            parsed = self._parse_model_response(raw)
            if parsed.get("type") == "final":
                text = str(parsed.get("text") or "").strip()
                break
            calls = parsed.get("toolCalls")
            if not isinstance(calls, list) or not calls:
                text = str(raw or "").strip()
                break
            for call in calls[:8]:
                if not isinstance(call, dict):
                    continue
                name = str(call.get("tool") or "")
                arguments = call.get("arguments", {})
                if name not in TOOL_CONTRACTS or not isinstance(arguments, dict):
                    observations.append({"tool": name, "error": "invalid tool call"})
                    continue
                call_id = str(call.get("callId") or uuid.uuid4())
                normalized = {"callId": call_id, "tool": name, "arguments": arguments}
                if TOOL_CONTRACTS[name].get("requiresApproval"):
                    pending_calls.append(normalized)
                    # Preserve plan order: never run or stage later actions before
                    # the user resolves this mutation.
                    break
                try:
                    result = self._call_tool(
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
            if pending_calls:
                text = "Prepared tool action(s) for your review."
                break
        if not text:
            text = "I could not complete the request within the local tool-loop limit."
        if not pending_calls:
            session.messages.append({"role": "assistant", "content": text})
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
            "metrics": {
                "latencyMs": int((time.monotonic() - started) * 1000),
                "toolCalls": session.tool_calls - calls_before,
                "toolCallErrors": tool_errors,
                "contextBytes": len(json.dumps(context, ensure_ascii=False, default=str).encode("utf-8")),
                "verified": verified,
            },
        }

    @staticmethod
    def _call_model(prompt: str) -> tuple[str, str | None]:
        from eurika.reasoning.architect import call_llm_with_prompt

        text, error = call_llm_with_prompt(prompt, max_tokens=2048)
        return text or "", error

    @staticmethod
    def _parse_model_response(raw: str) -> dict[str, Any]:
        value = (raw or "").strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            value = fence.group(1)
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {"type": "final", "text": raw or ""}
        return parsed if isinstance(parsed, dict) else {"type": "final", "text": raw or ""}

    @staticmethod
    def _chat_prompt(
        session: LocalSession,
        context: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> str:
        tools = {
            name: {
                "description": contract["description"],
                "requiresApproval": contract["requiresApproval"],
                "inputSchema": contract["inputSchema"],
            }
            for name, contract in TOOL_CONTRACTS.items()
        }
        def bounded(value: Any, limit: int) -> str:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            if len(encoded) <= limit:
                return encoded
            return json.dumps(
                {"truncated": True, "preview": encoded[:limit]},
                ensure_ascii=False,
            )

        return (
            "You are Eurika, a local coding agent. Use only the structured tools below. "
            "Never emit shell fences or claim a tool ran without an observation. "
            'Reply with JSON only: {"type":"tool_calls","toolCalls":'
            '[{"tool":"read","arguments":{...}}]} or '
            '{"type":"final","text":"answer"}. '
            "Use read-only tools to gather evidence. Side-effecting tools are presented "
            "to the user for approval and are never executed automatically.\n"
            f"CONVERSATION={bounded(session.messages[-12:], 40_000)}\n"
            f"EDITOR_CONTEXT={bounded(context, 220_000)}\n"
            f"TOOL_OBSERVATIONS={bounded(observations, 160_000)}\n"
            f"TOOLS={bounded(tools, 60_000)}"
        )

    def _call_tool(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: RuntimeEmitter,
    ) -> dict[str, Any]:
        session = self._session(params.get("sessionId"))
        name = params.get("tool")
        arguments = params.get("arguments", {})
        call_id = params.get("callId") or str(uuid.uuid4())
        if not isinstance(name, str) or name not in TOOL_CONTRACTS:
            raise RpcError(ERR_INVALID_PARAMS, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise RpcError(ERR_INVALID_PARAMS, "tool arguments must be an object")
        emit("tool/started", session.id, {"callId": call_id, "tool": name, "arguments": arguments})

        def tool_emit(event: str, data: dict[str, Any]) -> None:
            emit(event, session.id, {"callId": call_id, "tool": name, **data})

        try:
            result = self.tools.execute(name, arguments, cancel=cancel, emit=tool_emit)
        except RpcError as exc:
            emit("tool/failed", session.id, {"callId": call_id, "tool": name, "error": exc.as_dict()})
            raise
        with self._lock:
            session.tool_calls += 1
        emit("tool/completed", session.id, {"callId": call_id, "tool": name, "result": result})
        return {"callId": call_id, "tool": name, "result": result}

    def _run_calls(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: RuntimeEmitter,
    ) -> dict[str, Any]:
        session = self._session(params.get("sessionId"))
        calls = params.get("toolCalls", [])
        if not isinstance(calls, list):
            raise RpcError(ERR_INVALID_PARAMS, "toolCalls must be an array")
        outputs: list[dict[str, Any]] = []
        emit("run/started", session.id, {"toolCallCount": len(calls)})
        for index, call in enumerate(calls):
            if not isinstance(call, dict):
                raise RpcError(ERR_INVALID_PARAMS, f"toolCalls[{index}] must be an object")
            call_params = {
                "sessionId": session.id,
                "callId": call.get("callId"),
                "tool": call.get("tool"),
                "arguments": call.get("arguments", {}),
            }
            outputs.append(self._call_tool(call_params, cancel=cancel, emit=emit))
        summary = f"Completed {len(outputs)} structured tool call(s)."
        emit("response/chunk", session.id, {"text": summary})
        emit("run/completed", session.id, {"toolCallCount": len(outputs)})
        return {"sessionId": session.id, "toolResults": outputs, "text": summary}
