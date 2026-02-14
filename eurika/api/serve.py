"""Minimal HTTP server for JSON API (ROADMAP §2.3). Stdlib only."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from eurika.api import get_summary, get_history, get_diff


def _json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _run_handler(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    query: dict,
) -> None:
    if path == "/api/summary":
        data = get_summary(project_root)
        _json_response(handler, data)
        return
    if path == "/api/history":
        window = int(query.get("window", [5])[0])
        data = get_history(project_root, window=window)
        _json_response(handler, data)
        return
    if path == "/" or path == "/api":
        _json_response(
            handler,
            {
                "eurika": "JSON API",
                "endpoints": [
                    "GET /api/summary — architecture summary (project root)",
                    "GET /api/history?window=5 — evolution history",
                    "GET /api/diff?old=path/to/old.json&new=path/to/new.json — diff two self_maps",
                ],
            },
        )
        return
    if path == "/api/diff":
        old_q = query.get("old", [])
        new_q = query.get("new", [])
        if not old_q or not new_q:
            _json_response(
                handler,
                {"error": "query params 'old' and 'new' (paths to self_map.json) required"},
                status=400,
            )
            return
        old_path = project_root / old_q[0] if not Path(old_q[0]).is_absolute() else Path(old_q[0])
        new_path = project_root / new_q[0] if not Path(new_q[0]).is_absolute() else Path(new_q[0])
        data = get_diff(old_path, new_path)
        _json_response(handler, data)
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
            _run_handler(self, root, path, query)

        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet by default; override to enable logging

    server = HTTPServer((host, port), APIHandler)
    print(f"Eurika JSON API: http://{host}:{port}/api/summary  /api/history  /api/diff?old=...&new=...")
    print(f"Project root: {root}")
    server.serve_forever()
