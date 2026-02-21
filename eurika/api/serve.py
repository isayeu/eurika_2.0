"""Minimal HTTP server for JSON API (ROADMAP §2.3, 3.5.1, 3.5.8) and static UI (3.5.2). Stdlib only."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from eurika.api import get_diff, get_graph, get_history, get_operational_metrics, get_patch_plan, get_pending_plan, get_summary, explain_module, save_approvals
from eurika.api.chat import chat_send

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
MIME_TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".ico": "image/x-icon"}

# Whitelist for POST /api/exec (ROADMAP 3.5.8): only eurika subcommands.
EXEC_WHITELIST = {"scan", "doctor", "fix", "cycle", "explain", "report-snapshot"}


def _json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _serve_static(handler: BaseHTTPRequestHandler, file_path: Path) -> bool:
    """Serve static file; return True if served."""
    if not file_path.is_file():
        return False
    suffix = file_path.suffix.lower()
    ctype = MIME_TYPES.get(suffix, "application/octet-stream")
    try:
        body = file_path.read_bytes()
    except OSError:
        return False
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict | None:
    """Read and parse JSON body from POST request."""
    try:
        length = int(handler.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return None
        body = handler.rfile.read(length)
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def _exec_eurika_command(project_root: Path, command: str, timeout: int = 120) -> dict:
    """Execute a whitelisted eurika command in project_root. ROADMAP 3.5.8."""
    cmd_str = (command or "").strip()
    if not cmd_str:
        return {"error": "command required", "stdout": "", "stderr": "", "exit_code": -1}
    parts = shlex.split(cmd_str)
    if not parts:
        return {"error": "empty command", "stdout": "", "stderr": "", "exit_code": -1}
    subcmd = parts[0].lower()
    if subcmd == "eurika" and len(parts) > 1:
        subcmd = parts[1].lower()
        args = parts[2:]
    else:
        args = parts[1:] if len(parts) > 1 else []
    if subcmd not in EXEC_WHITELIST:
        return {
            "error": f"command not allowed: '{subcmd}'. Allowed: {', '.join(sorted(EXEC_WHITELIST))}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    # Always run in project_root (serve is bound to one project)
    path_str = str(project_root)
    flags = [a for a in args if a.startswith("-")]
    args = [path_str] + flags
    full_args = [sys.executable, "-m", "eurika_cli", subcmd] + args
    try:
        r = subprocess.run(
            full_args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "exit_code": r.returncode,
            "command": " ".join(full_args),
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "stdout": "", "stderr": "Command timed out", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "stdout": "", "stderr": str(e), "exit_code": -1}


def _try_serve_static_or_ui(
    handler: BaseHTTPRequestHandler,
    path: str,
) -> bool:
    """Serve UI or static files. Returns True if served (caller should return)."""
    if path.startswith("/api") or path == "/api":
        return False
    if path in ("/", "/index.html", "/ui", "/ui/"):
        return _serve_static(handler, UI_DIR / "index.html")
    seg = path.lstrip("/")
    if seg and ".." not in seg and _serve_static(handler, UI_DIR / seg):
        return True
    handler.send_response(404)
    handler.send_header("Content-Type", "text/plain")
    handler.end_headers()
    handler.wfile.write(b"Not found")
    return True


def _dispatch_api_get(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    query: dict,
) -> bool:
    """Dispatch GET /api/* routes. Returns True if handled."""
    if path == "/api/summary":
        _json_response(handler, get_summary(project_root))
        return True
    if path == "/api/history":
        window = int(query.get("window", [5])[0])
        _json_response(handler, get_history(project_root, window=window))
        return True
    if path.rstrip("/") == "/api":
        _json_response(handler, {
            "eurika": "JSON API",
            "endpoints": [
                "GET /api/summary — architecture summary (project root)",
                "GET /api/history?window=5 — evolution history",
                "GET /api/diff?old=path/to/old.json&new=path/to/new.json — diff two self_maps",
                "GET /api/doctor?window=5&no_llm=0 — full report + architect (ROADMAP 3.5.1)",
                "GET /api/patch_plan?window=5 — planned operations",
                "GET /api/explain?module=...&window=5 — module role and risks",
                "GET /api/graph — dependency graph (nodes=modules, edges=imports)",
                "GET /api/operational_metrics?window=10 — apply-rate, rollback-rate, median verify time",
                "GET /api/pending_plan — team-mode plan for approve UI (ROADMAP 3.5.6)",
                "GET /api/file?path=... — read file content (for diff preview)",
                "POST /api/approve — save approve/reject decisions to pending_plan.json",
                "POST /api/exec — run whitelisted eurika command (scan, doctor, fix, cycle, ...)",
                "POST /api/ask_architect — architect interpretation (returns architect_text from doctor)",
                "POST /api/chat — chat with Eurika (message → LLM via Eurika layer; logs to .eurika/chat_history/)",
            ],
        })
        return True
    if path == "/api/diff":
        old_q, new_q = query.get("old", []), query.get("new", [])
        if not old_q or not new_q:
            _json_response(handler, {"error": "query params 'old' and 'new' (paths to self_map.json) required"}, status=400)
            return True
        old_path = project_root / old_q[0] if not Path(old_q[0]).is_absolute() else Path(old_q[0])
        new_path = project_root / new_q[0] if not Path(new_q[0]).is_absolute() else Path(new_q[0])
        _json_response(handler, get_diff(old_path, new_path))
        return True
    if path == "/api/doctor":
        window = int(query.get("window", [5])[0])
        no_llm = query.get("no_llm", ["0"])[0].lower() in ("1", "true", "yes")
        from cli.orchestration.doctor import run_doctor_cycle
        _json_response(handler, run_doctor_cycle(project_root, window=window, no_llm=no_llm))
        return True
    if path == "/api/patch_plan":
        window = int(query.get("window", [5])[0])
        plan = get_patch_plan(project_root, window=window)
        _json_response(handler, plan if plan else {"error": "patch plan not available", "hint": "run eurika scan first"})
        return True
    if path == "/api/graph":
        _json_response(handler, get_graph(project_root))
        return True
    if path == "/api/operational_metrics":
        window = int(query.get("window", [10])[0])
        _json_response(handler, get_operational_metrics(project_root, window=window))
        return True
    if path == "/api/pending_plan":
        _json_response(handler, get_pending_plan(project_root))
        return True
    if path == "/api/file":
        file_q = query.get("path", [])
        if not file_q:
            _json_response(handler, {"error": "query param 'path' required (e.g. ?path=cli/handlers.py)"}, status=400)
            return True
        rel = file_q[0]
        if ".." in rel or rel.startswith("/"):
            _json_response(handler, {"error": "invalid path"}, status=400)
            return True
        fpath = (project_root / rel).resolve()
        if not str(fpath).startswith(str(project_root.resolve())):
            _json_response(handler, {"error": "path outside project"}, status=400)
            return True
        try:
            if not fpath.is_file():
                _json_response(handler, {"error": "not a file or not found"}, status=404)
                return True
            content = fpath.read_text(encoding="utf-8", errors="replace")
            _json_response(handler, {"path": rel, "content": content})
        except OSError as e:
            _json_response(handler, {"error": str(e)}, status=500)
        return True
    if path == "/api/explain":
        module_q = query.get("module", [])
        if not module_q:
            _json_response(handler, {"error": "query param 'module' required (e.g. ?module=cli/handlers.py)"}, status=400)
            return True
        window = int(query.get("window", [5])[0])
        text, err = explain_module(project_root, module_q[0], window=window)
        _json_response(handler, {"text": text, "module": module_q[0]} if not err else {"error": err, "text": text})
        return True
    return False


def _run_handler(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    query: dict,
    body: dict | None = None,
) -> None:
    if _try_serve_static_or_ui(handler, path):
        return
    if _dispatch_api_get(handler, project_root, path, query):
        return
    handler.send_response(404)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps({"error": "not found", "path": path}).encode("utf-8"))


def _run_post_handler(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    body: dict | None,
) -> bool:
    """Handle POST requests. Returns True if handled."""
    if path == "/api/approve":
        if not body or "operations" not in body:
            _json_response(
                handler,
                {"error": "JSON body with 'operations' array required"},
                status=400,
            )
            return True
        data = save_approvals(project_root, body["operations"])
        _json_response(handler, data)
        return True
    if path == "/api/exec":
        if not body or "command" not in body:
            _json_response(
                handler,
                {"error": "JSON body with 'command' required (e.g. {\"command\": \"eurika scan .\"})"},
                status=400,
            )
            return True
        timeout = int(body.get("timeout", 120))
        data = _exec_eurika_command(project_root, body["command"], timeout=timeout)
        _json_response(handler, data)
        return True
    if path == "/api/ask_architect":
        from cli.orchestration.doctor import run_doctor_cycle
        no_llm = (body or {}).get("no_llm", False)
        doctor_data = run_doctor_cycle(project_root, window=5, no_llm=no_llm)
        if doctor_data.get("error"):
            _json_response(handler, {"error": doctor_data["error"], "text": ""})
            return True
        text = doctor_data.get("architect_text") or ""
        _json_response(handler, {"text": text})
        return True
    if path == "/api/chat":
        msg = (body or {}).get("message", "")
        history = (body or {}).get("history")
        if not isinstance(history, list):
            history = None
        data = chat_send(project_root, msg, history=history)
        _json_response(handler, {"text": data.get("text", ""), "error": data.get("error")})
        return True
    return False


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
            _run_handler(self, root, path, query, body=None)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            body = _read_json_body(self)
            if _run_post_handler(self, root, path, body):
                return
            _json_response(
                self,
                {"error": "not found", "path": path},
                status=404,
            )

        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet by default; override to enable logging

    server = HTTPServer((host, port), APIHandler)
    print(f"Eurika: http://{host}:{port}/  (UI)  http://{host}:{port}/api  (JSON API)")
    print(f"Project root: {root}")
    server.serve_forever()




# TODO (eurika): refactor long_function '_dispatch_api_get' — consider extracting helper
