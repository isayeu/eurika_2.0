"""POST /api/* route handlers."""

from __future__ import annotations

from pathlib import Path

from eurika.api import preview_operation, save_approvals

from . import serve as _serve
from .serve_exec import EXEC_TIMEOUT_MAX, EXEC_TIMEOUT_MIN, exec_eurika_command


def dispatch_api_post(
    handler,
    project_root: Path,
    path: str,
    body: dict | None,
) -> bool:
    """Handle POST requests. Returns True if handled."""
    if path == "/api/operation_preview":
        if not body or "operation" not in body:
            _serve._json_response(handler, {"error": "JSON body with 'operation' object required"}, status=400)
            return True
        op = body.get("operation")
        if not isinstance(op, dict):
            _serve._json_response(handler, {"error": "operation must be object"}, status=400)
            return True
        _serve._json_response(handler, preview_operation(project_root, op))
        return True
    if path == "/api/approve":
        if not body or "operations" not in body:
            _serve._json_response(handler, {"error": "JSON body with 'operations' array required"}, status=400)
            return True
        ops = body.get("operations")
        if not isinstance(ops, list) or any(not isinstance(op, dict) for op in ops):
            _serve._json_response(handler, {"error": "invalid operations payload", "hint": "Expected operations: list[object]"}, status=400)
            return True
        data = save_approvals(project_root, body["operations"])
        _serve._json_response(handler, data)
        return True
    if path == "/api/exec":
        if not body or "command" not in body:
            _serve._json_response(handler, {"error": "JSON body with 'command' required (e.g. {\"command\": \"eurika scan .\"})"}, status=400)
            return True
        command = body.get("command")
        if not isinstance(command, str):
            _serve._json_response(handler, {"error": "invalid command payload", "hint": "Expected command: string"}, status=400)
            return True
        raw_timeout = body.get("timeout", 120)
        if raw_timeout is None:
            timeout = None
        else:
            try:
                timeout = int(raw_timeout)
            except (TypeError, ValueError):
                _serve._json_response(handler, {"error": "invalid timeout payload", "hint": "Expected timeout: integer or null"}, status=400)
                return True
            if timeout < EXEC_TIMEOUT_MIN or timeout > EXEC_TIMEOUT_MAX:
                _serve._json_response(handler, {
                    "error": "invalid timeout range",
                    "hint": f"Expected timeout: {EXEC_TIMEOUT_MIN}..{EXEC_TIMEOUT_MAX} seconds (or null for unlimited)",
                }, status=400)
                return True
        data = _serve._exec_eurika_command(project_root, command, timeout=timeout)
        _serve._json_response(handler, data)
        return True
    if path == "/api/ask_architect":
        from eurika.orchestration.doctor import run_doctor_cycle
        no_llm_raw = (body or {}).get("no_llm", False)
        no_llm = _serve.serve_utils.parse_bool_flag(no_llm_raw)
        if no_llm is None:
            _serve._json_response(handler, {"error": "invalid no_llm payload", "hint": "Expected no_llm: boolean"}, status=400)
            return True
        doctor_data = run_doctor_cycle(project_root, window=5, no_llm=no_llm)
        if doctor_data.get("error"):
            _serve._json_response(handler, {"error": doctor_data["error"], "text": ""})
            return True
        text = doctor_data.get("architect_text") or ""
        _serve._json_response(handler, {"text": text})
        return True
    if path == "/api/chat":
        if not body or "message" not in body:
            _serve._json_response(handler, {"error": "JSON body with 'message' required"}, status=400)
            return True
        msg = body.get("message")
        if not isinstance(msg, str):
            _serve._json_response(handler, {"error": "invalid message payload", "hint": "Expected message: string"}, status=400)
            return True
        raw_history = body.get("history")
        history: list[dict[str, str]] | None = None
        if raw_history is not None:
            if not isinstance(raw_history, list):
                _serve._json_response(handler, {"error": "invalid history payload", "hint": "Expected history: list[object]"}, status=400)
                return True
            normalized: list[dict[str, str]] = []
            for item in raw_history:
                if not isinstance(item, dict):
                    _serve._json_response(handler, {"error": "invalid history payload", "hint": "Expected history: list[object]"}, status=400)
                    return True
                role = item.get("role", "user")
                content = item.get("content", "")
                if not isinstance(role, str) or not isinstance(content, str):
                    _serve._json_response(handler, {"error": "invalid history payload", "hint": "Expected role/content: string"}, status=400)
                    return True
                normalized.append({"role": role, "content": content})
            history = normalized
        from eurika.api.chat import chat_send

        data = chat_send(project_root, msg, history=history)
        _serve._json_response(handler, {"text": data.get("text", ""), "error": data.get("error")})
        return True
    return False
