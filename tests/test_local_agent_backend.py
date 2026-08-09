"""Focused tests for the local JSON-RPC coding backend."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from eurika.agent.contracts import TOOL_CONTRACTS
from eurika.agent.local_runtime import LocalAgentRuntime
from eurika.agent.protocol import (
    ERR_APPROVAL_REQUIRED,
    ERR_CANCELLED,
    ERR_WORKSPACE_VIOLATION,
    PROTOCOL_VERSION,
    RpcError,
)
from eurika.agent.stdio import JsonRpcStdioServer
from eurika.agent.workspace import WorkspaceTools


def _runtime_call(
    runtime: LocalAgentRuntime, method: str, params: dict, events: list[tuple]
) -> dict[str, Any]:
    return runtime.dispatch(
        method,
        params,
        cancel=threading.Event(),
        emit=lambda event, session_id, data: events.append((event, session_id, data)),
    )


def test_handshake_advertises_versioned_structured_capabilities(tmp_path: Path) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    result = _runtime_call(runtime, "initialize", {"protocolVersion": PROTOCOL_VERSION}, [])
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["features"]["cancellation"] is True
    assert result["features"]["streamingEvents"] is True
    assert set(result["tools"]) == {
        "search", "read", "edit", "terminal", "diagnostics", "tests", "git_diff"
    }
    assert TOOL_CONTRACTS["edit"]["requiresApproval"] is True
    assert TOOL_CONTRACTS["read"]["requiresApproval"] is False


def test_local_agent_eval_cases_reference_advertised_tools() -> None:
    fixture = Path(__file__).parent / "fixtures" / "local_agent_eval_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(cases) >= 5
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["prompt"]
        assert case["success"]
        assert set(case["requiredTools"]).issubset(TOOL_CONTRACTS)


def test_session_tool_call_streams_events_and_reads_file(tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("answer = 42\n", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    events: list[tuple] = []
    created = _runtime_call(runtime, "session/create", {"metadata": {"client": "test"}}, events)
    session_id = created["sessionId"]
    result = _runtime_call(
        runtime,
        "tool/call",
        {"sessionId": session_id, "tool": "read", "arguments": {"path": "hello.py"}},
        events,
    )
    assert result["result"]["content"] == "answer = 42\n"
    assert [event[0] for event in events] == ["tool/started", "tool/completed"]
    assert all(event[1] == session_id for event in events)


def test_search_respects_gitignore_and_retrieves_symbols(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("def HiddenSymbol():\n    pass\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("def VisibleSymbol():\n    pass\n", encoding="utf-8")
    tools = WorkspaceTools(tmp_path)

    result = tools.search(
        {"query": "Symbol", "mode": "symbol"},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )

    assert [match["symbol"] for match in result["matches"]] == ["VisibleSymbol"]


def test_agent_run_executes_structured_calls_and_streams_summary(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    events: list[tuple] = []
    session_id = _runtime_call(runtime, "session/create", {}, events)["sessionId"]
    result = _runtime_call(
        runtime,
        "agent/run",
        {
            "sessionId": session_id,
            "toolCalls": [
                {"tool": "search", "arguments": {"query": "needle"}},
                {"tool": "read", "arguments": {"path": "a.txt"}},
            ],
        },
        events,
    )
    assert len(result["toolResults"]) == 2
    assert "2 structured tool call" in result["text"]
    assert "response/chunk" in [event[0] for event in events]


def test_session_chat_streams_model_response_and_creates_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    monkeypatch.setattr(
        runtime,
        "_call_model",
        lambda prompt: ('{"type":"final","text":"Evidence-based answer."}', None),
    )
    events: list[tuple] = []

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Explain the project", "context": {"activeFile": None}},
        events,
    )

    assert result["sessionId"]
    assert result["text"] == "Evidence-based answer."
    assert result["pendingToolCalls"] == []
    assert result["metrics"]["toolCallErrors"] == 0
    assert result["metrics"]["contextBytes"] > 0
    assert [event[0] for event in events] == [
        "message_start",
        "response/chunk",
        "message_end",
    ]


def test_session_chat_executes_reads_but_returns_edits_for_client_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [
                        {"tool": "read", "arguments": {"path": "sample.txt"}},
                    ],
                }
            ),
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [
                        {
                            "tool": "edit",
                            "arguments": {
                                "path": "sample.txt",
                                "oldText": "old",
                                "newText": "new",
                            },
                        }
                    ],
                }
            ),
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Update sample.txt", "context": {}},
        [],
    )

    assert target.read_text(encoding="utf-8") == "old"
    assert result["pendingToolCalls"][0]["tool"] == "edit"
    assert result["pendingToolCalls"][0]["arguments"]["newText"] == "new"


def test_workspace_confinement_rejects_parent_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    tools = WorkspaceTools(root)
    with pytest.raises(RpcError) as parent_error:
        tools.resolve("../outside.txt", must_exist=True)
    assert parent_error.value.code == ERR_WORKSPACE_VIOLATION
    (root / "escape").symlink_to(outside)
    with pytest.raises(RpcError) as symlink_error:
        tools.resolve("escape", must_exist=True)
    assert symlink_error.value.code == ERR_WORKSPACE_VIOLATION


def test_edit_requires_approval_and_uses_optimistic_version(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    tools = WorkspaceTools(tmp_path)
    cancel = threading.Event()
    with pytest.raises(RpcError) as error:
        tools.edit({"path": "sample.txt", "content": "new"}, cancel=cancel, emit=lambda *_: None)
    assert error.value.code == ERR_APPROVAL_REQUIRED
    version = tools.read({"path": "sample.txt"}, cancel=cancel, emit=lambda *_: None)["version"]
    result = tools.edit(
        {
            "path": "sample.txt",
            "oldText": "old",
            "newText": "new",
            "expectedVersion": version,
            "approval": True,
        },
        cancel=cancel,
        emit=lambda *_: None,
    )
    assert target.read_text(encoding="utf-8") == "new"
    assert result["version"] != version


def test_batch_edit_applies_multiple_files_under_one_approval(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    result = WorkspaceTools(tmp_path).edit(
        {
            "approval": True,
            "edits": [
                {"path": "first.txt", "oldText": "one", "newText": "ONE"},
                {"path": "second.txt", "oldText": "two", "newText": "TWO"},
            ],
        },
        cancel=threading.Event(),
        emit=lambda *_: None,
    )

    assert len(result["files"]) == 2
    assert first.read_text(encoding="utf-8") == "ONE"
    assert second.read_text(encoding="utf-8") == "TWO"


def test_terminal_requires_approval_and_can_be_cancelled(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path)
    with pytest.raises(RpcError) as approval_error:
        tools.terminal(
            {"argv": [sys.executable, "-c", "print('x')"]},
            cancel=threading.Event(),
            emit=lambda *_: None,
        )
    assert approval_error.value.code == ERR_APPROVAL_REQUIRED

    cancel = threading.Event()
    captured: list[RpcError] = []

    def run() -> None:
        try:
            tools.terminal(
                {
                    "argv": [sys.executable, "-c", "import time; time.sleep(10)"],
                    "approval": True,
                    "timeoutMs": 20_000,
                },
                cancel=cancel,
                emit=lambda *_: None,
            )
        except RpcError as exc:
            captured.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.1)
    cancel.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert captured and captured[0].code == ERR_CANCELLED


def test_diagnostics_reports_python_syntax_errors(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = WorkspaceTools(tmp_path).diagnostics(
        {"paths": ["broken.py"]}, cancel=threading.Event(), emit=lambda *_: None
    )
    assert result["checked"] == 1
    assert result["diagnostics"][0]["path"] == "broken.py"
    assert result["diagnostics"][0]["severity"] == "error"


def test_stdio_server_emits_jsonrpc_handshake_response(tmp_path: Path) -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION},
    }
    reader = io.StringIO(json.dumps(request) + "\n")
    writer = io.StringIO()
    JsonRpcStdioServer(LocalAgentRuntime(tmp_path), reader=reader, writer=writer).serve_forever()
    messages = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(messages) == 1
    assert messages[0]["jsonrpc"] == "2.0"
    assert messages[0]["id"] == 7
    assert messages[0]["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_stdio_server_cancels_active_request(tmp_path: Path) -> None:
    class SlowRuntime(LocalAgentRuntime):
        def dispatch(self, method, params, *, cancel, emit):
            while not cancel.wait(0.01):
                pass
            raise RpcError(ERR_CANCELLED, "Request cancelled")

    requests = [
        {"jsonrpc": "2.0", "id": 9, "method": "session/chat", "params": {"message": "wait"}},
        {"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": 9}},
    ]
    reader = io.StringIO("".join(json.dumps(request) + "\n" for request in requests))
    writer = io.StringIO()

    JsonRpcStdioServer(SlowRuntime(tmp_path), reader=reader, writer=writer).serve_forever()

    messages = [json.loads(line) for line in writer.getvalue().splitlines()]
    response = next(message for message in messages if message.get("id") == 9)
    assert response["error"]["code"] == ERR_CANCELLED
