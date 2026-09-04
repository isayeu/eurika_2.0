"""Live API/agent activity log for Chat, Terminal, and Desktop."""

from __future__ import annotations

from pathlib import Path

from eurika.agent.live_activity import (
    activity_path,
    consume_jsonl,
    publish_done,
    publish_start,
    recent,
)


def test_publish_and_consume_start_then_done(tmp_path: Path) -> None:
    started = publish_start(
        tmp_path, "POST /api/chat", {"message": "прочитай deep_nesting"}, client="http"
    )
    assert started["phase"] == "start"
    assert "deep_nesting" in started["title"]
    publish_done(
        tmp_path,
        started,
        ok=True,
        result={
            "text": "literal 3",
            "terminal_cmd": "$ sed -n '1,8p' x.py",
            "terminal_output": "ok",
            "approvalsQueued": 1,
        },
    )
    payload = recent(tmp_path, after_offset=0)
    phases = [event["phase"] for event in payload["events"]]
    assert phases == ["start", "done"]
    assert payload["events"][-1].get("approvalsQueued") == 1
    assert payload["offset"] > 0
    more, offset = consume_jsonl(activity_path(tmp_path), payload["offset"])
    assert more == []
    assert offset == payload["offset"]


def test_api_chat_writes_activity_before_reply(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.serve_routes_post import dispatch_api_post

    captured: dict[str, object] = {}

    class Handler:
        pass

    def _json(handler, data, status=200):
        captured["data"] = data
        captured["status"] = status

    monkeypatch.setattr("eurika.api.serve_routes_post._json_response", _json)
    monkeypatch.setattr(
        "eurika.api.chat.chat_send",
        lambda *_a, **_k: {"text": "34", "error": None},
    )
    assert dispatch_api_post(Handler(), tmp_path, "/api/chat", {"message": "extractable 5"})
    events = recent(tmp_path)["events"]
    assert events[0]["phase"] == "start"
    assert events[0]["method"] == "POST /api/chat"
    assert events[-1]["phase"] == "done"
    assert events[-1]["ok"] is True
    assert captured["data"]["text"] == "34"


def test_runtime_activity_recent_rpc(tmp_path: Path) -> None:
    import threading

    from eurika.agent.local_runtime import LocalAgentRuntime

    publish_start(tmp_path, "session/chat", {"message": "hi"}, client="agent")
    runtime = LocalAgentRuntime(tmp_path)
    result = runtime.dispatch(
        "activity/recent",
        {"afterOffset": 0, "limit": 10},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )
    assert result["events"]
    assert result["events"][0]["method"] == "session/chat"
    assert "activity/recent" in runtime.capabilities()["methods"]
