"""Loopback HTTP gateway for core Eurika (/api/*) and the local coding agent."""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .local_runtime import LocalAgentRuntime
from .protocol import (
    ERR_INTERNAL,
    ERR_INVALID_REQUEST,
    ERR_PARSE,
    JSONRPC_VERSION,
    RpcError,
    error_response,
    success_response,
    validate_request,
)

DEFAULT_PORT = 18765
ENDPOINT_FILE = "agent_http.json"
MAX_BODY_BYTES = 4_000_000


def endpoint_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".eurika" / ENDPOINT_FILE


def read_endpoint(workspace: Path) -> dict[str, Any] | None:
    path = endpoint_path(workspace)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not payload.get("url") or not payload.get("token"):
        return None
    return payload


def agent_http_enabled() -> bool:
    raw = (os.environ.get("EURIKA_AGENT_HTTP") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def probe_endpoint(endpoint: dict[str, Any], timeout: float = 1.5) -> dict[str, Any] | None:
    """Return /health payload if this workspace endpoint is alive."""
    url = str(endpoint.get("url") or "").rstrip("/")
    token = str(endpoint.get("token") or "")
    if not url or not token:
        return None
    request = urllib.request.Request(
        f"{url}/health",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None
    if isinstance(payload, dict) and payload.get("ok"):
        return payload
    return None


class AgentHttpService:
    """Serve LocalAgentRuntime on 127.0.0.1 and publish a workspace endpoint file."""

    def __init__(
        self,
        runtime: LocalAgentRuntime,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        token: str | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("agent HTTP binds to loopback only")
        self.runtime = runtime
        self.host = "127.0.0.1" if host == "localhost" else host
        self.token = token or secrets.token_urlsafe(32)
        self._preferred_port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._session_id: str | None = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("agent HTTP is not running")
        host, port = self._httpd.server_address[:2]
        if isinstance(host, (bytes, bytearray)):
            host = host.decode()
        return f"http://{host}:{port}"

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("agent HTTP is not running")
        return int(self._httpd.server_address[1])

    def start(self) -> dict[str, Any]:
        if self._httpd is not None:
            return self._write_endpoint()
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                print(f"[eurika-http] {format % args}", file=sys.stderr, flush=True)

            def _unauthorized(self) -> None:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization") or ""
                token = ""
                if header.lower().startswith("bearer "):
                    token = header[7:].strip()
                if not token:
                    token = (self.headers.get("X-Eurika-Token") or "").strip()
                return bool(token) and secrets.compare_digest(token, service.token)

            def do_GET(self) -> None:
                if not self._authorized():
                    self._unauthorized()
                    return
                try:
                    self._do_GET()
                except Exception as exc:
                    self._internal_error("GET", exc)

            def do_POST(self) -> None:
                if not self._authorized():
                    self._unauthorized()
                    return
                try:
                    self._do_POST()
                except Exception as exc:
                    self._internal_error("POST", exc)

            def _do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                query = parse_qs(parsed.query)
                status = 200
                ok = True
                try:
                    if path in {"/", "/health"}:
                        self._json(
                            {
                                "ok": True,
                                "workspace": str(service.runtime.workspace_root),
                                "pid": os.getpid(),
                                "sessionId": service._session_id,
                                "surfaces": ["core", "agent"],
                            }
                        )
                        return
                    if path.startswith("/api"):
                        from eurika.api.serve_routes_get import dispatch_api_get

                        if dispatch_api_get(self, service.runtime.workspace_root, path, query):
                            return
                        status = 404
                        ok = False
                        self._json({"error": "not found", "path": path}, status=404)
                        return
                    status = 404
                    ok = False
                    self._json({"error": "not found", "path": path}, status=404)
                finally:
                    from .live_activity import publish_http

                    publish_http(
                        service.runtime.workspace_root,
                        "GET",
                        path,
                        ok=ok,
                        status=status,
                    )

            def _do_POST(self) -> None:
                path = urlparse(self.path).path.rstrip("/") or "/"
                status = 200
                ok = True
                try:
                    body = service._read_body(self)
                except RpcError as exc:
                    self._json(error_response(None, exc), status=400)
                    from .live_activity import publish_http

                    publish_http(
                        service.runtime.workspace_root, "POST", path, ok=False, status=400
                    )
                    return
                try:
                    if path == "/rpc":
                        rpc = service.handle_rpc(body)
                        if "error" in rpc:
                            ok = False
                            status = 200
                        self._json(rpc)
                        return
                    if path == "/chat":
                        payload = service.handle_chat(body)
                        ok = payload.get("ok") is not False
                        status = 200 if ok else 400
                        self._json(payload, status=status)
                        return
                    if path.startswith("/api"):
                        from eurika.api.serve_routes_post import dispatch_api_post

                        if dispatch_api_post(
                            self,
                            service.runtime.workspace_root,
                            path,
                            body if isinstance(body, dict) else None,
                        ):
                            return
                        status = 404
                        ok = False
                        self._json({"error": "not found", "path": path}, status=404)
                        return
                    status = 404
                    ok = False
                    self._json({"error": "not found", "path": path}, status=404)
                finally:
                    from .live_activity import publish_http

                    detail = ""
                    if path == "/rpc" and isinstance(body, dict):
                        detail = str(body.get("method") or "")
                    elif path in {"/chat", "/api/chat"} and isinstance(body, dict):
                        detail = str(body.get("message") or "")
                    publish_http(
                        service.runtime.workspace_root,
                        "POST",
                        path,
                        ok=ok,
                        status=status,
                        detail=detail,
                    )

            def _internal_error(self, method: str, exc: Exception) -> None:
                detail = f"{type(exc).__name__}: {exc}"
                print(f"[eurika-http] {method} failed: {detail}", file=sys.stderr, flush=True)
                try:
                    self._json({"error": "internal error", "detail": detail}, status=500)
                except Exception:
                    pass

            def _json(self, payload: dict[str, Any], status: int = 200) -> None:
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        httpd = self._bind(Handler)
        self._httpd = httpd
        # Import routes before serving so a circular import fails at startup, not on the first GET.
        from eurika.api.serve_routes_get import dispatch_api_get as _dispatch_api_get  # noqa: F401
        from eurika.api.serve_routes_post import dispatch_api_post as _dispatch_api_post  # noqa: F401
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="eurika-agent-http",
            daemon=True,
        )
        self._thread.start()
        info = self._write_endpoint()
        print(
            f"Eurika HTTP gateway: {info['url']}  (token in {endpoint_path(self.runtime.workspace_root)})",
            file=sys.stderr,
            flush=True,
        )
        return info

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            # Default ThreadingMixIn.server_close() joins in-flight /chat threads
            # (local-agent LLM). Closing the Qt window must not wait for that.
            httpd.block_on_close = False
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1)
        path = endpoint_path(self.runtime.workspace_root)
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if isinstance(current, dict) and current.get("pid") == os.getpid():
            path.unlink(missing_ok=True)

    def handle_rpc(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            return error_response(None, RpcError(ERR_PARSE, "JSON-RPC body must be an object"))
        events: list[dict[str, Any]] = []
        cancel = threading.Event()
        try:
            request_id, method, params = validate_request(body)
        except RpcError as exc:
            return error_response(body.get("id") if isinstance(body, dict) else None, exc)
        params = self._with_session(method, dict(params))

        def emit(event: str, session_id: str | None, data: dict[str, Any]) -> None:
            events.append({"event": event, "sessionId": session_id, "data": data})

        try:
            result = self.runtime.dispatch(method, params, cancel=cancel, emit=emit)
        except RpcError as exc:
            return error_response(request_id, exc)
        except Exception as exc:  # pragma: no cover - containment
            detail = f"{type(exc).__name__}: {exc}"
            print(f"[eurika-http] {detail}", file=sys.stderr, flush=True)
            return error_response(request_id, RpcError(ERR_INTERNAL, "Internal error", {"detail": detail}))
        response = success_response(request_id, result)
        if events:
            response["events"] = events
        return response

    def handle_chat(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {"error": "JSON body required", "hint": '{"message":"..."}'}
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            return {"error": "message must be a non-empty string"}
        params: dict[str, Any] = {"message": message}
        if isinstance(body.get("sessionId"), str):
            params["sessionId"] = body["sessionId"]
        if isinstance(body.get("context"), dict):
            params["context"] = body["context"]
        rpc = self.handle_rpc(
            {
                "jsonrpc": JSONRPC_VERSION,
                "id": "chat",
                "method": "session/chat",
                "params": params,
            }
        )
        if "error" in rpc:
            return {"ok": False, **rpc}
        raw_result = rpc.get("result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
        return {
            "ok": True,
            "sessionId": result.get("sessionId") or params.get("sessionId"),
            "text": result.get("text", ""),
            "pendingToolCalls": result.get("pendingToolCalls") or [],
            "approvalsQueued": result.get("approvalsQueued") or 0,
            "metrics": result.get("metrics") or {},
            "events": rpc.get("events") or [],
        }

    def _with_session(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method not in {"session/chat", "tool/call"}:
            return params
        if isinstance(params.get("sessionId"), str) and params["sessionId"]:
            return params
        with self._lock:
            if self._session_id is None:
                created = self.runtime.dispatch(
                    "session/create",
                    {"metadata": {"client": "agent-http"}},
                    cancel=threading.Event(),
                    emit=lambda *_: None,
                )
                self._session_id = str(created["sessionId"])
            params["sessionId"] = self._session_id
        return params

    def _write_endpoint(self) -> dict[str, Any]:
        info = {
            "url": self.url,
            "token": self.token,
            "workspace": str(self.runtime.workspace_root),
            "pid": os.getpid(),
            "rpc": f"{self.url}/rpc",
            "api": f"{self.url}/api",
            "chat": f"{self.url}/api/chat",
            "agentChat": f"{self.url}/chat",
            "market": f"{self.url}/api/market",
            "learning": f"{self.url}/api/learning",
            "health": f"{self.url}/health",
            "surfaces": ["core", "agent"],
        }
        path = endpoint_path(self.runtime.workspace_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return info

    def _bind(self, handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
        preferred = self._preferred_port
        if preferred is None:
            raw = (os.environ.get("EURIKA_AGENT_HTTP_PORT") or str(DEFAULT_PORT)).strip()
            try:
                preferred = int(raw)
            except ValueError:
                preferred = DEFAULT_PORT
        if preferred == 0:
            return self._configure_httpd(ThreadingHTTPServer((self.host, 0), handler))
        last_error: OSError | None = None
        for port in range(preferred, preferred + 10):
            try:
                return self._configure_httpd(ThreadingHTTPServer((self.host, port), handler))
            except OSError as exc:
                last_error = exc
        raise OSError(f"Could not bind agent HTTP near port {preferred}: {last_error}") from last_error

    @staticmethod
    def _configure_httpd(httpd: ThreadingHTTPServer) -> ThreadingHTTPServer:
        httpd.daemon_threads = True
        httpd.block_on_close = False
        return httpd

    @staticmethod
    def _read_body(handler: BaseHTTPRequestHandler) -> Any:
        length = int(handler.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise RpcError(ERR_INVALID_REQUEST, "Request body is too large")
        raw = handler.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RpcError(ERR_PARSE, f"Invalid JSON: {exc}") from exc


def start_agent_http(runtime: LocalAgentRuntime) -> AgentHttpService | None:
    """Start loopback HTTP unless EURIKA_AGENT_HTTP=0 or a live gateway already owns the workspace."""
    if not agent_http_enabled():
        return None
    existing = read_endpoint(runtime.workspace_root)
    if existing and probe_endpoint(existing) is not None:
        print(
            f"Eurika HTTP already running at {existing['url']}",
            file=sys.stderr,
            flush=True,
        )
        return None
    token = (os.environ.get("EURIKA_AGENT_HTTP_TOKEN") or "").strip() or None
    service = AgentHttpService(runtime, token=token)
    service.start()
    return service


def ensure_workspace_gateway(
    workspace: str | Path,
    runtime: LocalAgentRuntime | None = None,
) -> AgentHttpService | None:
    """Start the workspace gateway, or reuse a healthy one already published."""
    if not agent_http_enabled():
        return None
    root = Path(workspace).expanduser().resolve()
    existing = read_endpoint(root)
    if existing and probe_endpoint(existing) is not None:
        return None
    if runtime is None:
        runtime = LocalAgentRuntime(root)
    try:
        return start_agent_http(runtime)
    except OSError as exc:
        print(f"[eurika-http] not started: {exc}", file=sys.stderr, flush=True)
        return None
