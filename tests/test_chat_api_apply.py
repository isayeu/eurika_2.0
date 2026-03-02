"""Apply/reject/confirmation tests for eurika.api.chat (split from test_chat_api)."""

import json as _json
from pathlib import Path


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
