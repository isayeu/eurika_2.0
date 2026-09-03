"""RPC method dispatch for LocalAgentRuntime (extracted for P0.4 file-size)."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

from .protocol import (
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    RpcError,
)

RuntimeEmitter = Callable[[str, str | None, dict[str, Any]], None]


def dispatch(
    runtime: Any,
    method: str,
    params: dict[str, Any],
    *,
    cancel: threading.Event,
    emit: RuntimeEmitter,
) -> Any:
    from .local_runtime import LocalSession

    if method == "initialize":
        # Protocol handshake: version negotiation, then capabilities().
        requested = params.get("protocolVersion")
        if requested is not None and requested != PROTOCOL_VERSION:
            raise RpcError(
                ERR_INVALID_PARAMS,
                f"Unsupported protocol version: {requested}",
                {"supported": [PROTOCOL_VERSION]},
            )
        result = runtime.capabilities()
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
            messages=runtime.history.load(),
        )
        with runtime._lock:
            runtime._sessions[session.id] = session
        return {"sessionId": session.id}
    if method == "session/close":
        session = runtime._session(params.get("sessionId"))
        with runtime._lock:
            runtime._sessions.pop(session.id, None)
        return {"sessionId": session.id, "closed": True}
    if method == "session/chat":
        return runtime._with_live_activity(
            method, params, lambda: runtime._chat(params, cancel=cancel, emit=emit)
        )
    if method == "session/history":
        limit = params.get("limit", 80)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise RpcError(ERR_INVALID_PARAMS, "limit must be a non-negative integer")
        return {"messages": runtime.history.load(limit)}
    if method == "session/clear":
        runtime.history.clear()
        with runtime._lock:
            for active_session in runtime._sessions.values():
                active_session.messages.clear()
        return {"cleared": True}
    if method == "workspace/list":
        supplied = params.get("path")
        scope = runtime.tools.resolve(str(supplied or "."), must_exist=True)
        if not scope.is_dir():
            raise RpcError(ERR_INVALID_PARAMS, "workspace/list path must name a directory")
        files = [
            path.relative_to(runtime.workspace_root).as_posix()
            for path in runtime.tools._search_files(scope)
            if path.is_file()
        ]
        return {"files": sorted(files)[:5000], "truncated": len(files) > 5000}
    if method == "tool/call":
        return runtime._with_live_activity(
            method, params, lambda: runtime._call_tool(params, cancel=cancel, emit=emit)
        )
    if method == "agent/run":
        return runtime._with_live_activity(
            method, params, lambda: runtime._run_calls(params, cancel=cancel, emit=emit)
        )
    if method == "proposal/prepare":
        return runtime.proposals.prepare(params)
    if method == "proposal/get":
        return runtime.proposals.get(params.get("proposalId"), params.get("path"))
    if method == "proposal/apply":
        result = runtime._with_live_activity(
            method, params, lambda: runtime.proposals.apply(params, cancel=cancel)
        )
        runtime._record_apply_feedback(params, result)
        return result
    if method == "proposal/reject":
        return runtime._with_live_activity(
            method, params, lambda: runtime.proposals.reject(params)
        )
    if method == "checkpoint/list":
        return runtime.proposals.list_checkpoints()
    if method == "checkpoint/restore":
        return runtime.proposals.restore(params, cancel=cancel)
    if method == "panel/state":
        return runtime.panels.state(params.get("panel"))
    if method == "approval/preview":
        return runtime.panels.approval_preview(params)
    if method == "approval/save":
        return runtime.panels.approval_save(params)
    if method == "command/run":
        return runtime._with_live_activity(
            method,
            params,
            lambda: runtime.panels.command_run(
                params,
                cancel=cancel,
                emit=lambda event, data: emit(event, None, data),
            ),
        )
    if method == "activity/recent":
        from .live_activity import recent as live_recent

        after = params.get("afterOffset", 0)
        if not isinstance(after, int) or isinstance(after, bool) or after < 0:
            raise RpcError(ERR_INVALID_PARAMS, "afterOffset must be a non-negative integer")
        limit = params.get("limit", 80)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise RpcError(ERR_INVALID_PARAMS, "limit must be a non-negative integer")
        return live_recent(runtime.workspace_root, after_offset=after, limit=limit)
    raise RpcError(ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
