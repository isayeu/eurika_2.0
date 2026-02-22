"""Domain-level edge-case tests for eurika.api.chat."""

from pathlib import Path


def test_chat_send_empty_message_returns_error(tmp_path: Path) -> None:
    """Empty/whitespace message should be rejected deterministically."""
    from eurika.api.chat import chat_send

    out = chat_send(tmp_path, "   ")
    assert out.get("text") == ""
    assert out.get("error") == "message is empty"


def test_chat_send_llm_error_tolerates_history_write_failure(tmp_path: Path, monkeypatch) -> None:
    """LLM error path should not crash even if history append raises."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: (None, None))
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("", "llm offline"))
    monkeypatch.setattr(chat_mod, "append_chat_history", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))

    out = chat_mod.chat_send(tmp_path, "hello")
    assert out.get("text") == ""
    assert out.get("error") == "llm offline"


def test_chat_send_save_intent_invalid_path_does_not_write(tmp_path: Path, monkeypatch) -> None:
    """Save intent with unsafe target path should not create files."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "../hack.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None))

    out = chat_mod.chat_send(tmp_path, "save it")
    assert out.get("error") is None
    assert "[Сохранено в " not in (out.get("text") or "")
    assert not (tmp_path / "hack.py").exists()


def test_chat_send_save_intent_writes_code_and_marks_output(tmp_path: Path, monkeypatch) -> None:
    """Save intent should persist extracted code and append saved marker."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "foo.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None))

    out = chat_mod.chat_send(tmp_path, "save it")
    assert out.get("error") is None
    assert "[Сохранено в foo.py" in (out.get("text") or "")
    assert (tmp_path / "foo.py").read_text(encoding="utf-8") == "x = 1\n"


def test_chat_send_delete_intent_invalid_path_returns_failure(tmp_path: Path, monkeypatch) -> None:
    """Delete intent should reject unsafe path traversal target."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("delete", "../danger.py"))
    out = chat_mod.chat_send(tmp_path, "delete")
    assert out.get("error") is None
    assert "Не удалось удалить: invalid path" in (out.get("text") or "")


def test_chat_send_create_intent_invalid_path_returns_failure(tmp_path: Path, monkeypatch) -> None:
    """Create intent should reject unsafe path traversal target."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("create", "../danger.py"))
    out = chat_mod.chat_send(tmp_path, "create")
    assert out.get("error") is None
    assert "Не удалось создать: invalid path" in (out.get("text") or "")


def test_chat_send_refactor_dry_run_calls_fix_with_dry_flag(tmp_path: Path, monkeypatch) -> None:
    """Refactor intent with dry-run phrase should trigger fix dry_run=True."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    called: dict[str, object] = {}

    def _fake_run_fix(_root, dry_run=False, timeout=180):
        called["dry_run"] = dry_run
        called["timeout"] = timeout
        return "ok"

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("refactor", None))
    monkeypatch.setattr(chat_mod, "_run_eurika_fix", _fake_run_fix)

    out = chat_mod.chat_send(tmp_path, "please refactor dry-run")
    assert out.get("error") is None
    assert called.get("dry_run") is True


def test_chat_send_remember_tolerates_save_context_failure(tmp_path: Path, monkeypatch) -> None:
    """Remember intent should not crash if user-context persistence fails."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("remember", "name:Alex"))
    monkeypatch.setattr(chat_mod, "_save_user_context", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("ro fs")))

    out = chat_mod.chat_send(tmp_path, "remember my name")
    assert out.get("error") is None
    assert "Запомнил" in (out.get("text") or "")


def test_chat_send_recall_returns_unknown_when_context_missing(tmp_path: Path, monkeypatch) -> None:
    """Recall intent should return deterministic fallback when name absent."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("recall", "name"))
    monkeypatch.setattr(chat_mod, "_load_user_context", lambda _root: {})

    out = chat_mod.chat_send(tmp_path, "what is my name")
    assert out.get("error") is None
    assert "Я не знаю, как тебя зовут" in (out.get("text") or "")
