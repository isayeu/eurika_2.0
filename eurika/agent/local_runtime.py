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

from .contracts import RPC_METHOD_CONTRACTS, TOOL_CONTRACTS
from .history import SessionHistory
from .protocol import (
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    ERR_TOOL_FAILED,
    PROTOCOL_VERSION,
    RpcError,
)
from .proposals import ProposalStore
from .panels import PanelService
from .workspace import WorkspaceTools, _search_source_kind

RuntimeEmitter = Callable[[str, str | None, dict[str, Any]], None]
_CITED_RELATIVE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|cjs|json|md))"
)


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


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
        if method == "initialize":
            # Protocol handshake: version negotiation, then capabilities().
            requested = params.get("protocolVersion")
            if requested is not None and requested != PROTOCOL_VERSION:
                raise RpcError(
                    ERR_INVALID_PARAMS,
                    f"Unsupported protocol version: {requested}",
                    {"supported": [PROTOCOL_VERSION]},
                )
            result = self.capabilities()
            client = params.get("client")
            if client is not None:
                if not isinstance(client, dict):
                    raise RpcError(ERR_INVALID_PARAMS, "client must be an object")
                manifest = client.get("manifest")
                if manifest is not None and not isinstance(manifest, dict):
                    raise RpcError(ERR_INVALID_PARAMS, "client.manifest must be an object")
                result["clientAdapter"] = manifest or {
                    "id": str(client.get("name") or "unknown"),
                    "name": str(client.get("name") or "unknown"),
                    "version": str(client.get("version") or ""),
                    "capabilities": params.get("capabilities") or {},
                }
            return result
        if method == "session/create":
            metadata = params.get("metadata", {})
            if not isinstance(metadata, dict):
                raise RpcError(ERR_INVALID_PARAMS, "metadata must be an object")
            session = LocalSession(
                id=str(uuid.uuid4()),
                metadata=dict(metadata),
                messages=self.history.load(),
            )
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
        if method == "session/history":
            limit = params.get("limit", 80)
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise RpcError(ERR_INVALID_PARAMS, "limit must be a non-negative integer")
            return {"messages": self.history.load(limit)}
        if method == "session/clear":
            self.history.clear()
            with self._lock:
                for active_session in self._sessions.values():
                    active_session.messages.clear()
            return {"cleared": True}
        if method == "workspace/list":
            supplied = params.get("path")
            scope = self.tools.resolve(str(supplied or "."), must_exist=True)
            if not scope.is_dir():
                raise RpcError(ERR_INVALID_PARAMS, "workspace/list path must name a directory")
            files = [
                path.relative_to(self.workspace_root).as_posix()
                for path in self.tools._search_files(scope)
                if path.is_file()
            ]
            return {"files": sorted(files)[:5000], "truncated": len(files) > 5000}
        if method == "tool/call":
            return self._call_tool(params, cancel=cancel, emit=emit)
        if method == "agent/run":
            return self._run_calls(params, cancel=cancel, emit=emit)
        if method == "proposal/prepare":
            return self.proposals.prepare(params)
        if method == "proposal/get":
            return self.proposals.get(params.get("proposalId"), params.get("path"))
        if method == "proposal/apply":
            return self.proposals.apply(params, cancel=cancel)
        if method == "proposal/reject":
            return self.proposals.reject(params)
        if method == "checkpoint/list":
            return self.proposals.list_checkpoints()
        if method == "checkpoint/restore":
            return self.proposals.restore(params, cancel=cancel)
        if method == "panel/state":
            return self.panels.state(params.get("panel"))
        if method == "approval/preview":
            return self.panels.approval_preview(params)
        if method == "approval/save":
            return self.panels.approval_save(params)
        if method == "command/run":
            return self.panels.command_run(
                params,
                cancel=cancel,
                emit=lambda event, data: emit(event, None, data),
            )
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
                session = LocalSession(
                    id=str(uuid.uuid4()),
                    metadata={"client": "chat"},
                    messages=self.history.load(),
                )
                with self._lock:
                    self._sessions[session.id] = session
        context = params.get("context", {})
        if not isinstance(context, dict):
            raise RpcError(ERR_INVALID_PARAMS, "context must be an object")
        if tool_results is None:
            assert isinstance(message, str)
            user_message = message.strip()
            session.messages.append({"role": "user", "content": user_message})
            self.history.append("user", user_message)
        emit("message_start", session.id, {})

        started = time.monotonic()
        calls_before = session.tool_calls
        tool_errors = 0
        observations: list[dict[str, Any]] = list(tool_results or [])
        pending_calls: list[dict[str, Any]] = []
        text = ""
        notice = ""
        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            self.tools._check_cancel(cancel)
            prompt = self._chat_prompt(session, context, observations)
            raw, error = self._call_model(prompt)
            if error:
                text = self._format_model_failure(error)
                break
            body, found = self._split_model_notice(raw)
            if found:
                notice = found
            parsed = self._parse_model_response(body)
            if parsed.get("type") == "final":
                text = self._accept_grounded_final(
                    str(parsed.get("text") or "").strip(),
                    observations,
                )
                if text:
                    break
                continue
            calls = parsed.get("toolCalls")
            if not isinstance(calls, list) or not calls:
                text = self._accept_grounded_final(str(parsed.get("text") or body or "").strip(), observations)
                if text:
                    break
                continue
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
                    if name == "edit":
                        normalized["proposal"] = self.proposals.prepare(arguments)
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
        if not text and not pending_calls:
            self.tools._check_cancel(cancel)
            raw, error = self._call_model(
                self._chat_prompt(session, context, observations, force_final=True)
            )
            if error:
                text = self._format_model_failure(error)
            else:
                body, found = self._split_model_notice(raw)
                if found:
                    notice = found
                parsed = self._parse_model_response(body)
                candidate = ""
                if parsed.get("type") == "final":
                    candidate = str(parsed.get("text") or "").strip()
                elif not parsed.get("toolCalls"):
                    candidate = str(parsed.get("text") or body or "").strip()
                text = self._accept_grounded_final(candidate, observations)
                if not text:
                    text = self._grounded_fallback(observations)
        if not text:
            text = "I could not complete the request within the local tool-loop limit."
        text = self._with_notice(text, notice)
        if not pending_calls:
            session.messages.append({"role": "assistant", "content": text})
            self.history.append("assistant", text)
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
    def _cited_relative_paths(text: str) -> list[str]:
        return [_normalize_rel(path) for path in _CITED_RELATIVE_PATH.findall(text or "")]

    @staticmethod
    def _observed_paths(observations: list[dict[str, Any]]) -> set[str]:
        paths: set[str] = set()

        def add(value: Any) -> None:
            if isinstance(value, str) and value.strip() and not Path(value).is_absolute():
                paths.add(_normalize_rel(value))

        for item in observations:
            if not isinstance(item, dict):
                continue
            add(item.get("path"))
            payload = item.get("result")
            if isinstance(payload, dict):
                add(payload.get("path"))
                for match in payload.get("matches") or []:
                    if isinstance(match, dict):
                        add(match.get("path"))
        return paths

    def _ungrounded_cited_paths(self, text: str, observations: list[dict[str, Any]]) -> list[str]:
        observed = self._observed_paths(observations)
        bad: list[str] = []
        for path in self._cited_relative_paths(text):
            if path not in observed:
                bad.append(path)
        return bad

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
        bad = self._ungrounded_cited_paths(candidate, observations)
        if not bad:
            tests_only = self._non_implementation_citations(candidate)
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
                "observed": sorted(self._observed_paths(observations)),
            }
        )
        return ""

    def _non_implementation_citations(self, text: str) -> list[str]:
        cited = self._cited_relative_paths(text)
        if not cited:
            return []
        impl = [path for path in cited if _search_source_kind(path) == "implementation"]
        other = [path for path in cited if _search_source_kind(path) != "implementation"]
        return other if other and not impl else []

    def _grounded_fallback(self, observations: list[dict[str, Any]]) -> str:
        observed = sorted(self._observed_paths(observations))
        impl = [path for path in observed if _search_source_kind(path) == "implementation"]
        if impl:
            return "From tool observations: " + ", ".join(impl[:8]) + "."
        tests = [path for path in observed if _search_source_kind(path) == "test"]
        if tests:
            return (
                "Tests are not the implementation. "
                f"Observed test files: {', '.join(tests[:5])}. "
                "Search and read the production module they import (eurika/)."
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

        text, error = call_llm_with_prompt(prompt, max_tokens=2048)
        if error:
            return text or "", humanize_llm_error(error)
        return text or "", None

    @staticmethod
    def _split_model_notice(raw: str) -> tuple[str, str]:
        value = raw or ""
        match = re.search(r"\n+\s*—\s*\n(Лимит[\s\S]+)\Z", value)
        if not match:
            return value, ""
        return value[: match.start()].rstrip(), match.group(1).strip()

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
        try:
            loaded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            start_obj = (value or "").find("{")
            start_arr = (value or "").find("[")
            starts = [item for item in (start_obj, start_arr) if item >= 0]
            if not starts:
                return None
            try:
                loaded, _end = json.JSONDecoder().raw_decode(value, min(starts))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        return loaded if isinstance(loaded, (dict, list)) else None

    @staticmethod
    def _loads_json_object(value: str) -> dict[str, Any] | None:
        loaded = LocalAgentRuntime._loads_json_value(value)
        return loaded if isinstance(loaded, dict) else None

    @staticmethod
    def _coerce_tool_call(obj: Any) -> dict[str, Any] | None:
        if not isinstance(obj, dict):
            return None
        fn = obj.get("function") if isinstance(obj.get("function"), dict) else {}
        name = obj.get("tool") or obj.get("name") or fn.get("name")
        arguments = obj.get("arguments")
        if arguments is None:
            arguments = obj.get("args") or obj.get("parameters") or fn.get("arguments") or fn.get("parameters")
        if not isinstance(name, str) or name not in TOOL_CONTRACTS:
            return None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return None
        call: dict[str, Any] = {"tool": name, "arguments": arguments}
        call_id = obj.get("callId") or obj.get("id")
        if call_id:
            call["callId"] = str(call_id)
        return call

    @staticmethod
    def _extract_tool_calls(parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            if parsed.get("type") == "final":
                return []
            raw = parsed.get("toolCalls") or parsed.get("tool_calls") or parsed.get("tools")
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items = [raw]
            else:
                one = LocalAgentRuntime._coerce_tool_call(parsed)
                return [one] if one else []
        else:
            return []
        calls: list[dict[str, Any]] = []
        for item in items:
            call = LocalAgentRuntime._coerce_tool_call(item)
            if call:
                calls.append(call)
        return calls

    @staticmethod
    def _unwrap_json_payload(value: str) -> str:
        text = (value or "").strip()
        fence = re.search(r"```(?:json)?\s*([\{\[][\s\S]*?[\}\]])\s*```", text, flags=re.IGNORECASE)
        if fence:
            return fence.group(1)
        opened = re.match(r"```(?:json)?\s*", text, flags=re.IGNORECASE)
        if opened:
            text = text[opened.end() :]
            text = re.sub(r"\s*```\s*$", "", text)
        return text.strip()

    @staticmethod
    def _parse_model_response(raw: str) -> dict[str, Any]:
        body, _notice = LocalAgentRuntime._split_model_notice(raw or "")
        value = LocalAgentRuntime._unwrap_json_payload(body)
        parsed = LocalAgentRuntime._loads_json_value(value)
        if parsed is None and value != body.strip():
            parsed = LocalAgentRuntime._loads_json_value(body)
        if parsed is None:
            return {"type": "final", "text": body.strip() or (raw or "")}
        calls = LocalAgentRuntime._extract_tool_calls(parsed)
        if calls:
            return {"type": "tool_calls", "toolCalls": calls}
        if isinstance(parsed, dict):
            if parsed.get("type") == "final":
                return parsed
            text = parsed.get("text")
            if isinstance(text, str) and text.strip():
                return {"type": "final", "text": text.strip()}
        return {"type": "final", "text": body.strip() or (raw or "")}

    @staticmethod
    def _chat_prompt(
        session: LocalSession,
        context: dict[str, Any],
        observations: list[dict[str, Any]],
        *,
        force_final: bool = False,
    ) -> str:
        tools = {
            name: {
                "description": str(contract["description"])[:120],
                "requiresApproval": contract["requiresApproval"],
                "required": list((contract.get("inputSchema") or {}).get("required") or []),
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

        closing = (
            "LAST TURN. Do not emit toolCalls. Reply with JSON only: "
            '{"type":"final","text":"answer"} using TOOL_OBSERVATIONS. '
            "Cite only workspace paths that appear in TOOL_OBSERVATIONS. "
            "If a guessed path was missing, name the real files you read. "
            if force_final
            else (
                "Prefer one search then targeted reads. As soon as observations "
                "answer the question, emit type:final and stop calling tools. "
                'Reply with JSON only: {"type":"tool_calls","toolCalls":'
                '[{"tool":"read","arguments":{...}}]} or '
                '{"type":"final","text":"answer"}. '
            )
        )
        return (
            "You are Eurika, a local coding agent. Use only the structured tools below. "
            "Never emit shell fences or claim a tool ran without an observation. "
            "Never invent a workspace path. If a read fails because the file does not "
            "exist, call search and read a real match. "
            "When asked where something is implemented, cite production source "
            "(eurika/ or the matching package), not tests/ or docs/. Tests only "
            "verify; if search hits a test first, read the production module it "
            "imports. "
            + closing
            + "When the user asks to create, change, fix, or implement workspace code, "
            "use the edit tool and return the proposal for approval; do not answer with "
            "only a description of the requested code. "
            "For claims about the current paper Market, PnL, positions, or learning, "
            "call market_status first and assess profitability from the verdict / net "
            "PnL / mean edge, not accuracy alone. Never call a losing paper book "
            "'неплохо' or 'good' just because accuracy > 0.5. Never cite command "
            "output unless a terminal tool observation is present. "
            "Use read-only tools to gather evidence. Side-effecting tools are presented "
            "to the user for approval and are never executed automatically.\n"
            f"CONVERSATION={bounded(session.messages[-8:], 12_000)}\n"
            f"EDITOR_CONTEXT={bounded(context, 40_000)}\n"
            f"TOOL_OBSERVATIONS={bounded(observations, 40_000)}\n"
            f"TOOLS={bounded(tools, 8_000)}"
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
