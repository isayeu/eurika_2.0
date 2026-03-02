"""History and context tests for eurika.api.chat (split from test_chat_api)."""

import json
from pathlib import Path


def test_append_chat_history_records_timezone_aware_utc_timestamp(tmp_path: Path) -> None:
    """append_chat_history should write UTC timestamp in Z-suffixed ISO format."""
    from eurika.api.chat import append_chat_history

    append_chat_history(tmp_path, "user", "hello", None)
    log_path = tmp_path / ".eurika" / "chat_history" / "chat.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    ts = payload.get("ts") or ""
    assert ts.endswith("Z")
    assert "T" in ts


def test_build_chat_context_with_scope_includes_focus_and_prioritize(tmp_path: Path) -> None:
    """R5 2.3: @-mentions scope enriches context with focus, prioritize hint, and scoped risks."""
    from eurika.api.chat import _build_chat_context

    (tmp_path / "self_map.json").write_text(
        '{"modules":[{"path":"a.py","lines":10},{"path":"b.py","lines":10}],'
        '"dependencies":{"a.py":["b.py"]},"summary":{"files":2,"total_lines":20}}',
        encoding="utf-8",
    )
    scope = {"modules": ["a.py"], "smells": ["god_module"]}
    ctx = _build_chat_context(tmp_path, scope=scope)
    assert "Focus module(s): a.py" in ctx
    assert "Focus smell(s): god_module" in ctx
    assert "Prioritize answers regarding the focused scope" in ctx
    assert "Project:" in ctx or "Scoped module details" in ctx


def test_append_chat_history_truncates_content_and_context(tmp_path: Path) -> None:
    """append_chat_history should cap content and context snapshot lengths."""
    from eurika.api.chat import append_chat_history

    append_chat_history(tmp_path, "assistant", "x" * 12000, "y" * 900)
    log_path = tmp_path / ".eurika" / "chat_history" / "chat.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert len(payload.get("content") or "") == 10000
    assert len(payload.get("context_snapshot") or "") == 500


def test_append_chat_history_stores_none_context_when_empty(tmp_path: Path) -> None:
    """append_chat_history should store null context_snapshot when context is empty."""
    from eurika.api.chat import append_chat_history

    append_chat_history(tmp_path, "assistant", "ok", "")
    payload = json.loads((tmp_path / ".eurika" / "chat_history" / "chat.jsonl").read_text(encoding="utf-8").strip())
    assert payload.get("context_snapshot") is None


def test_chat_send_works_with_preexisting_corrupted_chat_jsonl(tmp_path: Path, monkeypatch) -> None:
    """chat_send should remain functional even when chat.jsonl has corrupted prior lines."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    chat_dir = tmp_path / ".eurika" / "chat_history"
    chat_dir.mkdir(parents=True, exist_ok=True)
    (chat_dir / "chat.jsonl").write_text("{bad json line\n", encoding="utf-8")

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("recall", "name"))
    monkeypatch.setattr(chat_mod, "_load_user_context", lambda _root: {"name": "Alex"})
    out = chat_mod.chat_send(tmp_path, "what is my name")
    assert out.get("error") is None
    assert "Тебя зовут Alex." in (out.get("text") or "")
    # Ensure new valid line can still be appended after corrupted content.
    lines = (chat_dir / "chat.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 3
