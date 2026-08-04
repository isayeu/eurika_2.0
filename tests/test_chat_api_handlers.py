"""Chat API handler tests: add_module_test, release_check, roadmap_verify, ls, ritual, git, tree, ui_tabs, structured_patch, clarification."""
import json
from pathlib import Path


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
    from eurika.api.chat_context import load_dialog_state

    st = load_dialog_state(tmp_path)
    assert st.get("last_release_check_output") == "FAIL: pytest tests/"
    assert st.get("last_release_check_ok") is False


def test_chat_send_release_check_qt_callback_uses_exit_code(tmp_path: Path, monkeypatch) -> None:
    """Qt path must not force empty FAIL; use run_command_with_result output/code."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    def _run(cmd: str) -> tuple[str, int]:
        assert "release_check" in cmd
        return ("==> Release check\nFAIL: ruff", 1)

    out = chat_mod.chat_send(
        tmp_path,
        "прогони release check",
        run_command_with_result=_run,
    )
    text = out.get("text") or ""
    assert "не прошёл" in text
    assert "FAIL: ruff" in text
    assert "(вывод пуст)" not in text
    assert out.get("terminal_exit_code") == 1


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


def test_chat_prompt_russian_when_user_writes_russian() -> None:
    from eurika.api.chat import _build_chat_prompt

    prompt = _build_chat_prompt("почему модуль X важен?", "ctx", history=None)
    assert "Russian only" in prompt


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
    text = out.get("text") or ""
    assert "Я Eurika" in text
    assert "Исаев" in text
    assert "ProDG" in text

    creator = chat_send(tmp_path, "Кто твой создатель?")
    assert creator.get("error") is None
    assert "Исаев Андрей Аркадьевич" in (creator.get("text") or "")


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


def test_chat_send_question_like_message_goes_to_llm_not_ritual(tmp_path: Path, monkeypatch) -> None:
    """Question-like messages (что делает, чем отличается) go to LLM, not ritual (ROADMAP 3.6.8 Phase 5)."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda prompt, max_tokens=1024: ("Doctor диагностирует проект. Suggest-plan предлагает план рефакторинга.", None),
    )
    out = chat_mod.chat_send(tmp_path, "Чем doctor отличается от suggest-plan?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Выполнил ритуал" not in text
    assert "diagnost" in text.lower() or "рефакторинг" in text.lower() or "doctor" in text.lower()


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


def test_git_commit_message_with_apply_word_does_not_hijack_confirmation() -> None:
    """Commit text containing 'Apply' must stay git_commit, not HITL apply."""
    from eurika.api.chat_direct import is_apply_confirmation, is_git_commit_request, resolve_direct_handler
    from pathlib import Path

    msg = "собери коммит: Gate Apply after Diff preview for chat pending plans"
    assert is_git_commit_request(msg) is True
    assert is_apply_confirmation(msg) is False
    assert resolve_direct_handler(Path("."), msg)[0] == "git_commit"
    assert is_apply_confirmation("применяй token:abcd1234") is True
    assert is_apply_confirmation("apply token:abcd1234") is True
    assert is_apply_confirmation("Gate Apply after Diff") is False


def test_goal_status_and_clear_goal_intents(tmp_path: Path, monkeypatch) -> None:
    """goal_status / clear_goal are direct handlers; context injects active goal."""
    import json
    import eurika.api.chat as chat_mod
    from eurika.api.chat_context import build_chat_context, format_dialog_goal_block
    from eurika.api.chat_direct import resolve_direct_handler

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    hist = tmp_path / ".eurika" / "chat_history"
    hist.mkdir(parents=True)
    state = {
        "active_goal": {
            "intent": "refactor",
            "target": "foo.py",
            "source": "chat",
            "risk_level": "low",
        },
        "pending_clarification": {"original": "уточни файл"},
        "pending_plan": {},
        "last_execution": {"ok": True, "summary": "done", "verification_ok": True},
    }
    (hist / "dialog_state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )

    assert resolve_direct_handler(tmp_path, "какая цель?")[0] == "goal_status"
    assert resolve_direct_handler(tmp_path, "сбрось цель")[0] == "clear_goal"

    status = chat_mod.chat_send(tmp_path, "какая цель?")
    text = status.get("text") or ""
    assert status.get("error") is None
    assert "refactor" in text and "foo.py" in text
    assert "уточни файл" in text

    ctx = build_chat_context(tmp_path)
    assert "[Agent context:" in ctx
    assert "refactor" in ctx

    cleared = chat_mod.chat_send(tmp_path, "сбрось цель")
    assert cleared.get("error") is None
    assert "Сбросил" in (cleared.get("text") or "")
    after = json.loads((hist / "dialog_state.json").read_text(encoding="utf-8"))
    assert after.get("active_goal") == {}
    assert after.get("pending_clarification") == {}
    empty = format_dialog_goal_block(after)
    assert "Нет активной цели" in empty


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


def test_chat_send_project_overview_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'что за проект?' should return structured overview, not LLM."""
    import eurika.api.chat as chat_mod

    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "self_map.json").write_text(
        '{"modules":[{"path":"app.py","lines":1,"functions":[],"classes":[]}],'
        '"dependencies":{},"summary":{"files":1,"total_lines":1}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "что за проект?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "1 модулей" in text or "1 модул" in text
    assert "app.py" in text or ".py" in text


def test_chat_send_file_recount_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'пересчитай файлы' should recount from disk without LLM."""
    import eurika.api.chat as chat_mod

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "util.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "self_map.json").write_text(
        '{"modules":[{"path":"src/main.py","lines":1},{"path":"src/util.py","lines":1}],'
        '"dependencies":{},"summary":{"files":2,"total_lines":2}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "ты уверена? пересчитай файлы")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Пересчитал файлы" in text
    assert "main.py" in text
    assert "util.py" in text
    assert "2" in text


def test_chat_send_greeting_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'привет' should get a local greeting, not LLM."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "привет")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Eurika" in text
    assert "puedo" not in text.lower()


def test_chat_send_file_count_question_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'сколько всего файлов в проекте?' should recount from disk."""
    import eurika.api.chat as chat_mod

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("y\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сколько всего файлов в проекте?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Всего файлов" in text
    assert "2" in text
    assert "puedo" not in text.lower()


def test_chat_send_file_count_with_filler_words_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'сколько всего там файлов?' should recount from disk."""
    import eurika.api.chat as chat_mod

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "сколько всего там файлов?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Всего файлов" in text
    assert "puedo" not in text.lower()


def test_chat_send_file_recount_confirmation_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'ты пересчитала все файлы?' should recount again, not LLM."""
    import eurika.api.chat as chat_mod

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "ты пересчитала все файлы?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Пересчитал файлы" in text
    assert "Всего файлов" in text


def test_chat_send_list_docs_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'какие есть документы по проекту?' lists docs from disk, no LLM."""
    import eurika.api.chat as chat_mod

    (tmp_path / "README.md").write_text("# Project\n\nIntro\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "Architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (tmp_path / "docs" / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "Какие есть документы по проекту?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Документация проекта" in text
    assert "README.md" in text
    assert "Architecture.md" in text
    assert "ROADMAP.md" in text


def test_chat_send_list_docs_empty_project(tmp_path: Path, monkeypatch) -> None:
    """When no docs found, suggest informative project artifacts."""
    import eurika.api.chat as chat_mod

    (tmp_path / "self_map.json").write_text('{"modules":[]}', encoding="utf-8")
    (tmp_path / "kv").mkdir()
    (tmp_path / "kv" / "ui.kv").write_text("#:kivy\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "покажи документацию")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "не найдено" in text.lower()
    assert "self_map.json" in text or "ui.kv" in text


def test_chat_send_web_search_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'поищи в интернете kivy' uses web search handler, not LLM."""
    import eurika.api.chat as chat_mod
    from eurika.utils.web_search import WebSearchResult

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    monkeypatch.setattr(
        "eurika.utils.web_search.search_web",
        lambda query, **kwargs: (
            [WebSearchResult("Kivy", "https://kivy.org", "UI framework", "duckduckgo")],
            "duckduckgo",
            None,
        ),
    )
    out = chat_mod.chat_send(tmp_path, "поищи в интернете kivy sqlite")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Результаты поиска" in text
    assert "https://kivy.org" in text


def test_chat_send_capabilities_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'что ты умеешь?' returns structured help, not LLM."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "Что ты умеешь?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "локальный доступ к проекту" in text
    assert "что за проект" in text
    assert "поищи в интернете" in text
    assert "god_module" not in text.lower()


def test_chat_send_can_write_programs_without_llm(tmp_path: Path, monkeypatch) -> None:
    """'ты можешь писать программы?' must not go to LLM (weak models hallucinate)."""
    import eurika.api.chat as chat_mod
    from eurika.api.chat_intents_config import clear_cache, match_direct_intent

    clear_cache()
    assert match_direct_intent(tmp_path, "ты можешь писать программы?") == ("capabilities", None)
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "ты можешь писать программы?")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "локальный доступ к проекту" in text
    assert "Правила за рефакторинго" not in text
    assert "L4" not in text


def test_chat_send_roadmap_next_without_llm(tmp_path: Path, monkeypatch) -> None:
    """Roadmap / development questions read ROADMAP.md, not LLM."""
    import eurika.api.chat as chat_mod

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ROADMAP.md").write_text(
        """# ROADMAP

## 1. Принцип и текущая задача

Саморазвитие Eurika.

### 4.5 Текущий фокус

| Приоритет | Задача | Статус |
|-----------|--------|--------|
| 1 | Chat intents | ✅ |

### 4.6 Следующие шаги

**Architecture Freeze (S0) — активно:** только упрощение.

## 6. Открытый бэклог

- [ ] **RV11** Call graph
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    msg = "просмотри документацию, что у нас дальше по развитию проекта?"
    out = chat_mod.chat_send(tmp_path, msg)
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "без LLM" in text
    assert "Architecture Freeze" in text
    assert "RV11" in text
    assert "403 модул" not in text
    assert "patch_engine" not in text.lower()


def test_discover_project_docs_finds_nested_readme(tmp_path: Path) -> None:
    """Auto-discovery scans shallow tree for README outside docs/."""
    from eurika.api.chat_utils import discover_project_docs

    sub = tmp_path / "flutter_app"
    sub.mkdir()
    (sub / "README.md").write_text("# Flutter app\n", encoding="utf-8")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "design.md").write_text("# Design\n", encoding="utf-8")
    grouped, total = discover_project_docs(tmp_path)
    assert total >= 2
    other = grouped.get("other") or []
    notes = grouped.get("notes") or []
    paths = {str(p.relative_to(tmp_path)) for p, _ in other + notes}
    assert "flutter_app/README.md" in paths or any("README.md" in p for p in paths)
    assert any("design.md" in p for p in paths)


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
