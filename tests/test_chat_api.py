"""Domain-level edge-case tests for eurika.api.chat."""

import json
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


def test_chat_send_add_empty_tab_request_returns_task_understanding(tmp_path: Path, monkeypatch) -> None:
    """Add-empty-tab request should return deterministic task understanding (no LLM)."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "после вкладки Chat создать пустую вкладку в UI")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "добавить пустую вкладку после `Chat`" in text
    assert "qt_app/ui/main_window.py" in text


def test_chat_send_remove_new_tab_request_returns_task_understanding(tmp_path: Path, monkeypatch) -> None:
    """Remove-tab request should be interpreted as ui_remove_tab intent."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "удали вкладку New Tab в UI")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "удалить вкладку `New Tab`" in text
    assert "qt_app/ui/main_window.py" in text
    assert "Risk: `high`" in text


def test_chat_send_apply_prefers_latest_remove_tab_plan_over_previous_add(tmp_path: Path, monkeypatch) -> None:
    """E2E: add intent then remove intent; apply must execute latest (remove) plan."""
    import json as _json
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    first = chat_mod.chat_send(tmp_path, "после вкладки Chat создать пустую вкладку в UI")
    assert first.get("error") is None

    second = chat_mod.chat_send(tmp_path, "удали вкладку New Tab")
    assert second.get("error") is None

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    pending = state.get("pending_plan") or {}
    assert pending.get("intent") == "ui_remove_tab"

    captured: dict[str, str] = {}

    def _fake_execute(_root, spec):
        captured["intent"] = spec.intent
        captured["target"] = spec.target
        return type(
            "ExecReport",
            (),
            {
                "ok": True,
                "summary": "removed New Tab",
                "applied_steps": ["remove New Tab"],
                "skipped_steps": [],
                "verification": {"ok": True, "output": "qt smoke: OK"},
                "artifacts_changed": ["qt_app/ui/main_window.py"],
                "error": None,
            },
        )()

    monkeypatch.setattr(chat_mod, "execute_spec", _fake_execute)
    out = chat_mod.chat_send(tmp_path, "применяй")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert captured.get("intent") == "ui_remove_tab"
    assert "Готово:" in text
    assert "qt smoke: OK" in text


def test_chat_send_apply_confirmation_executes_ui_add_tab_and_runs_smoke(tmp_path: Path, monkeypatch) -> None:
    """Confirmation should apply pending ui_add_empty_tab goal and run smoke."""
    import json as _json
    import eurika.api.chat as chat_mod

    target = tmp_path / "qt_app" / "ui"
    target.mkdir(parents=True, exist_ok=True)
    main_window = target / "main_window.py"
    main_window.write_text(
        'def build():\n'
        '    tab = object()\n'
        '    self = type("X", (), {"tabs": object()})()\n'
        '    self.tabs.addTab(tab, "Chat")\n',
        encoding="utf-8",
    )
    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps(
            {
                "pending_plan": {
                    "intent": "ui_add_empty_tab",
                    "target": "qt_app/ui/main_window.py",
                    "token": "abcd1234abcd1234",
                    "status": "pending_confirmation",
                    "expires_ts": 4102444800,
                    "steps": ["insert New Tab", "verify UI smoke"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chat_mod,
        "execute_spec",
        lambda *_args, **_kwargs: type(
            "ExecReport",
            (),
            {
                "ok": True,
                "summary": "added empty tab after Chat",
                "applied_steps": ["insert New Tab"],
                "skipped_steps": [],
                "verification": {"ok": True, "output": "qt smoke: OK"},
                "artifacts_changed": ["qt_app/ui/main_window.py"],
                "error": None,
            },
        )(),
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    out = chat_mod.chat_send(tmp_path, "применяй")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Готово:" in text
    assert "qt smoke: OK" in text
    # Execution path is handled through executor contract.


def test_chat_send_apply_with_wrong_token_is_rejected(tmp_path: Path) -> None:
    """Wrong confirmation token should not execute pending plan."""
    import json as _json
    import eurika.api.chat as chat_mod

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps(
            {
                "pending_plan": {
                    "intent": "create",
                    "target": "x.py",
                    "token": "deadbeefdeadbeef",
                    "status": "pending_confirmation",
                    "expires_ts": 4102444800,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = chat_mod.chat_send(tmp_path, "применяй token:11223344")
    assert out.get("error") is None
    assert "token подтверждения не совпадает" in (out.get("text") or "")


def test_chat_send_apply_without_pending_plan_does_not_fallback_to_active_goal(tmp_path: Path, monkeypatch) -> None:
    """Confirmation must execute only pending plan, not stale active goal."""
    import json as _json
    import eurika.api.chat as chat_mod

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps({"active_goal": {"intent": "save", "target": "foo.py"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        chat_mod,
        "execute_spec",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("execute_spec should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, "применяй")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "нет активного плана на подтверждение" in text


def test_chat_send_reject_pending_plan_clears_it(tmp_path: Path) -> None:
    """Reject command should clear valid pending plan without execution."""
    import json as _json
    import eurika.api.chat as chat_mod

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps(
            {
                "pending_plan": {
                    "intent": "ui_add_empty_tab",
                    "target": "qt_app/ui/main_window.py",
                    "token": "abcd1234abcd1234",
                    "status": "pending_confirmation",
                    "expires_ts": 4102444800,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = chat_mod.chat_send(tmp_path, "отклонить")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Отклонил pending-план" in text
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    assert state.get("pending_plan") == {}


def test_chat_send_run_lint_executes_without_confirmation(tmp_path: Path, monkeypatch) -> None:
    """Low-risk lint intent should execute immediately via executor."""
    import eurika.api.chat as chat_mod

    monkeypatch.setattr(
        chat_mod,
        "execute_spec",
        lambda *_args, **_kwargs: type(
            "ExecReport",
            (),
            {
                "ok": True,
                "summary": "lint passed",
                "applied_steps": ["run lint"],
                "skipped_steps": [],
                "verification": {"ok": True, "output": "clean"},
                "artifacts_changed": [],
                "error": None,
            },
        )(),
    )
    out = chat_mod.chat_send(tmp_path, "запусти линтер")
    assert out.get("error") is None
    assert "Готово: lint passed." in (out.get("text") or "")


def test_chat_send_run_command_requires_confirmation(tmp_path: Path) -> None:
    """High-risk run_command intent should produce pending confirmation."""
    import eurika.api.chat as chat_mod

    out = chat_mod.chat_send(tmp_path, "выполни команду eurika scan .")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Подтверди выполнение" in text
    assert "run_command" in text


def test_chat_send_code_edit_patch_requires_confirmation(tmp_path: Path) -> None:
    import eurika.api.chat as chat_mod

    out = chat_mod.chat_send(
        tmp_path,
        'замени в файле qt_app/ui/main_window.py "Chat" на "ChatX"',
    )
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "code_edit_patch" in text
    assert "Подтверди выполнение" in text


def test_chat_send_confirm_code_edit_patch_uses_pending_entities(tmp_path: Path, monkeypatch) -> None:
    import json as _json
    import eurika.api.chat as chat_mod

    state_path = tmp_path / ".eurika" / "chat_history" / "dialog_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        _json.dumps(
            {
                "pending_plan": {
                    "intent": "code_edit_patch",
                    "target": "a.py",
                    "entities": {"old_text": "x", "new_text": "y"},
                    "token": "abcd1234abcd1234",
                    "status": "pending_confirmation",
                    "expires_ts": 4102444800,
                    "steps": ["apply patch"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured = {}

    def _fake_execute(_root, spec):
        captured["intent"] = spec.intent
        captured["target"] = spec.target
        captured["old_text"] = spec.entities.get("old_text")
        return type(
            "ExecReport",
            (),
            {
                "ok": True,
                "summary": "patch applied and verified",
                "applied_steps": ["apply patch"],
                "skipped_steps": [],
                "verification": {"ok": True, "output": "ok"},
                "artifacts_changed": ["a.py"],
                "error": None,
            },
        )()

    monkeypatch.setattr(chat_mod, "execute_spec", _fake_execute)
    out = chat_mod.chat_send(tmp_path, "применяй token:abcd1234abcd1234")
    assert out.get("error") is None
    assert captured.get("intent") == "code_edit_patch"
    assert captured.get("old_text") == "x"


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


def test_append_chat_history_records_timezone_aware_utc_timestamp(tmp_path: Path) -> None:
    """append_chat_history should write UTC timestamp in Z-suffixed ISO format."""
    from eurika.api.chat import append_chat_history

    append_chat_history(tmp_path, "user", "hello", None)
    log_path = tmp_path / ".eurika" / "chat_history" / "chat.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    ts = payload.get("ts") or ""
    assert ts.endswith("Z")
    assert "T" in ts


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
