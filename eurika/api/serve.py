"""Minimal HTTP server for JSON API (ROADMAP §2.3, 3.5.1, 3.5.8). Stdlib only."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from eurika.api import (
    get_diff,
    get_graph,
    get_history,
    get_operational_metrics,
    get_patch_plan,
    get_pending_plan,
    get_risk_prediction,
    get_self_guard,
    get_smells_with_plugins,
    get_summary,
    explain_module,
    preview_operation,
    save_approvals,
)
from eurika.api.chat import chat_send

# Whitelist for POST /api/exec (ROADMAP 3.5.8): only eurika subcommands.
EXEC_WHITELIST = {"scan", "doctor", "fix", "cycle", "explain", "report-snapshot", "learning-kpi"}
EXEC_TIMEOUT_MIN = 1
EXEC_TIMEOUT_MAX = 3600
_FLAG_TAKES_VALUE = 1
_FLAG_IS_BOOL = 0
EXEC_ALLOWED_FLAGS: dict[str, dict[str, int]] = {
    "scan": {
        "--format": _FLAG_TAKES_VALUE,
        "-f": _FLAG_TAKES_VALUE,
        "--color": _FLAG_IS_BOOL,
        "--no-color": _FLAG_IS_BOOL,
    },
    "doctor": {
        "--window": _FLAG_TAKES_VALUE,
        "--no-llm": _FLAG_IS_BOOL,
        "--online": _FLAG_IS_BOOL,
        "--runtime-mode": _FLAG_TAKES_VALUE,
    },
    "fix": {
        "--window": _FLAG_TAKES_VALUE,
        "--dry-run": _FLAG_IS_BOOL,
        "--quiet": _FLAG_IS_BOOL,
        "-q": _FLAG_IS_BOOL,
        "--no-clean-imports": _FLAG_IS_BOOL,
        "--no-code-smells": _FLAG_IS_BOOL,
        "--verify-cmd": _FLAG_TAKES_VALUE,
        "--verify-timeout": _FLAG_TAKES_VALUE,
        "--interval": _FLAG_TAKES_VALUE,
        "--runtime-mode": _FLAG_TAKES_VALUE,
        "--non-interactive": _FLAG_IS_BOOL,
        "--session-id": _FLAG_TAKES_VALUE,
        "--allow-campaign-retry": _FLAG_IS_BOOL,
        "--allow-low-risk-campaign": _FLAG_IS_BOOL,
        "--online": _FLAG_IS_BOOL,
        "--apply-suggested-policy": _FLAG_IS_BOOL,
        "--team-mode": _FLAG_IS_BOOL,
        "--apply-approved": _FLAG_IS_BOOL,
        "--approve-ops": _FLAG_TAKES_VALUE,
        "--reject-ops": _FLAG_TAKES_VALUE,
    },
    "cycle": {
        "--window": _FLAG_TAKES_VALUE,
        "--dry-run": _FLAG_IS_BOOL,
        "--quiet": _FLAG_IS_BOOL,
        "-q": _FLAG_IS_BOOL,
        "--no-llm": _FLAG_IS_BOOL,
        "--no-clean-imports": _FLAG_IS_BOOL,
        "--no-code-smells": _FLAG_IS_BOOL,
        "--verify-cmd": _FLAG_TAKES_VALUE,
        "--verify-timeout": _FLAG_TAKES_VALUE,
        "--interval": _FLAG_TAKES_VALUE,
        "--runtime-mode": _FLAG_TAKES_VALUE,
        "--non-interactive": _FLAG_IS_BOOL,
        "--session-id": _FLAG_TAKES_VALUE,
        "--allow-campaign-retry": _FLAG_IS_BOOL,
        "--allow-low-risk-campaign": _FLAG_IS_BOOL,
        "--online": _FLAG_IS_BOOL,
        "--apply-suggested-policy": _FLAG_IS_BOOL,
        "--team-mode": _FLAG_IS_BOOL,
        "--apply-approved": _FLAG_IS_BOOL,
        "--approve-ops": _FLAG_TAKES_VALUE,
        "--reject-ops": _FLAG_TAKES_VALUE,
    },
    "explain": {
        "--window": _FLAG_TAKES_VALUE,
    },
    "report-snapshot": {},
    "learning-kpi": {"--json": _FLAG_IS_BOOL, "--top-n": _FLAG_TAKES_VALUE},
}


def _normalize_exec_args_for_subcommand(
    project_root: Path,
    subcmd: str,
    raw_args: list[str],
) -> tuple[list[str] | None, str | None]:
    """Validate/normalize argv for a whitelisted eurika subcommand."""
    allowed_flags = EXEC_ALLOWED_FLAGS.get(subcmd, {})
    flags: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(raw_args):
        tok = str(raw_args[i])
        if tok.startswith("-"):
            arity = allowed_flags.get(tok)
            if arity is None:
                allowed = ", ".join(sorted(allowed_flags.keys()))
                hint = f"Allowed flags for '{subcmd}': {allowed}" if allowed else f"'{subcmd}' does not accept flags"
                return None, f"flag not allowed for '{subcmd}': {tok}. {hint}"
            flags.append(tok)
            if arity == _FLAG_TAKES_VALUE:
                if i + 1 >= len(raw_args):
                    return None, f"flag '{tok}' requires a value"
                flags.append(str(raw_args[i + 1]))
                i += 1
            i += 1
            continue
        positional.append(tok)
        i += 1

    path_str = str(project_root)
    if subcmd == "explain":
        if not positional:
            return None, "explain requires module positional argument (e.g. 'eurika explain cli/handlers.py')"
        if len(positional) > 2:
            return None, f"too many positional arguments for explain: {positional}"
        module = positional[0]
        return [module, path_str] + flags, None

    if len(positional) > 1:
        return None, f"too many positional arguments for '{subcmd}': {positional}"
    return [path_str] + flags, None


def _parse_bool_flag(value: object) -> bool | None:
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


def _json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


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


def _resolve_project_root_override(
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


def _exec_eurika_command(project_root: Path, command: str, timeout: int | None = 120) -> dict:
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
    normalized_args, normalize_error = _normalize_exec_args_for_subcommand(
        project_root, subcmd, args
    )
    if normalize_error:
        return {"error": normalize_error, "stdout": "", "stderr": "", "exit_code": -1}

    full_args = [sys.executable, "-m", "eurika_cli", subcmd] + (normalized_args or [])
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


def _dispatch_api_get(
    handler: BaseHTTPRequestHandler,
    project_root: Path,
    path: str,
    query: dict,
) -> bool:
    """Dispatch GET /api/* routes. Returns True if handled."""
    if path == "/api/summary":
        include_plugins = query.get("include_plugins", ["0"])[0].lower() in ("1", "true", "yes")
        _json_response(handler, get_summary(project_root, include_plugins=include_plugins))
        return True
    if path == "/api/self_guard":
        _json_response(handler, get_self_guard(project_root))
        return True
    if path == "/api/risk_prediction":
        top_n = int(query.get("top_n", [10])[0])
        _json_response(handler, get_risk_prediction(project_root, top_n=top_n))
        return True
    if path == "/api/smells_with_plugins":
        include = query.get("include_plugins", ["1"])[0].lower() not in ("0", "false", "no")
        _json_response(handler, get_smells_with_plugins(project_root, include_plugins=include))
        return True
    if path == "/api/history":
        window = int(query.get("window", [5])[0])
        _json_response(handler, get_history(project_root, window=window))
        return True
    if path.rstrip("/") == "/api":
        _json_response(handler, {
            "eurika": "JSON API",
            "project_root": str(project_root),
            "endpoints": [
                "GET /api/summary?include_plugins=1 — summary (R5: merge plugin smells when 1)",
                "GET /api/self_guard — R5 SELF-GUARD health gate (violations, alarms)",
                "GET /api/risk_prediction?top_n=10 — R5 top modules by regression risk",
                "GET /api/smells_with_plugins?include_plugins=1 — R5 Eurika + plugin smells",
                "GET /api/history?window=5 — evolution history",
                "GET /api/diff?old=path/to/old.json&new=path/to/new.json — diff two self_maps",
                "GET /api/doctor?window=5&no_llm=0 — full report + architect (ROADMAP 3.5.1)",
                "GET /api/patch_plan?window=5 — planned operations",
                "GET /api/explain?module=...&window=5 — module role and risks",
                "GET /api/graph — dependency graph (nodes=modules, edges=imports)",
                "GET /api/operational_metrics?window=10 — apply-rate, rollback-rate, median verify time",
                "GET /api/pending_plan — team-mode plan for approve UI (ROADMAP 3.5.6)",
                "GET /api/file?path=... — read file content (for diff preview)",
                "POST /api/operation_preview — preview single-file op diff (ROADMAP 3.6.7)",
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
        if not str(rel).strip() or ".." in rel or rel.startswith("/"):
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
    if path == "/api/operation_preview":
        if not body or "operation" not in body:
            _json_response(
                handler,
                {"error": "JSON body with 'operation' object required"},
                status=400,
            )
            return True
        op = body.get("operation")
        if not isinstance(op, dict):
            _json_response(handler, {"error": "operation must be object"}, status=400)
            return True
        _json_response(handler, preview_operation(project_root, op))
        return True
    if path == "/api/approve":
        if not body or "operations" not in body:
            _json_response(
                handler,
                {"error": "JSON body with 'operations' array required"},
                status=400,
            )
            return True
        ops = body.get("operations")
        if not isinstance(ops, list) or any(not isinstance(op, dict) for op in ops):
            _json_response(
                handler,
                {"error": "invalid operations payload", "hint": "Expected operations: list[object]"},
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
        command = body.get("command")
        if not isinstance(command, str):
            _json_response(
                handler,
                {"error": "invalid command payload", "hint": "Expected command: string"},
                status=400,
            )
            return True
        raw_timeout = body.get("timeout", 120)
        if raw_timeout is None:
            timeout = None
        else:
            try:
                timeout = int(raw_timeout)
            except (TypeError, ValueError):
                _json_response(
                    handler,
                    {"error": "invalid timeout payload", "hint": "Expected timeout: integer or null"},
                    status=400,
                )
                return True
            if timeout < EXEC_TIMEOUT_MIN or timeout > EXEC_TIMEOUT_MAX:
                _json_response(
                    handler,
                    {
                        "error": "invalid timeout range",
                        "hint": f"Expected timeout: {EXEC_TIMEOUT_MIN}..{EXEC_TIMEOUT_MAX} seconds (or null for unlimited)",
                    },
                    status=400,
                )
                return True
        data = _exec_eurika_command(project_root, command, timeout=timeout)
        _json_response(handler, data)
        return True
    if path == "/api/ask_architect":
        from cli.orchestration.doctor import run_doctor_cycle
        no_llm_raw = (body or {}).get("no_llm", False)
        no_llm = _parse_bool_flag(no_llm_raw)
        if no_llm is None:
            _json_response(
                handler,
                {"error": "invalid no_llm payload", "hint": "Expected no_llm: boolean"},
                status=400,
            )
            return True
        doctor_data = run_doctor_cycle(project_root, window=5, no_llm=no_llm)
        if doctor_data.get("error"):
            _json_response(handler, {"error": doctor_data["error"], "text": ""})
            return True
        text = doctor_data.get("architect_text") or ""
        _json_response(handler, {"text": text})
        return True
    if path == "/api/chat":
        if not body or "message" not in body:
            _json_response(
                handler,
                {"error": "JSON body with 'message' required"},
                status=400,
            )
            return True
        msg = body.get("message")
        if not isinstance(msg, str):
            _json_response(
                handler,
                {"error": "invalid message payload", "hint": "Expected message: string"},
                status=400,
            )
            return True
        raw_history = body.get("history")
        history: list[dict[str, str]] | None = None
        if raw_history is not None:
            if not isinstance(raw_history, list):
                _json_response(
                    handler,
                    {"error": "invalid history payload", "hint": "Expected history: list[object]"},
                    status=400,
                )
                return True
            normalized: list[dict[str, str]] = []
            for item in raw_history:
                if not isinstance(item, dict):
                    _json_response(
                        handler,
                        {"error": "invalid history payload", "hint": "Expected history: list[object]"},
                        status=400,
                    )
                    return True
                role = item.get("role", "user")
                content = item.get("content", "")
                if not isinstance(role, str) or not isinstance(content, str):
                    _json_response(
                        handler,
                        {"error": "invalid history payload", "hint": "Expected role/content: string"},
                        status=400,
                    )
                    return True
                normalized.append({"role": role, "content": content})
            history = normalized
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
            selected_root = root
            if path.startswith("/api"):
                selected_root, root_err = _resolve_project_root_override(
                    root,
                    query.get("project_root"),
                )
                if root_err:
                    _json_response(self, {"error": root_err}, status=400)
                    return
                if selected_root is None:
                    _json_response(self, {"error": "invalid project_root payload"}, status=400)
                    return
            _run_handler(self, selected_root, path, query, body=None)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            body = _read_json_body(self)
            selected_root = root
            if path.startswith("/api"):
                selected_root, root_err = _resolve_project_root_override(
                    root,
                    (body or {}).get("project_root"),
                )
                if root_err:
                    _json_response(self, {"error": root_err}, status=400)
                    return
                if selected_root is None:
                    _json_response(self, {"error": "invalid project_root payload"}, status=400)
                    return
            if _run_post_handler(self, selected_root, path, body):
                return
            _json_response(
                self,
                {"error": "not found", "path": path},
                status=404,
            )

        def log_message(self, format: str, *args: object) -> None:
            pass  # quiet by default; override to enable logging

    server = HTTPServer((host, port), APIHandler)
    print(f"Eurika: http://{host}:{port}/api  (JSON API)")
    print(f"Project root: {root}")
    server.serve_forever()




# TODO (eurika): refactor long_function '_dispatch_api_get' — consider extracting helper
