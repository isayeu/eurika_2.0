"""Domain-level edge-case tests for eurika.api.chat."""

import json
from pathlib import Path


def test_extract_commit_message_from_request_regex() -> None:
    """Regex extraction for explicit commit message patterns (ROADMAP 3.6.8)."""
    from eurika.api.chat_direct import extract_commit_message_from_request

    msg = "Собери коммит. В сообщении напиши: ROADMAP 3.6.8 Phase 1–4"
    assert extract_commit_message_from_request(msg) == "ROADMAP 3.6.8 Phase 1–4"
    assert extract_commit_message_from_request("собери коммит с сообщением fix docs") == "fix docs"
    assert extract_commit_message_from_request(
        "git commit с сообщением: Add chat pending Diff preview"
    ) == "Add chat pending Diff preview"
    assert extract_commit_message_from_request("собери коммит") is None


def test_chat_send_git_commit_uses_llm_when_user_gives_context(tmp_path: Path, monkeypatch) -> None:
    """When user gives context (not just 'собери коммит'), LLM infers commit message (ROADMAP 3.6.8)."""
    import subprocess

    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda prompt, max_tokens=80: ("ROADMAP 3.6.8 Phase 1-4, порядок в секции 3.6", None),
    )
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")

    out = chat_mod.chat_send(tmp_path, "Собери коммит. В сообщении напиши: ROADMAP 3.6.8 Phase 1–4, порядок в секции 3.6")
    text = out.get("text") or ""
    assert "ROADMAP" in text
    # Regex should extract first, so we get exact match
    assert "3.6.8" in text or "Phase" in text

    # Test LLM path: no regex match, user gave context
    out2 = chat_mod.chat_send(tmp_path, "закоммить изменения, хочу чтобы в сообщении было про chat tools и feedback")
    text2 = out2.get("text") or ""
    # LLM is mocked to return our message for any prompt; with context, we use LLM
    assert "применяй" in text2 or "Нет изменений" in text2


def test_save_chat_feedback_writes_json(tmp_path: Path) -> None:
    """save_chat_feedback should append entry to .eurika/chat_feedback.json (ROADMAP 3.6.8 Phase 3)."""
    from eurika.api.chat import save_chat_feedback

    save_chat_feedback(tmp_path, "hello", "hi there", helpful=True)
    path = tmp_path / ".eurika" / "chat_feedback.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    assert len(entries) == 1
    assert entries[0]["user_message"] == "hello"
    assert entries[0]["assistant_message"] == "hi there"
    assert entries[0]["helpful"] is True
    assert entries[0].get("clarification") is None

    save_chat_feedback(tmp_path, "x", "y", helpful=False, clarification="meant Z")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    assert len(entries) == 2
    assert entries[1]["helpful"] is False
    assert entries[1]["clarification"] == "meant Z"


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
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("", "llm offline"))
    monkeypatch.setattr(chat_mod, "append_chat_history", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))

    out = chat_mod.chat_send(tmp_path, "проанализируй код")
    assert out.get("text") == ""
    assert out.get("error") == "llm offline"


def test_chat_send_save_intent_allows_one_level_up_path(tmp_path: Path, monkeypatch) -> None:
    """Save intent may write into parent directory (one level above root)."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "../hack.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None))

    out = chat_mod.chat_send(tmp_path, "save it")
    assert out.get("error") is None
    assert "[Сохранено в " in (out.get("text") or "")
    assert (tmp_path.parent / "hack.py").exists()


def test_chat_send_save_intent_blocks_path_above_parent(tmp_path: Path, monkeypatch) -> None:
    """Save intent must not write above allowed parent-level sandbox."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "../../hack.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None))

    out = chat_mod.chat_send(tmp_path, "save it")
    assert out.get("error") is None
    assert "[Сохранено в " not in (out.get("text") or "")
    assert not (tmp_path.parent.parent / "hack.py").exists()


def test_chat_send_save_intent_writes_code_and_marks_output(tmp_path: Path, monkeypatch) -> None:
    """Save intent should persist extracted code and append saved marker."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "foo.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(architect_mod, "call_llm_with_prompt", lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None))

    out = chat_mod.chat_send(tmp_path, "save it")
    assert out.get("error") is None
    assert "[Сохранено в foo.py" in (out.get("text") or "")
    assert (tmp_path / "foo.py").read_text(encoding="utf-8") == "x = 1\n"


def test_chat_send_save_intent_without_target_uses_default_app_py(tmp_path: Path, monkeypatch) -> None:
    """Save intent without explicit target should persist code into default app.py."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", None))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "print('Hello, World!')\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(
        architect_mod,
        "call_llm_with_prompt",
        lambda _prompt, max_tokens=1024: ("```python\nprint('Hello, World!')\n```", None),
    )

    out = chat_mod.chat_send(tmp_path, "напиши приложение hello world и сохрани")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "[Сохранено в app.py" in text
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "print('Hello, World!')\n"


def test_chat_send_show_report_returns_doctor_report_without_llm(tmp_path: Path, monkeypatch) -> None:
    """When user asks for report and eurika_doctor_report.json exists, return formatted report without LLM."""
    import eurika.api.chat as chat_mod

    doctor_data = {
        "summary": {
            "system": {"modules": 42, "dependencies": 20, "cycles": 0},
            "risks": ["god_module @ foo.py (severity=10.00)"],
        },
        "architect": "Short architect take.",
    }
    (tmp_path / "eurika_doctor_report.json").write_text(
        json.dumps(doctor_data), encoding="utf-8"
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "покажи отчет")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "42" in text or "Модули" in text or "god_module" in text


def test_chat_send_show_report_no_file_returns_hint(tmp_path: Path, monkeypatch) -> None:
    """When no report exists, return hint to run scan/doctor."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сформируй отчет")
    assert out.get("error") is None
    assert "scan" in (out.get("text") or "").lower() or "doctor" in (out.get("text") or "").lower()


def test_chat_send_show_file_returns_contents_without_llm(tmp_path: Path, monkeypatch) -> None:
    """When user asks to show file and path exists, return file contents without LLM (CR-A1)."""
    import eurika.api.chat as chat_mod

    (tmp_path / ".eurika" / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "rules" / "eurika.mdc").write_text(
        "---\ndescription: test\n---\n# Eurika rules", encoding="utf-8"
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "покажи файл .eurika/rules/eurika.mdc")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Eurika rules" in text
    assert ".eurika/rules/eurika.mdc" in text


def test_chat_send_add_api_test_creates_test(tmp_path: Path, monkeypatch) -> None:
    """CR-B1: 'добавь тест для /api/foo' in Eurika chat adds test to test_api_serve.py."""
    import eurika.api.chat as chat_mod

    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_api_serve.py").write_text(
        '"""Tests."""\nfrom eurika.api import serve as api_serve\n\nclass _DummyHandler:\n    pass\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "добавь тест для /api/summary")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Добавлен" in text or "тест" in text.lower()
    content = (tmp_path / "tests" / "test_api_serve.py").read_text(encoding="utf-8")
    assert '"/api/summary"' in content
    assert "test_dispatch_api_get_summary" in content
