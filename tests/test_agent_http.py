"""Loopback HTTP JSON-RPC for the local coding agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eurika.agent.http_api import AgentHttpService, read_endpoint
from eurika.agent.http_client import AgentHttpClient
from eurika.agent.local_runtime import LocalAgentRuntime


@pytest.fixture
def agent_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EURIKA_AGENT_HTTP", "1")
    runtime = LocalAgentRuntime(tmp_path)
    service = AgentHttpService(runtime, port=0)
    service.start()
    try:
        yield service
    finally:
        service.stop()


def test_agent_http_health_requires_token(agent_http: AgentHttpService) -> None:
    import urllib.error
    import urllib.request

    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{agent_http.url}/health", timeout=5)
    assert exc.value.code == 401


def test_agent_http_health_and_initialize(agent_http: AgentHttpService, tmp_path: Path) -> None:
    endpoint = read_endpoint(tmp_path)
    assert endpoint is not None
    assert endpoint["url"] == agent_http.url
    client = AgentHttpClient(agent_http.url, agent_http.token)
    health = client.health()
    assert health["ok"] is True
    assert health["workspace"] == str(tmp_path.resolve())
    assert "core" in health["surfaces"]
    rpc = client.rpc("initialize", {"protocolVersion": "1.0"})
    assert rpc["result"]["protocolVersion"] == "1.0"
    assert "session/chat" in rpc["result"]["methods"]


def test_agent_http_chat_executes_bare_tool_json(
    agent_http: AgentHttpService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "readme.txt").write_text("hello from workspace\n", encoding="utf-8")
    replies = iter(
        [
            json.dumps({"tool": "read", "arguments": {"path": "readme.txt"}}),
            '{"type":"final","text":"readme.txt says hello from workspace."}',
        ]
    )
    monkeypatch.setattr(agent_http.runtime, "_call_model", lambda prompt: (next(replies), None))
    client = AgentHttpClient(agent_http.url, agent_http.token)
    result = client.agent_chat("What does readme.txt say?")
    assert result["ok"] is True
    assert "hello from workspace" in result["text"]
    assert result["sessionId"]
    assert result["pendingToolCalls"] == []


def test_health_hit_is_written_to_live_activity(agent_http: AgentHttpService, tmp_path: Path) -> None:
    from eurika.agent.live_activity import recent

    client = AgentHttpClient(agent_http.url, agent_http.token)
    assert client.health()["ok"] is True
    titles = [event.get("title") for event in recent(tmp_path)["events"]]
    assert any(isinstance(title, str) and "GET /health" in title for title in titles)


def test_agent_http_stops_and_removes_endpoint(tmp_path: Path) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    service = AgentHttpService(runtime, port=0)
    service.start()
    assert read_endpoint(tmp_path) is not None
    service.stop()
    assert read_endpoint(tmp_path) is None


def test_agent_http_client_discover_waits_for_running_server(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        AgentHttpClient.discover(tmp_path)


def test_gateway_exposes_core_api_market_and_learning(agent_http: AgentHttpService) -> None:
    client = AgentHttpClient(agent_http.url, agent_http.token)
    catalog = client.get("/api")
    assert catalog.get("eurika") == "JSON API"
    endpoints = " ".join(catalog.get("endpoints") or [])
    assert "GET /api/market" in endpoints
    assert "GET /api/learning" in endpoints
    market = client.get("/api/market")
    assert market["panel"] == "market"
    assert isinstance(market.get("data"), dict)
    learning = client.get("/api/learning")
    assert "paper" in learning
    missing = client.post("/api/chat", {})
    assert "error" in missing


def test_ensure_workspace_gateway_reuses_live_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eurika.agent.http_api import ensure_workspace_gateway

    monkeypatch.setenv("EURIKA_AGENT_HTTP", "1")
    monkeypatch.setenv("EURIKA_AGENT_HTTP_PORT", "0")
    first = ensure_workspace_gateway(tmp_path)
    assert first is not None
    try:
        second = ensure_workspace_gateway(tmp_path)
        assert second is None
        health = AgentHttpClient.discover(tmp_path).health()
        assert health["ok"] is True
        assert health["workspace"] == str(tmp_path.resolve())
    finally:
        first.stop()


def test_serve_routes_get_imports_without_loading_serve() -> None:
    import importlib
    import sys

    for name in (
        "eurika.api.serve",
        "eurika.api.serve_routes_get",
        "eurika.api.serve_routes_post",
    ):
        sys.modules.pop(name, None)
    mod = importlib.import_module("eurika.api.serve_routes_get")
    assert callable(mod.dispatch_api_get)
    assert "eurika.api.serve" not in sys.modules


def test_gateway_market_survives_cold_process(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys
    import textwrap

    script = tmp_path / "cold_gateway.py"
    script.write_text(
        textwrap.dedent(
            """
            from pathlib import Path
            from eurika.agent.http_api import AgentHttpService
            from eurika.agent.http_client import AgentHttpClient
            from eurika.agent.local_runtime import LocalAgentRuntime

            root = Path(__file__).resolve().parent
            service = AgentHttpService(LocalAgentRuntime(root), port=0)
            service.start()
            try:
                market = AgentHttpClient(service.url, service.token).get("/api/market")
                assert market.get("panel") == "market", market
            finally:
                service.stop()
            """
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_ok_treats_null_error_as_success() -> None:
    from eurika.agent.http_client import _cli_ok

    assert _cli_ok({"ok": True})
    assert _cli_ok({"text": "hi", "error": None})
    assert not _cli_ok({"ok": False, "text": "x"})
    assert not _cli_ok({"error": "boom"})

