"""Focused tests for the local JSON-RPC coding backend."""

from __future__ import annotations

import io
import json
import os
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
    ERR_INTERNAL,
    ERR_INVALID_PARAMS,
    ERR_WORKSPACE_VIOLATION,
    PROTOCOL_VERSION,
    RpcError,
)
from eurika.agent.stdio import JsonRpcStdioServer, configure_workspace_env, redirect_library_stdout
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
    assert result["features"]["editProposals"] is True
    assert "proposal/apply" in result["methods"]
    assert result["methodContracts"]["proposal/apply"]["requiresApproval"] is True
    assert set(result["tools"]) == {
        "search", "read", "market_status", "edit", "terminal", "diagnostics", "tests", "git_diff"
    }
    assert TOOL_CONTRACTS["edit"]["requiresApproval"] is True
    assert TOOL_CONTRACTS["read"]["requiresApproval"] is False


@pytest.mark.parametrize(
    ("adapter_id", "panels"),
    [
        ("desktop", ["chat", "diff", "approvals", "commands", "market"]),
        ("vscode", ["chat"]),
        ("qt", ["market", "approvals", "commands"]),
    ],
)
def test_frontend_adapters_share_one_versioned_contract(
    tmp_path: Path, adapter_id: str, panels: list[str]
) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    result = _runtime_call(
        runtime,
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "client": {
                "name": f"eurika-{adapter_id}",
                "version": "0.1.0",
                "manifest": {
                    "id": adapter_id,
                    "name": adapter_id,
                    "version": "0.1.0",
                    "capabilities": {"panels": panels},
                },
            },
        },
        [],
    )
    assert result["clientAdapter"]["id"] == adapter_id
    assert result["adapterContract"]["version"] == 1
    assert result["features"]["productPanels"] is True


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


def test_market_status_tool_reads_stable_product_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coding_root = tmp_path / "coding"
    market_root = tmp_path / "market"
    coding_root.mkdir()
    ml = market_root / ".eurika" / "ml"
    ml.mkdir(parents=True)
    (ml / "paper_portfolio.json").write_text(
        json.dumps(
            {
                "start_equity_usdt": 1000.0,
                "equity_usdt": 975.0,
                "realized_pnl_usdt": -25.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EURIKA_MARKET_ROOT", str(market_root))
    runtime = LocalAgentRuntime(coding_root)
    session_id = _runtime_call(runtime, "session/create", {}, [])["sessionId"]

    response = _runtime_call(
        runtime,
        "tool/call",
        {"sessionId": session_id, "tool": "market_status", "arguments": {}},
        [],
    )

    assert response["result"]["marketRoot"] == str(market_root)
    assert response["result"]["portfolio"]["equity_usdt"] == 975.0
    assert response["result"]["verdict"]["tone"] == "loss"
    assert response["result"]["verdict"]["label"] == "убыток"
    assert "equity=975.00 USDT" in response["result"]["summary"]
    assert "вердикт: убыток" in response["result"]["summary"]
    assert not (coding_root / ".eurika" / "ml").exists()


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


def test_search_ranks_implementation_ahead_of_tests(tmp_path: Path) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "eurika" / "runtime.py").write_text(
        "def capabilities():\n    \"\"\"protocol handshake payload\"\"\"\n    return {}\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_runtime.py").write_text(
        "def test_handshake_advertises_capabilities():\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "RELEASE.md").write_text(
        "Protocol handshake and capability negotiation.\n",
        encoding="utf-8",
    )
    tools = WorkspaceTools(tmp_path)

    result = tools.search(
        {"query": "handshake", "maxResults": 3},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )

    paths = [match["path"] for match in result["matches"]]
    assert paths[0] == "eurika/runtime.py"
    assert result["matches"][0]["kind"] == "implementation"
    assert "tests/test_runtime.py" in paths
    assert paths.index("eurika/runtime.py") < paths.index("tests/test_runtime.py")


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


def test_session_chat_can_ground_market_assessment_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ml = tmp_path / ".eurika" / "ml"
    ml.mkdir(parents=True)
    (ml / "paper_portfolio.json").write_text(
        json.dumps(
            {
                "start_equity_usdt": 1000.0,
                "equity_usdt": 986.0,
                "realized_pnl_usdt": -14.0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EURIKA_MARKET_ROOT", str(tmp_path))
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            '{"type":"tool_calls","toolCalls":[{"tool":"market_status","arguments":{}}]}',
            '{"type":"final","text":"Market убыточен: equity ниже стартового банка."}',
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Как успехи Market?", "context": {}},
        [],
    )

    assert result["text"].startswith("Market убыточен")
    assert result["metrics"]["toolCalls"] == 1
    assert result["pendingToolCalls"] == []


def test_session_history_survives_restart_and_can_be_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    monkeypatch.setattr(
        runtime,
        "_call_model",
        lambda prompt: ('{"type":"final","text":"Persistent answer."}', None),
    )
    _runtime_call(runtime, "session/chat", {"message": "Remember this"}, [])

    restarted = LocalAgentRuntime(tmp_path)
    history = _runtime_call(restarted, "session/history", {"limit": 80}, [])
    assert history["messages"] == [
        {"role": "user", "content": "Remember this"},
        {"role": "assistant", "content": "Persistent answer."},
    ]
    created = _runtime_call(restarted, "session/create", {}, [])
    assert restarted._session(created["sessionId"]).messages == history["messages"]

    assert _runtime_call(restarted, "session/clear", {}, []) == {"cleared": True}
    assert _runtime_call(restarted, "session/history", {}, [])["messages"] == []
    assert restarted._session(created["sessionId"]).messages == []


def test_session_continues_after_approved_edit_with_structured_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    prompts: list[str] = []
    replies = iter(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [
                        {
                            "callId": "edit-1",
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
            '{"type":"final","text":"The approved change is complete."}',
        ]
    )

    def model(prompt: str) -> tuple[str, None]:
        prompts.append(prompt)
        return next(replies), None

    monkeypatch.setattr(runtime, "_call_model", model)
    session_id = _runtime_call(runtime, "session/create", {}, [])["sessionId"]
    prepared = _runtime_call(
        runtime,
        "session/chat",
        {"sessionId": session_id, "message": "Update the sample"},
        [],
    )
    pending = prepared["pendingToolCalls"][0]
    outcome = _runtime_call(
        runtime,
        "proposal/apply",
        {"proposalId": pending["proposal"]["proposalId"], "approval": True},
        [],
    )
    completed = _runtime_call(
        runtime,
        "session/chat",
        {
            "sessionId": session_id,
            "toolResults": [
                {
                    "callId": pending["callId"],
                    "tool": pending["tool"],
                    "result": {"decision": "applied", "outcome": outcome},
                }
            ],
        },
        [],
    )

    assert target.read_text(encoding="utf-8") == "new"
    assert completed["text"] == "The approved change is complete."
    assert "use the edit tool and return the proposal for approval" in prompts[0]
    assert '"decision": "applied"' in prompts[-1]
    assert _runtime_call(runtime, "session/history", {}, [])["messages"] == [
        {"role": "user", "content": "Update the sample"},
        {"role": "assistant", "content": "The approved change is complete."},
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
    descriptor = result["pendingToolCalls"][0]["proposal"]
    assert "after" not in descriptor["files"][0]
    preview = _runtime_call(
        runtime,
        "proposal/get",
        {"proposalId": descriptor["proposalId"], "path": "sample.txt"},
        [],
    )
    assert preview["files"][0]["after"] == "new"


def test_implement_request_nudges_model_to_emit_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            '{"type":"final","text":"I would change sample.txt to new."}',
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [
                        {
                            "callId": "edit-1",
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
        {"message": "Implement a one-line fix in sample.txt", "context": {}},
        [],
    )
    assert target.read_text(encoding="utf-8") == "old"
    assert result["pendingToolCalls"][0]["tool"] == "edit"
    assert result["pendingToolCalls"][0]["arguments"]["newText"] == "new"
    assert "Prepared tool action" in result["text"]


def test_core_proposal_supports_granular_apply_reject_and_restore(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    proposal = _runtime_call(
        runtime,
        "proposal/prepare",
        {
            "edits": [
                {"path": "a.txt", "oldText": "one", "newText": "ONE"},
                {"path": "b.txt", "oldText": "two", "newText": "TWO"},
            ]
        },
        [],
    )

    applied = _runtime_call(
        runtime,
        "proposal/apply",
        {"proposalId": proposal["proposalId"], "paths": ["a.txt"], "approval": True},
        [],
    )
    assert applied["applied"] == ["a.txt"]
    assert applied["remaining"] == ["b.txt"]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "ONE"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "two"

    rejected = _runtime_call(
        runtime,
        "proposal/reject",
        {"proposalId": proposal["proposalId"], "paths": ["b.txt"]},
        [],
    )
    assert rejected["remaining"] == []
    restored = _runtime_call(
        runtime,
        "checkpoint/restore",
        {"checkpointId": applied["checkpointId"], "approval": True},
        [],
    )
    assert restored == {
        "checkpointId": applied["checkpointId"],
        "restored": ["a.txt"],
        "conflicts": [],
    }
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one"


def test_core_proposal_rejects_stale_apply_and_restore_conflict(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    proposal = _runtime_call(
        runtime,
        "proposal/prepare",
        {"path": "sample.txt", "content": "new"},
        [],
    )
    target.write_text("user edit", encoding="utf-8")
    with pytest.raises(RpcError):
        _runtime_call(
            runtime,
            "proposal/apply",
            {"proposalId": proposal["proposalId"], "approval": True},
            [],
        )


def test_core_proposal_checks_editor_version_before_preview(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    version = runtime.tools.read(
        {"path": "sample.txt"},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )["version"]
    target.write_text("user edit", encoding="utf-8")

    with pytest.raises(RpcError):
        _runtime_call(
            runtime,
            "proposal/prepare",
            {"path": "sample.txt", "content": "agent edit", "expectedVersion": version},
            [],
        )


def test_core_proposal_rolls_back_when_checkpoint_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    proposal = _runtime_call(
        runtime,
        "proposal/prepare",
        {
            "edits": [
                {"path": "first.txt", "content": "ONE"},
                {"path": "second.txt", "content": "TWO"},
            ]
        },
        [],
    )
    monkeypatch.setattr(
        runtime.proposals,
        "_write_checkpoints",
        lambda _checkpoints: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OSError, match="disk full"):
        _runtime_call(
            runtime,
            "proposal/apply",
            {"proposalId": proposal["proposalId"], "approval": True},
            [],
        )

    assert first.read_text(encoding="utf-8") == "one"
    assert second.read_text(encoding="utf-8") == "two"


def test_core_proposal_rejects_unknown_selected_path(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("old", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    proposal = _runtime_call(
        runtime,
        "proposal/prepare",
        {"path": "sample.txt", "content": "new"},
        [],
    )
    with pytest.raises(RpcError):
        _runtime_call(
            runtime,
            "proposal/reject",
            {"proposalId": proposal["proposalId"], "paths": ["other.txt"]},
            [],
        )


def test_product_panels_are_serializable_without_qt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EURIKA_MARKET_ROOT", str(tmp_path))
    ml = tmp_path / ".eurika" / "ml"
    ml.mkdir(parents=True)
    (ml / "paper_portfolio.json").write_text(
        json.dumps({"equity_usdt": 1001.5}),
        encoding="utf-8",
    )
    (ml / "market_journal.jsonl").write_text(
        json.dumps({"kind": "learn", "message": "trained"}) + "\n",
        encoding="utf-8",
    )
    runtime = LocalAgentRuntime(tmp_path)

    market = _runtime_call(runtime, "panel/state", {"panel": "market"}, [])
    commands = _runtime_call(runtime, "panel/state", {"panel": "commands"}, [])
    approvals = _runtime_call(runtime, "panel/state", {"panel": "approvals"}, [])

    assert market["data"]["portfolio"]["equity_usdt"] == 1001.5
    assert market["data"]["events"][0]["message"] == "trained"
    assert "scan" in {item["id"] for item in commands["commands"]}
    assert approvals["data"]["error"] == "no pending plan"


def test_read_missing_file_is_invalid_params_not_internal(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path)
    with pytest.raises(RpcError) as error:
        tools.read(
            {"path": "local_agent_handshake.py"},
            cancel=threading.Event(),
            emit=lambda *_: None,
        )
    assert error.value.code == ERR_INVALID_PARAMS
    assert error.value.code != ERR_INTERNAL
    assert error.value.data == {"path": "local_agent_handshake.py"}

    runtime = LocalAgentRuntime(tmp_path)
    session = _runtime_call(runtime, "session/create", {}, [])
    with pytest.raises(RpcError) as call_error:
        _runtime_call(
            runtime,
            "tool/call",
            {
                "sessionId": session["sessionId"],
                "tool": "read",
                "arguments": {"path": "local_agent_handshake.py"},
            },
            [],
        )
    assert call_error.value.code == ERR_INVALID_PARAMS


def test_session_chat_missing_read_continues_with_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [
                        {
                            "tool": "read",
                            "arguments": {"path": "local_agent_handshake.py"},
                        }
                    ],
                }
            ),
            '{"type":"final","text":"Handshake is initialize in eurika.agent, not that filename."}',
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert result["text"].startswith("Handshake is initialize")
    assert result["metrics"]["toolCallErrors"] == 1
    assert result["pendingToolCalls"] == []


def test_session_chat_model_failure_stays_in_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = LocalAgentRuntime(tmp_path)
    monkeypatch.setattr(
        runtime,
        "_call_model",
        lambda prompt: ("", "ollama CLI skipped: prompt is 48000 chars (limit 12000); use HTTP"),
    )

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the handshake?"},
        [],
    )

    assert result["text"].startswith("Модель не ответила.")
    assert "ollama CLI skipped" in result["text"]
    assert result["pendingToolCalls"] == []


def test_session_chat_synthesizes_after_tool_loop_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "stdio.py").write_text("def initialize():\n    return capabilities\n", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    prompts: list[str] = []

    def model(prompt: str) -> tuple[str, None]:
        prompts.append(prompt)
        if "LAST TURN" in prompt:
            return '{"type":"final","text":"Handshake is initialize() in stdio.py."}', None
        return (
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "stdio.py"}}],
                }
            ),
            None,
        )

    monkeypatch.setattr(runtime, "_call_model", model)
    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert result["text"] == "Handshake is initialize() in stdio.py."
    assert any("LAST TURN" in prompt for prompt in prompts)
    assert result["metrics"]["toolCalls"] == 5


def test_session_chat_rejects_invented_implementation_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "eurika" / "runtime.py").write_text(
        "def capabilities():\n    return {}\n",
        encoding="utf-8",
    )
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            '{"type":"final","text":"eurika/local_agent/handshake.py"}',
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "eurika/runtime.py"}}],
                }
            ),
            '{"type":"final","text":"Handshake is capabilities() in eurika/runtime.py."}',
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert result["text"] == "Handshake is capabilities() in eurika/runtime.py."
    assert "handshake.py" not in result["text"]
    assert result["metrics"]["toolCalls"] == 1


def test_parse_model_response_unwraps_fenced_json_with_rate_limit_footer() -> None:
    raw = (
        '```json\n{"type":"final","text":"Handshake is capabilities() in eurika/runtime.py."}\n```\n\n'
        "—\nЛимит Groq достигнут. Снова можно использовать через ~40 мин (около 09:16). "
        "Пока отвечаю через локальный Ollama"
    )
    parsed = LocalAgentRuntime._parse_model_response(raw)
    body, notice = LocalAgentRuntime._split_model_notice(raw)
    assert parsed["type"] == "final"
    assert parsed["text"] == "Handshake is capabilities() in eurika/runtime.py."
    assert "Лимит Groq" in notice
    assert "```" not in parsed["text"]


def test_parse_model_response_executes_unclosed_fenced_tool_calls() -> None:
    raw = (
        '```json\n{"type":"tool_calls","toolCalls":'
        '[{"tool":"search","arguments":{"query":"LocalAgentRuntime","mode":"symbol"}}]}'
    )
    parsed = LocalAgentRuntime._parse_model_response(raw)
    assert parsed["type"] == "tool_calls"
    assert parsed["toolCalls"][0]["tool"] == "search"
    assert parsed["toolCalls"][0]["arguments"]["query"] == "LocalAgentRuntime"


def test_parse_model_response_same_line_fence_with_nested_arguments() -> None:
    raw = (
        '```json {"type":"tool_calls","toolCalls":'
        '[{"tool":"search","arguments":{"query":"Qt Chat HITL git commit"}}]} ```'
    )
    parsed = LocalAgentRuntime._parse_model_response(raw)
    assert parsed["type"] == "tool_calls"
    assert parsed["toolCalls"][0]["tool"] == "search"
    assert parsed["toolCalls"][0]["arguments"]["query"] == "Qt Chat HITL git commit"


def test_session_chat_rejects_test_file_as_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "eurika" / "runtime.py").write_text("def capabilities():\n    return {}\n", encoding="utf-8")
    (tmp_path / "tests" / "test_runtime.py").write_text(
        "def test_handshake_advertises_capabilities():\n    assert True\n",
        encoding="utf-8",
    )
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "tests/test_runtime.py"}}],
                }
            ),
            '{"type":"final","text":"The local agent handshake is implemented in tests/test_runtime.py."}',
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "eurika/runtime.py"}}],
                }
            ),
            '{"type":"final","text":"Handshake is capabilities() in eurika/runtime.py."}',
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert result["text"] == "Handshake is capabilities() in eurika/runtime.py."
    assert "tests/test_runtime.py" not in result["text"]


def test_session_chat_executes_bare_tool_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "eurika" / "stdio.py").write_text(
        "def initialize():\n    '''local agent handshake'''\n    return capabilities\n",
        encoding="utf-8",
    )
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            json.dumps(
                {
                    "tool": "search",
                    "arguments": {
                        "query": "handshake",
                        "path": "",
                        "maxResults": 20,
                        "mode": "text",
                    },
                }
            ),
            '{"type":"final","text":"Handshake is initialize() in eurika/stdio.py."}',
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Где в коде реализован handshake локального агента?"},
        [],
    )

    assert result["text"].startswith("Handshake is initialize()")
    assert "eurika/stdio.py" in result["text"]
    assert '"tool"' not in result["text"]
    assert result["metrics"]["toolCalls"] >= 1
    assert result["pendingToolCalls"] == []


def test_session_chat_does_not_render_protocol_json_after_groq_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "eurika" / "runtime.py").write_text("def capabilities():\n    return {}\n", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)
    replies = iter(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "eurika/runtime.py"}}],
                }
            ),
            (
                '```json\n{"type":"final","text":"Handshake is capabilities() in eurika/runtime.py."}\n```\n\n'
                "—\nЛимит Groq достигнут. Снова можно использовать через ~40 мин (около 09:16). "
                "Пока отвечаю через локальный Ollama"
            ),
        ]
    )
    monkeypatch.setattr(runtime, "_call_model", lambda prompt: (next(replies), None))

    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert result["text"].startswith("Handshake is capabilities() in eurika/runtime.py.")
    assert "```" not in result["text"]
    assert '"type"' not in result["text"]
    assert "Лимит Groq" in result["text"]


def test_session_chat_does_not_ship_invented_path_after_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eurika").mkdir()
    (tmp_path / "eurika" / "runtime.py").write_text("def capabilities():\n    pass\n", encoding="utf-8")
    runtime = LocalAgentRuntime(tmp_path)

    def model(prompt: str) -> tuple[str, None]:
        if "LAST TURN" in prompt:
            return '{"type":"final","text":"eurika/local_agent/handshake.py"}', None
        return (
            json.dumps(
                {
                    "type": "tool_calls",
                    "toolCalls": [{"tool": "read", "arguments": {"path": "eurika/runtime.py"}}],
                }
            ),
            None,
        )

    monkeypatch.setattr(runtime, "_call_model", model)
    result = _runtime_call(
        runtime,
        "session/chat",
        {"message": "Where is the local agent handshake implemented?"},
        [],
    )

    assert "handshake.py" not in result["text"]
    assert "eurika/runtime.py" in result["text"]


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


def test_resolve_accepts_absolute_path_inside_workspace(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "qt_app"
    nested.mkdir(parents=True)
    target = nested / "main_window.py"
    target.write_text("ok", encoding="utf-8")
    tools = WorkspaceTools(root)
    resolved = tools.resolve(str(target.resolve()))
    assert resolved == target.resolve()
    runtime = LocalAgentRuntime(root)
    proposal = _runtime_call(
        runtime,
        "proposal/prepare",
        {"path": str(target.resolve()), "content": "changed"},
        [],
    )
    assert proposal["files"][0]["path"] == "qt_app/main_window.py"


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


def test_stdio_loads_workspace_dotenv_for_llm_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=gsk-desktop-test\nOPENAI_BASE_URL=https://api.groq.com/openai/v1\n",
        encoding="utf-8",
    )

    configure_workspace_env(tmp_path)

    assert os.environ["OPENAI_API_KEY"] == "gsk-desktop-test"
    assert os.environ["OPENAI_BASE_URL"] == "https://api.groq.com/openai/v1"


def test_stdio_rewrites_retired_groq_llama_in_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=gsk-desktop-test\n"
        "OPENAI_BASE_URL=https://api.groq.com/openai/v1\n"
        "OPENAI_MODEL=llama-3.3-70b-versatile\n",
        encoding="utf-8",
    )

    configure_workspace_env(tmp_path)

    assert os.environ["OPENAI_MODEL"] == "openai/gpt-oss-120b"
    assert "OPENAI_MODEL=openai/gpt-oss-120b" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_redirect_library_stdout_keeps_rpc_channel_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", rpc)
    monkeypatch.setattr(sys, "stderr", err)
    writer = redirect_library_stdout()
    print("LiteLLM.Info: If you need to debug this error")
    writer.write('{"jsonrpc":"2.0"}\n')
    assert "LiteLLM" not in writer.getvalue()
    assert "LiteLLM" in err.getvalue()
    assert '{"jsonrpc":"2.0"}' in writer.getvalue()


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


def test_stdio_internal_error_preserves_exception_type_and_detail(tmp_path: Path) -> None:
    class BrokenRuntime(LocalAgentRuntime):
        def dispatch(self, method, params, *, cancel, emit):
            raise ValueError("broken response")

    request = {"jsonrpc": "2.0", "id": 8, "method": "session/chat", "params": {}}
    writer = io.StringIO()
    JsonRpcStdioServer(
        BrokenRuntime(tmp_path),
        reader=io.StringIO(json.dumps(request) + "\n"),
        writer=writer,
    ).serve_forever()
    response = json.loads(writer.getvalue())
    assert response["error"]["code"] == ERR_INTERNAL
    assert response["error"]["data"]["detail"] == "ValueError: broken response"


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
