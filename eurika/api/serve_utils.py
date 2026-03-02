"""HTTP server utilities: JSON response, body parsing, project root resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from http.server import BaseHTTPRequestHandler


def json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def read_json_body(handler: BaseHTTPRequestHandler) -> dict | None:
    """Read and parse JSON body from POST request."""
    try:
        length = int(handler.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return None
        body = handler.rfile.read(length)
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def resolve_project_root_override(
    default_root: Path,
    raw_value: object,
) -> tuple[Path | None, str | None]:
    """Resolve optional project_root override from query/body payload."""
    if raw_value is None:
        return default_root, None
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else None
        if raw_value is None:
            return default_root, None
    if not isinstance(raw_value, str):
        return None, "invalid project_root payload (expected string)"
    raw = raw_value.strip()
    if not raw:
        return default_root, None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (default_root / p)
    try:
        resolved = p.resolve()
    except OSError as e:
        return None, f"invalid project_root: {e}"
    if not resolved.exists() or not resolved.is_dir():
        return None, f"project_root not found or not a directory: {resolved}"
    return resolved, None


def parse_bool_flag(value: object) -> bool | None:
    """Parse bool-like request payload value; return None for invalid input."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        return None
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None
