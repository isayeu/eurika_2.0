"""POST /api/* route handlers."""
from __future__ import annotations

from pathlib import Path

from eurika.api import preview_operation, save_approvals

from .serve_exec import EXEC_TIMEOUT_MAX, EXEC_TIMEOUT_MIN, exec_eurika_command
from .serve_utils import emit_route_json as _json_response

def dispatch_api_post(handler, project_root: Path, path: str, body: dict | None) -> bool:
    """Handle POST requests. Returns True if handled."""
    if path == '/api/operation_preview':
        if not body or 'operation' not in body:
            _json_response(handler, {'error': "JSON body with 'operation' object required"}, status=400)
            return True
        op = body.get('operation')
        if not isinstance(op, dict):
            _json_response(handler, {'error': 'operation must be object'}, status=400)
            return True
        _json_response(handler, preview_operation(project_root, op))
        return True
    if path == '/api/approve':
        if not body or 'operations' not in body:
            _json_response(handler, {'error': "JSON body with 'operations' array required"}, status=400)
            return True
        ops = body.get('operations')
        if not isinstance(ops, list) or any((not isinstance(op, dict) for op in ops)):
            _json_response(handler, {'error': 'invalid operations payload', 'hint': 'Expected operations: list[object]'}, status=400)
            return True
        data = save_approvals(project_root, body['operations'])
        _json_response(handler, data)
        return True
    if path == '/api/exec':
        if not body or 'command' not in body:
            _json_response(handler, {'error': 'JSON body with \'command\' required (e.g. {"command": "eurika scan ."})'}, status=400)
            return True
        command = body.get('command')
        if not isinstance(command, str):
            _json_response(handler, {'error': 'invalid command payload', 'hint': 'Expected command: string'}, status=400)
            return True
        if 'timeout' not in body:
            timeout = 120
        elif body.get('timeout') is None:
            timeout = None
        else:
            raw_timeout = body.get('timeout')
            timeout, err = _compute_timeout(raw_timeout)
            if err:
                _json_response(handler, {'error': err, 'hint': 'Expected timeout: integer, null, or 1..3600'}, status=400)
                return True
        _json_response(handler, exec_eurika_command(project_root, command, timeout))
        return True
    if path == '/api/chat':
        if not body or 'message' not in body:
            _json_response(handler, {'error': "JSON body with 'message' required"}, status=400)
            return True
        message = body.get('message')
        if not isinstance(message, str):
            _json_response(handler, {'error': 'invalid message payload', 'hint': 'Expected message: string'}, status=400)
            return True
        history = body.get('history')
        if history is not None:
            if not isinstance(history, list):
                _json_response(handler, {'error': 'invalid history payload', 'hint': 'Expected history: list of {role, content}'}, status=400)
                return True
            for i, item in enumerate(history):
                if not isinstance(item, dict):
                    _json_response(handler, {'error': 'invalid history payload', 'hint': 'history items must be objects'}, status=400)
                    return True
                role = item.get('role')
                content = item.get('content')
                if not isinstance(role, str):
                    _json_response(handler, {'error': 'invalid history payload', 'hint': 'history item role must be string'}, status=400)
                    return True
                if content is not None and not isinstance(content, str):
                    _json_response(handler, {'error': 'invalid history payload', 'hint': 'history item content must be string'}, status=400)
                    return True
        from eurika.api.chat import chat_send
        result = chat_send(project_root, message, history=history)
        _json_response(handler, result)
        return True
    if path == '/api/ask_architect':
        no_llm_raw = body.get('no_llm') if body else None
        no_llm = _parse_no_llm(no_llm_raw)
        if no_llm is None:
            _json_response(handler, {'error': 'invalid no_llm payload', 'hint': 'Expected no_llm: boolean or "yes"/"true"/"1"'}, status=400)
            return True
        from eurika.orchestration.doctor import run_doctor_cycle
        out = run_doctor_cycle(project_root, window=5, no_llm=no_llm)
        text = out.get('architect_text', '') if isinstance(out, dict) else ''
        _json_response(handler, {'text': text})
        return True
    return False


def _parse_no_llm(raw: object) -> bool | None:
    """Parse no_llm to bool. Returns None if invalid."""
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in ('1', 'true', 'yes')
    return None

def _compute_timeout(raw_timeout) -> tuple[int | None, str | None]:
    """Return (timeout_value, error) — error is None if valid."""
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return None, "invalid timeout payload"
    if timeout < EXEC_TIMEOUT_MIN or timeout > EXEC_TIMEOUT_MAX:
        return None, "invalid timeout range"
    return timeout, None