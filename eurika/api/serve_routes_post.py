"""POST /api/* route handlers."""
from __future__ import annotations
from pathlib import Path
from eurika.api import preview_operation, save_approvals
from . import serve as _serve
from .serve_exec import EXEC_TIMEOUT_MAX, EXEC_TIMEOUT_MIN, exec_eurika_command

def dispatch_api_post(handler, project_root: Path, path: str, body: dict | None) -> bool:
    """Handle POST requests. Returns True if handled."""
    if path == '/api/operation_preview':
        if not body or 'operation' not in body:
            _serve._json_response(handler, {'error': "JSON body with 'operation' object required"}, status=400)
            return True
        op = body.get('operation')
        if not isinstance(op, dict):
            _serve._json_response(handler, {'error': 'operation must be object'}, status=400)
            return True
        _serve._json_response(handler, preview_operation(project_root, op))
        return True
    if path == '/api/approve':
        if not body or 'operations' not in body:
            _serve._json_response(handler, {'error': "JSON body with 'operations' array required"}, status=400)
            return True
        ops = body.get('operations')
        if not isinstance(ops, list) or any((not isinstance(op, dict) for op in ops)):
            _serve._json_response(handler, {'error': 'invalid operations payload', 'hint': 'Expected operations: list[object]'}, status=400)
            return True
        data = save_approvals(project_root, body['operations'])
        _serve._json_response(handler, data)
        return True
    if path == '/api/exec':
        if not body or 'command' not in body:
            _serve._json_response(handler, {'error': 'JSON body with \'command\' required (e.g. {"command": "eurika scan ."})'}, status=400)
            return True
        command = body.get('command')
        if not isinstance(command, str):
            _serve._json_response(handler, {'error': 'invalid command payload', 'hint': 'Expected command: string'}, status=400)
            return True
        raw_timeout = body.get('timeout', 120)
        timeout = _compute_timeout(raw_timeout)
        if timeout is None:
            _serve._json_response(handler, {'error': 'invalid timeout payload', 'hint': 'Expected timeout: integer or null'}, status=400)
            return True
        _serve._json_response(handler, exec_eurika_command(project_root, command, timeout))
        return True
    return False

def _compute_timeout(raw_timeout):
    if raw_timeout is None:
        return None
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return None
    if timeout < EXEC_TIMEOUT_MIN or timeout > EXEC_TIMEOUT_MAX:
        return None
    return timeout