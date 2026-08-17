"""CLI/library client for the loopback Eurika HTTP gateway."""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .http_api import read_endpoint


class AgentHttpClient:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    @classmethod
    def discover(cls, workspace: str | Path = ".") -> "AgentHttpClient":
        endpoint = read_endpoint(Path(workspace))
        if endpoint is None:
            raise FileNotFoundError(
                "Eurika HTTP gateway is not running. Open Eurika Qt or Desktop "
                "(or start `python -m eurika.agent.stdio`) and retry."
            )
        return cls(str(endpoint["url"]), str(endpoint["token"]))

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get(self, path: str) -> dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 300) -> dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path
        return self._request("POST", path, payload or {}, timeout=timeout)

    def chat(self, message: str, *, history: list[dict[str, Any]] | None = None, timeout: float = 180) -> dict[str, Any]:
        """Core Eurika chat (`chat_send` / Qt Chat tab)."""
        payload: dict[str, Any] = {"message": message}
        if history is not None:
            payload["history"] = history
        return self.post("/api/chat", payload, timeout=timeout)

    def agent_chat(self, message: str, *, context: dict[str, Any] | None = None, timeout: float = 90) -> dict[str, Any]:
        """Desktop local-agent session/chat loop."""
        payload: dict[str, Any] = {"message": message}
        if context:
            payload["context"] = context
        return self.post("/chat", payload, timeout=timeout)

    def exec_command(self, command: str, *, timeout: int | None = 120) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command}
        http_timeout = float(timeout) + 15 if timeout is not None else 135.0
        if timeout is not None:
            payload["timeout"] = timeout
        return self.post("/api/exec", payload, timeout=http_timeout)

    def rpc(self, method: str, params: dict[str, Any] | None = None, request_id: Any = 1, *, timeout: float = 300) -> dict[str, Any]:
        return self.post(
            "/rpc",
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 300) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise RuntimeError(f"Eurika HTTP gateway timed out after {timeout:.0f}s on {method} {path}") from exc
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError) as exc:
            raise RuntimeError(
                "Eurika HTTP gateway closed the connection. Restart Eurika Qt or Desktop "
                "so it loads the current /api/* handlers."
            ) from exc


def _cli_ok(payload: dict[str, Any]) -> bool:
    """Treat JSON `error: null` from chat_send as success."""
    if payload.get("ok") is False:
        return False
    err = payload.get("error")
    return err in (None, "", False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Call the running Eurika gateway over loopback HTTP")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("market")
    sub.add_parser("learning")
    get = sub.add_parser("get")
    get.add_argument("path", help="Gateway path, e.g. /api/summary")
    chat = sub.add_parser("chat", help="Core Eurika chat (same as Qt Chat)")
    chat.add_argument("message")
    agent_chat = sub.add_parser("agent-chat", help="Desktop local-agent session/chat")
    agent_chat.add_argument("message")
    rpc = sub.add_parser("rpc")
    rpc.add_argument("method")
    rpc.add_argument("params", nargs="?", default="{}")
    exe = sub.add_parser("exec", help="Whitelisted eurika command via POST /api/exec")
    exe.add_argument("command")
    args = parser.parse_args(argv)
    client = AgentHttpClient.discover(args.workspace)
    if args.cmd == "health":
        payload = client.health()
    elif args.cmd == "market":
        payload = client.get("/api/market")
    elif args.cmd == "learning":
        payload = client.get("/api/learning")
    elif args.cmd == "get":
        payload = client.get(args.path)
    elif args.cmd == "chat":
        payload = client.chat(args.message)
    elif args.cmd == "agent-chat":
        payload = client.agent_chat(args.message)
    elif args.cmd == "exec":
        payload = client.exec_command(args.command)
    else:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise SystemExit("rpc params must be a JSON object")
        payload = client.rpc(args.method, params)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if _cli_ok(payload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
