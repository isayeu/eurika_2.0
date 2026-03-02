"""Minimal HTTP server for JSON API (ROADMAP §2.3, 3.5.1, 3.5.8). Stdlib only."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import serve_utils
from .serve_utils import (
    json_response as _json_response,
    read_json_body as _read_json_body,
    resolve_project_root_override as _resolve_project_root_override,
)
from .serve_exec import (
    EXEC_TIMEOUT_MAX,
    EXEC_TIMEOUT_MIN,
    exec_eurika_command as _exec_eurika_command,
    _normalize_exec_args_for_subcommand,
)
from .serve_routes_get import dispatch_api_get as _dispatch_api_get
from .serve_routes_post import dispatch_api_post

# Re-exports for backward compatibility (tests/test_api_serve.py)
_run_post_handler = dispatch_api_post


def _run_handler(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    query: dict,
    body: dict | None = None,
) -> None:
    if _dispatch_api_get(handler, project_root, path, query):
        return
    handler.send_response(404)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps({"error": "not found", "path": path}).encode("utf-8"))


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    project_root: Optional[Path] = None,
) -> None:
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()

    class APIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            selected_root: Path = root
            if path.startswith("/api"):
                resolved, root_err = _resolve_project_root_override(root, query.get("project_root"))
                if root_err or resolved is None:
                    _json_response(self, {"error": root_err or "invalid project_root payload"}, status=400)
                    return
                selected_root = resolved
            _run_handler(self, selected_root, path, query, body=None)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            body = _read_json_body(self)
            selected_root: Path = root
            if path.startswith("/api"):
                resolved, root_err = _resolve_project_root_override(root, (body or {}).get("project_root"))
                if root_err or resolved is None:
                    _json_response(self, {"error": root_err or "invalid project_root payload"}, status=400)
                    return
                selected_root = resolved
            if dispatch_api_post(self, selected_root, path, body):
                return
            json_response(self, {"error": "not found", "path": path}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet by default; override to enable logging

    server = HTTPServer((host, port), APIHandler)
    print(f"Eurika: http://{host}:{port}/api  (JSON API)")
    print(f"Project root: {root}")
    server.serve_forever()
