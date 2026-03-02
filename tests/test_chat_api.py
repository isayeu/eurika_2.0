"""Domain-level edge-case tests for eurika.api.chat."""

import json
from pathlib import Path


def test_extract_commit_message_from_request_regex() -> None:
    """Regex extraction for explicit commit message patterns (ROADMAP 3.6.8)."""
    from eurika.api.chat import _extract_commit_message_from_request

    msg = "Собери коммит. В сообщении напиши: ROADMAP 3.6.8 Phase 1–4"
    assert _extract_commit_message_from_request(msg) == "ROADMAP 3.6.8 Phase 1–4"
    assert _extract_commit_message_from_request("собери коммит с сообщением fix docs") == "fix docs"
    assert _extract_commit_message_from_request("собери коммит") is None


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

    out = chat_mod.chat_send(tmp_path, "hello")
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


def test_chat_send_add_module_test_creates_test_file(tmp_path: Path, monkeypatch) -> None:
    """'добавь тест для eurika/polygon/long_function.py' creates tests/test_eurika_polygon_long_function.py."""
    import eurika.api.chat as chat_mod

    (tmp_path / "eurika" / "polygon").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eurika" / "polygon" / "long_function.py").write_text(
        '"""Dummy module."""\ndef foo(): return 42\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "добавь тест для eurika/polygon/long_function.py")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Добавлен" in text
    test_file = tmp_path / "tests" / "test_eurika_polygon_long_function.py"
    assert test_file.exists()
    content = test_file.read_text(encoding="utf-8")
    assert "eurika.polygon.long_function" in content
    assert "test_module_imports" in content


def test_chat_send_add_api_test_creates_file_if_missing(tmp_path: Path, monkeypatch) -> None:
    """CR-B1: when tests/test_api_serve.py missing, create it and add test — доступ везде."""
    import eurika.api.chat as chat_mod

    # No tests/ dir, no test_api_serve.py
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "добавь тест для /api/summary")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Добавлен" in text or "тест" in text.lower()
    test_file = tmp_path / "tests" / "test_api_serve.py"
    assert test_file.exists()
    content = test_file.read_text(encoding="utf-8")
    assert '"/api/summary"' in content
    assert "test_dispatch_api_get_summary" in content
    assert "from eurika.api import serve" in content
    assert "class _DummyHandler" in content


def test_chat_send_release_check_runs_script(tmp_path: Path, monkeypatch) -> None:
    """CR-B2: 'прогони release check' runs release_check.sh and returns output."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_tools as tools_mod

    def _fake_ok(_root, timeout=300):
        return (True, "==> Release check PASSED")

    monkeypatch.setattr(tools_mod, "run_release_check", _fake_ok)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "release_check.sh").write_text("#!/bin/bash\nexit 0", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "прогони release check")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Release check" in text or "PASSED" in text


def test_chat_send_release_check_failure_stores_output(tmp_path: Path, monkeypatch) -> None:
    """CR-B2: when release check fails, output is stored for follow-up fix."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_tools as tools_mod

    def _fake_fail(_root, timeout=300):
        return (False, "FAIL: pytest tests/")

    monkeypatch.setattr(tools_mod, "run_release_check", _fake_fail)
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "release_check.sh").write_text("#!/bin/bash\nexit 1", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "прогони release check")
    text = out.get("text") or ""
    assert "не прошёл" in text or "FAIL" in text or "исправь" in text.lower()
    assert "FAIL: pytest tests/" in text
    from eurika.api.chat import _load_dialog_state
    st = _load_dialog_state(tmp_path)
    assert st.get("last_release_check_output") == "FAIL: pytest tests/"
    assert st.get("last_release_check_ok") is False


def test_chat_send_roadmap_verify_phase(tmp_path: Path, monkeypatch) -> None:
    """CR-B3: 'проверь фазу X.Y' runs roadmap verification and returns step report."""
    import eurika.api.chat as chat_mod

    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text("""
version: 1
intents:
  roadmap_verify:
    patterns: ["проверь фазу", "сверь roadmap", "verify phase"]
    emit: null
""", encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    roadmap = tmp_path / "docs" / "ROADMAP.md"
    roadmap.write_text("""
### Фаза 2.7 — Test Phase

| #      | Шаг    | Задача | Критерий готовности |
| ------ | ------ | ------ | ------------------- |
| 2.7.1  | Step A | ...    | ✅ foo_func; tests/test_foo.py |
| 2.7.2  | Step B | ...    | ✅ bar_module |
""", encoding="utf-8")
    (tmp_path / "eurika").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eurika" / "foo.py").write_text("def foo_func(): pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_foo.py").write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "проверь фазу 2.7")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "2.7" in text
    assert "2.7.1" in text or "Step A" in text


def test_chat_send_roadmap_verify_no_phase_hint(tmp_path: Path, monkeypatch) -> None:
    """CR-B3: 'сверь roadmap' without phase number returns hint."""
    import eurika.api.chat as chat_mod

    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text("""
version: 1
intents:
  roadmap_verify:
    patterns: ["проверь фазу", "сверь roadmap", "verify phase"]
    emit: null
""", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сверь roadmap")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "фазу" in text or "phase" in text.lower()


def test_chat_send_show_file_not_found_returns_hint(tmp_path: Path, monkeypatch) -> None:
    """When file does not exist, return error hint without LLM."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "покажи файл .eurika/rules/nonexistent.mdc")
    assert out.get("error") is None
    assert "не найден" in (out.get("text") or "").lower() or "not found" in (out.get("text") or "").lower()


def test_chat_send_full_path_query_returns_saved_file_abs_path(tmp_path: Path, monkeypatch) -> None:
    """After save, full-path query should return deterministic absolute path."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("save", "foo.py"))
    monkeypatch.setattr(intent_mod, "extract_code_block", lambda _text: "x = 1\n")
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(
        architect_mod,
        "call_llm_with_prompt",
        lambda _prompt, max_tokens=1024: ("```python\nx = 1\n```", None),
    )
    save_out = chat_mod.chat_send(tmp_path, "save it")
    assert save_out.get("error") is None

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "покажи полный путь к файлу")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert str((tmp_path / "foo.py").resolve()) in text


def test_chat_send_delete_intent_invalid_path_returns_failure(tmp_path: Path, monkeypatch) -> None:
    """Delete intent should require confirmation before execution."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("delete", "../danger.py"))
    out = chat_mod.chat_send(tmp_path, "delete")
    assert out.get("error") is None
    assert "Подтверди выполнение" in (out.get("text") or "")
    assert "delete" in (out.get("text") or "")


def test_chat_send_create_intent_invalid_path_returns_failure(tmp_path: Path, monkeypatch) -> None:
    """Create intent should require confirmation before execution."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("create", "../danger.py"))
    out = chat_mod.chat_send(tmp_path, "create")
    assert out.get("error") is None
    assert "Подтверди выполнение" in (out.get("text") or "")
    assert "create" in (out.get("text") or "")


def test_chat_send_refactor_dry_run_calls_fix_with_dry_flag(tmp_path: Path, monkeypatch) -> None:
    """Refactor intent should require confirmation in risk-based flow."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: ("refactor", None))

    out = chat_mod.chat_send(tmp_path, "please refactor dry-run")
    assert out.get("error") is None
    assert "Подтверди выполнение" in (out.get("text") or "")
    assert "refactor" in (out.get("text") or "")


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


def test_chat_prompt_includes_intent_interpretation_rules() -> None:
    """Chat prompt should include intent interpretation rules (ROADMAP 3.6.8 Phase 2)."""
    from eurika.api.chat import _build_chat_prompt

    prompt = _build_chat_prompt("hello", "ctx", history=None)
    assert "собери коммит" in prompt
    assert "ритуал" in prompt or "ritual" in prompt.lower()
    assert "покажи отчёт" in prompt or "отчёт" in prompt


def test_load_chat_feedback_injects_few_shot_into_prompt(tmp_path: Path) -> None:
    """When chat_feedback.json exists, prompt should include few-shot block (ROADMAP 3.6.8 Phase 4)."""
    from eurika.api.chat import _build_chat_prompt, _load_chat_feedback_for_prompt, save_chat_feedback

    save_chat_feedback(tmp_path, "запусти проверку", "ok", helpful=False, clarification="eurika doctor .")
    save_chat_feedback(tmp_path, "собери коммит", "status...", helpful=True)

    snippet = _load_chat_feedback_for_prompt(tmp_path)
    assert "Few-shot" in snippet
    assert "user meant" in snippet
    assert "eurika doctor" in snippet
    assert "correct" in snippet

    prompt = _build_chat_prompt("hi", "ctx", feedback_snippet=snippet)
    assert "Few-shot" in prompt
    assert "запусти проверку" in prompt or "eurika doctor" in prompt


def test_chat_send_identity_question_returns_eurika_persona(tmp_path: Path) -> None:
    """Identity question should be answered directly by Eurika persona."""
    from eurika.api.chat import chat_send

    out = chat_send(tmp_path, "ты кто?")
    assert out.get("error") is None
    assert "Я Eurika" in (out.get("text") or "")


def test_chat_send_rewrites_model_identity_leak(tmp_path: Path, monkeypatch) -> None:
    """LLM self-identification as base model should be normalized to Eurika."""
    import eurika.api.chat as chat_mod
    import eurika.api.chat_intent as intent_mod
    import eurika.reasoning.architect as architect_mod

    monkeypatch.setattr(intent_mod, "detect_intent", lambda _msg: (None, None))
    monkeypatch.setattr(chat_mod, "_build_chat_context", lambda _root, scope=None: "ctx")
    monkeypatch.setattr(
        architect_mod,
        "call_llm_with_prompt",
        lambda _prompt, max_tokens=1024: ("Я Qwen, ваш ассистент по коду.\nГотов помочь.", None),
    )

    out = chat_mod.chat_send(tmp_path, "привет")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Я Eurika" in text
    assert "Я Qwen" not in text


def test_chat_send_ls_request_returns_real_listing_without_llm(tmp_path: Path, monkeypatch) -> None:
    """ls request should return actual root listing and skip LLM path."""
    import eurika.api.chat as chat_mod

    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    out = chat_mod.chat_send(tmp_path, "ты можешь выполнить команду ls в корне своего проекта?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "a.py" in text
    assert "docs/" in text
    assert "README.md" in text


def test_chat_send_ritual_request_runs_scan_doctor_report_snapshot(tmp_path: Path, monkeypatch) -> None:
    """Ritual request should run eurika scan, doctor, report-snapshot (ROADMAP 3.6.8)."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    import eurika.api.chat as chat_mod

    out = chat_mod.chat_send(tmp_path, "проведи ритуал")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "eurika scan" in text or "scan" in text.lower()
    assert "Выполнил ритуал" in text or "ритуал" in text


def test_chat_send_git_commit_request_returns_real_status_without_llm(tmp_path: Path, monkeypatch) -> None:
    """Git commit request should return real git status/diff and skip LLM (ROADMAP 3.6.8 Phase 1)."""
    import subprocess

    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")

    out = chat_mod.chat_send(tmp_path, "собери коммит")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "git status" in text.lower() or "status" in text.lower()
    assert "применяй" in text or "Нет изменений" in text


def test_chat_send_git_commit_apply_executes_real_commit(tmp_path: Path, monkeypatch) -> None:
    """Apply confirmation after git commit request should execute real git commit."""
    import subprocess

    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
    (tmp_path / "y.py").write_text("b=2\n", encoding="utf-8")

    chat_mod.chat_send(tmp_path, "собери коммит")
    out = chat_mod.chat_send(tmp_path, "применяй")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "коммит" in text.lower() or "commit" in text.lower()
    r = subprocess.run(["git", "log", "-1", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0
    assert "Update" in r.stdout or "y.py" in r.stdout


def test_chat_send_tree_request_returns_real_tree_without_llm(tmp_path: Path, monkeypatch) -> None:
    """Tree request should return factual structure from filesystem."""
    import eurika.api.chat as chat_mod

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    out = chat_mod.chat_send(tmp_path, "а конкретно сейчас фактическую полную структуру?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "src/" in text
    assert "main.py" in text
    assert "tests/" in text
    assert "test_main.py" in text


def test_chat_send_ui_tabs_query_returns_grounded_tabs_without_llm(tmp_path: Path, monkeypatch) -> None:
    """UI tabs query should be answered from factual Qt shell state."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "какие вкладки есть в твоем UI?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Commands" in text
    assert "Dashboard" in text
    assert "Approvals" in text
    assert "Chat" in text


def test_chat_send_ui_tabs_count_query_returns_grounded_tabs_without_llm(tmp_path: Path, monkeypatch) -> None:
    """Count-style UI tabs query should also use grounded Qt tab list."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сколько у тебя вкладок в UI?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Commands" in text
    assert "Dashboard" in text
    assert "Approvals" in text
    assert "Chat" in text


def test_chat_send_structured_patch_json_creates_pending_plan(tmp_path: Path) -> None:
    import json as _json
    import eurika.api.chat as chat_mod

    payload = _json.dumps(
        {
            "intent": "code_edit_patch",
            "target": "a.py",
            "old_text": "x = 1",
            "new_text": "x = 2",
            "verify_target": "tests/test_ok.py",
        },
        ensure_ascii=False,
    )
    out = chat_mod.chat_send(tmp_path, payload)
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "code_edit_patch" in text
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    pending = state.get("pending_plan") or {}
    assert pending.get("intent") == "code_edit_patch"
    entities = pending.get("entities") or {}
    assert entities.get("verify_target") == "tests/test_ok.py"


def test_chat_send_structured_patch_batch_json_creates_pending_plan(tmp_path: Path) -> None:
    import json as _json
    import eurika.api.chat as chat_mod

    payload = _json.dumps(
        {
            "intent": "code_edit_patch",
            "operations": [
                {"target": "a.py", "old_text": "x = 1", "new_text": "x = 2"},
                {"target": "b.py", "old_text": "y = 1", "new_text": "y = 2"},
            ],
            "verify_target": "tests/test_ok.py",
        },
        ensure_ascii=False,
    )
    out = chat_mod.chat_send(tmp_path, payload)
    assert out.get("error") is None
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    pending = state.get("pending_plan") or {}
    assert pending.get("intent") == "code_edit_patch"
    entities = pending.get("entities") or {}
    assert entities.get("operations_json")
    assert entities.get("verify_target") == "tests/test_ok.py"


def test_chat_send_structured_patch_json_dry_run_sets_pending_flag(tmp_path: Path) -> None:
    import json as _json
    import eurika.api.chat as chat_mod

    payload = _json.dumps(
        {
            "schema_version": 1,
            "intent": "code_edit_patch",
            "target": "a.py",
            "old_text": "x = 1",
            "new_text": "x = 2",
            "dry_run": True,
        },
        ensure_ascii=False,
    )
    out = chat_mod.chat_send(tmp_path, payload)
    assert out.get("error") is None
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    pending = state.get("pending_plan") or {}
    entities = pending.get("entities") or {}
    assert entities.get("dry_run") == "1"


def test_chat_send_clarification_payload_with_catalog_word_does_not_trigger_tree(tmp_path: Path, monkeypatch) -> None:
    """Clarification payload mentioning root catalog should not be misdetected as tree request."""
    import json as _json
    import eurika.api.chat as chat_mod

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps({"pending_clarification": {"original": "хорошо, сделай это, когда будет готово"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    msg = (
        "цель: проверить твои возможности и функционал\n"
        "границы : в пределах своего корневого каталога и интерфейса.\n"
        "задачи : после вкладки Chat создать пустую вкладку"
    )
    out = chat_mod.chat_send(tmp_path, msg, history=[])
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Показываю фактическую структуру проекта" not in text
    assert "добавить пустую вкладку после `Chat`" in text


def test_chat_send_ambiguous_request_asks_clarification_without_llm(tmp_path: Path, monkeypatch) -> None:
    """Ambiguous imperative should request clarification instead of guessing."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сделай как лучше")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Уточни" in text
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    assert state_path.exists()
    state_raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert isinstance(state_raw.get("pending_clarification"), dict)
