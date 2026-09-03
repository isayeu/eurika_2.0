"""Unified session runtime for CLI, IDE, Qt, and HTTP adapters."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .contracts import RPC_METHOD_CONTRACTS, TOOL_CONTRACTS
from .history import SessionHistory
from .protocol import (
    ERR_INVALID_PARAMS,
    ERR_TOOL_FAILED,
    PROTOCOL_VERSION,
    RpcError,
)
from .proposals import ProposalStore
from .panels import PanelService
from .local_runtime_ground import (
    non_implementation_citations,
    observed_paths,
    ungrounded_cited_paths,
)
from .workspace import WorkspaceTools

RuntimeEmitter = Callable[[str, str | None, dict[str, Any]], None]


@dataclass(slots=True)
class LocalSession:
    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    staged_before: dict[str, bytes | None] = field(default_factory=dict)
    staged_after: dict[str, bytes | None] = field(default_factory=dict)


class LocalAgentRuntime:
    """Transport-neutral dispatcher for structured local agent operations."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.tools = WorkspaceTools(workspace_root)
        self.proposals = ProposalStore(self.tools)
        self.panels = PanelService(self.tools)
        self.history = SessionHistory(self.tools.root)
        self._sessions: dict[str, LocalSession] = {}
        self._lock = threading.RLock()

    @property
    def workspace_root(self) -> Path:
        return self.tools.root

    def capabilities(self) -> dict[str, Any]:
        """Return the protocol handshake payload advertised by ``initialize``."""
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
                "persistentSessionHistory": True,
                "editProposals": True,
                "checkpoints": True,
                "productPanels": True,
            },
            "methods": [
                "initialize",
                "session/create",
                "session/close",
                "session/chat",
                "session/history",
                "session/clear",
                "workspace/list",
                "tool/call",
                "agent/run",
                "proposal/prepare",
                "proposal/get",
                "proposal/apply",
                "proposal/reject",
                "checkpoint/list",
                "checkpoint/restore",
                "panel/state",
                "approval/preview",
                "approval/save",
                "command/run",
                "activity/recent",
                "$/cancelRequest",
            ],
            "tools": TOOL_CONTRACTS,
            "methodContracts": RPC_METHOD_CONTRACTS,
            "models": [{"id": "auto", "label": "Auto"}],
            "adapterContract": {
                "version": 1,
                "capabilities": [
                    "editorContext",
                    "terminal",
                    "notifications",
                    "approvals",
                    "panels",
                ],
            },
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
        from .local_runtime_dispatch import dispatch as dispatch_rpc

        return dispatch_rpc(self, method, params, cancel=cancel, emit=emit)

    def _record_apply_feedback(self, params: dict[str, Any], result: dict[str, Any]) -> None:
        """Save positive feedback when a proposal is applied (self-improvement loop)."""
        try:
            applied = result.get("applied") or []
            if not applied:
                return
            session_id = params.get("sessionId")
            session = self._sessions.get(session_id) if session_id else None
            user_msg = ""
            if session:
                for m in reversed(session.messages):
                    if m.get("role") == "user":
                        user_msg = str(m.get("content") or "")
                        break
            from eurika.api.chat import save_chat_feedback
            save_chat_feedback(
                self.workspace_root,
                user_message=user_msg[:500] or f"[agent-chat apply: {', '.join(applied)}]",
                assistant_message=f"Applied edit to: {', '.join(applied)}",
                helpful=True,
                clarification="auto: proposal/apply succeeded",
            )
        except Exception:
            pass

    def _with_live_activity(self, method: str, params: dict[str, Any], fn):
        from .live_activity import publish_done, publish_start, should_mirror_rpc

        if not should_mirror_rpc(method):
            return fn()
        started = publish_start(self.workspace_root, method, params, client="agent")
        try:
            result = fn()
        except Exception as exc:
            publish_done(self.workspace_root, started, ok=False, error=str(exc))
            raise
        publish_done(self.workspace_root, started, ok=True, result=result)
        return result

    def _chat(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: RuntimeEmitter,
    ) -> dict[str, Any]:
        from .local_runtime_chat import run_chat

        return run_chat(self, params, cancel=cancel, emit=emit)


    def _accept_grounded_final(self, text: str, observations: list[dict[str, Any]]) -> str:
        candidate = (text or "").strip()
        if not candidate:
            return ""
        parsed = self._parse_model_response(candidate)
        if parsed.get("toolCalls"):
            return ""
        inner = str(parsed.get("text") or "").strip()
        if parsed.get("type") == "final" and inner and inner != candidate:
            candidate = inner
        bad = ungrounded_cited_paths(candidate, observations)
        if not bad:
            tests_only = non_implementation_citations(candidate)
            if tests_only:
                observations.append(
                    {
                        "error": "tests/ and docs/ are not the implementation",
                        "paths": tests_only,
                        "hint": "Cite a production file from TOOL_OBSERVATIONS (eurika/). Search initialize/capabilities if needed.",
                    }
                )
                return ""
            return candidate
        observations.append(
            {
                "error": "cited paths were not in tool observations",
                "paths": bad,
                "observed": sorted(observed_paths(observations)),
            }
        )
        return ""

    @staticmethod
    def _format_model_failure(error: str) -> str:
        reason = (error or "").strip() or "unknown model error"
        if reason.startswith("Лимит"):
            return reason
        return f"Модель не ответила.\n{reason}"

    @staticmethod
    def _call_model(prompt: str) -> tuple[str, str | None]:
        from eurika.reasoning.architect import call_llm_with_prompt, humanize_llm_error
        from eurika.utils.env import apply_qt_chat_routing

        apply_qt_chat_routing()
        text, error = call_llm_with_prompt(prompt, max_tokens=2048)
        if error:
            return text or "", humanize_llm_error(error)
        return text or "", None

    @staticmethod
    def _split_model_notice(raw: str) -> tuple[str, str]:
        from .local_runtime_parse import split_model_notice

        return split_model_notice(raw)

    @staticmethod
    def _with_notice(text: str, notice: str) -> str:
        body = (text or "").rstrip()
        if not notice or not body:
            return body
        if "Лимит " in body:
            return body
        return f"{body}\n\n—\n{notice}"

    @staticmethod
    def _loads_json_value(value: str) -> Any:
        from .local_runtime_parse import loads_json_value

        return loads_json_value(value)

    @staticmethod
    def _loads_json_object(value: str) -> dict[str, Any] | None:
        from .local_runtime_parse import loads_json_object

        return loads_json_object(value)

    @staticmethod
    def _coerce_tool_call(obj: Any) -> dict[str, Any] | None:
        from .local_runtime_parse import coerce_tool_call

        return coerce_tool_call(obj)

    @staticmethod
    def _extract_tool_calls(parsed: Any) -> list[dict[str, Any]]:
        from .local_runtime_parse import extract_tool_calls

        return extract_tool_calls(parsed)

    @staticmethod
    def _unwrap_json_payload(value: str) -> str:
        from .local_runtime_parse import unwrap_json_payload

        return unwrap_json_payload(value)

    @staticmethod
    def _parse_model_response(raw: str) -> dict[str, Any]:
        from .local_runtime_parse import parse_model_response

        return parse_model_response(raw)

    @staticmethod
    def _chat_prompt(
        session: LocalSession,
        context: dict[str, Any],
        observations: list[dict[str, Any]],
        *,
        force_final: bool = False,
    ) -> str:
        from .local_runtime_prompt import chat_prompt

        return chat_prompt(session.messages, context, observations, force_final=force_final)

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
        except OSError as exc:
            error = RpcError(ERR_TOOL_FAILED, f"{type(exc).__name__}: {exc}")
            emit("tool/failed", session.id, {"callId": call_id, "tool": name, "error": error.as_dict()})
            raise error from exc
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
