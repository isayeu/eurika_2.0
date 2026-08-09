"""Versioned JSON-RPC contracts for the local Eurika agent backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "1.0"

ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_CANCELLED = -32800
ERR_TIMEOUT = -32801
ERR_APPROVAL_REQUIRED = -32001
ERR_WORKSPACE_VIOLATION = -32002
ERR_TOOL_FAILED = -32003


@dataclass(slots=True)
class RpcError(Exception):
    """Error that can be serialized as a JSON-RPC error response."""

    code: int
    message: str
    data: Any = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, error: RpcError) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error.as_dict()}


def event_notification(
    *,
    event: str,
    session_id: str | None,
    request_id: Any,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "event": event,
        "requestId": request_id,
        "data": data or {},
    }
    if session_id is not None:
        params["sessionId"] = session_id
    return {"jsonrpc": JSONRPC_VERSION, "method": "agent/event", "params": params}


def validate_request(value: Any) -> tuple[Any, str, dict[str, Any]]:
    if not isinstance(value, dict) or value.get("jsonrpc") != JSONRPC_VERSION:
        raise RpcError(ERR_INVALID_REQUEST, "Expected a JSON-RPC 2.0 object")
    method = value.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(ERR_INVALID_REQUEST, "Request method must be a non-empty string")
    params = value.get("params", {})
    if not isinstance(params, dict):
        raise RpcError(ERR_INVALID_PARAMS, "Request params must be an object")
    return value.get("id"), method, params
