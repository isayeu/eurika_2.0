"""Qt Models source must win over project .env for Chat and Desktop."""

from __future__ import annotations

import json
import os
from pathlib import Path

from eurika.utils.env import (
    LLM_ENV_LOCK_KEY,
    apply_qt_chat_routing,
    load_project_dotenv,
)


def test_chat_source_label_maps_providers() -> None:
    from qt_app.ui.handlers.chat_handlers import _chat_source_label

    assert _chat_source_label("cursor") == "LLM: Cursor"
    assert _chat_source_label("openai") == "LLM: облако"
    assert _chat_source_label("unknown") == "LLM: —"


def test_chat_source_tooltip_includes_cursor_model() -> None:
    from types import SimpleNamespace
    from typing import cast

    from qt_app.ui.handlers.chat_handlers import _chat_source_tooltip
    from qt_app.ui.main_window import MainWindow

    main = cast(
        MainWindow,
        SimpleNamespace(
            chat_cursor_model_combo=SimpleNamespace(currentText=lambda: "Composer 2.5"),
            chat_cursor_router_combo=SimpleNamespace(
                currentText=lambda: "cost",
                isEnabled=lambda: True,
            ),
        ),
    )
    tip = _chat_source_tooltip(main, "cursor")
    assert "Composer 2.5" in tip
    assert "Router: cost" in tip


def test_dotenv_lock_keeps_cursor_provider(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "EURIKA_CHAT_PROVIDER=openai\nCURSOR_API_KEY=crsr_test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(LLM_ENV_LOCK_KEY, "1")
    monkeypatch.setenv("EURIKA_CHAT_PROVIDER", "cursor")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    load_project_dotenv(tmp_path)
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "cursor"
    assert os.environ["CURSOR_API_KEY"] == "crsr_test"


def test_apply_qt_chat_routing_overrides_env(tmp_path, monkeypatch) -> None:
    settings = tmp_path / "qt_settings.json"
    settings.write_text(
        json.dumps(
            {
                "chat_provider": "cursor",
                "chat_cursor_model": "composer-2.5",
                "chat_cursor_router": "cost",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(settings))
    monkeypatch.delenv(LLM_ENV_LOCK_KEY, raising=False)
    monkeypatch.setenv("EURIKA_CHAT_PROVIDER", "openai")
    applied = apply_qt_chat_routing()
    assert applied == "cursor"
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "cursor"
    assert os.environ["CURSOR_MODEL"] == "composer-2.5"


def test_apply_qt_chat_routing_loads_cursor_key_from_dotenv(tmp_path, monkeypatch) -> None:
    settings = tmp_path / "qt_settings.json"
    settings.write_text(
        json.dumps({"chat_provider": "cursor", "chat_cursor_model": "composer-2.5"}),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("CURSOR_API_KEY=crsr_from_env\n", encoding="utf-8")
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(settings))
    monkeypatch.delenv(LLM_ENV_LOCK_KEY, raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    load_project_dotenv(tmp_path)
    applied = apply_qt_chat_routing()
    assert applied == "cursor"
    assert os.environ.get("CURSOR_API_KEY") == "crsr_from_env"


def test_apply_qt_chat_routing_respects_lock(tmp_path, monkeypatch) -> None:
    settings = tmp_path / "qt_settings.json"
    settings.write_text(json.dumps({"chat_provider": "ollama"}), encoding="utf-8")
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(settings))
    monkeypatch.setenv(LLM_ENV_LOCK_KEY, "1")
    monkeypatch.setenv("EURIKA_CHAT_PROVIDER", "cursor")
    assert apply_qt_chat_routing() == "cursor"
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "cursor"


def test_chat_send_dotenv_does_not_clobber_adapter_cursor(tmp_path, monkeypatch) -> None:
    from eurika.api import chat as chat_mod
    from qt_app.adapters import eurika_api_adapter as adapter_mod
    from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter

    (tmp_path / ".env").write_text(
        "EURIKA_CHAT_PROVIDER=openai\nCURSOR_API_KEY=crsr_test\n",
        encoding="utf-8",
    )
    chat_mod._ENV_LOADED_ROOTS.clear()
    monkeypatch.delenv(LLM_ENV_LOCK_KEY, raising=False)
    seen: dict[str, str | None] = {}

    def _probe(_root, _message, _history, **_kwargs):
        root = Path(_root).resolve()
        chat_mod._load_project_env_once(root)
        chat_mod._apply_chat_llm_routing()
        seen["provider"] = os.environ.get("EURIKA_CHAT_PROVIDER")
        seen["locked"] = os.environ.get(LLM_ENV_LOCK_KEY)
        return {"text": "ok", "error": None}

    monkeypatch.setattr(adapter_mod, "_chat_send", _probe)
    api = EurikaApiAdapter(str(tmp_path))
    out = api.chat_send(
        message="hello",
        history=[],
        provider="cursor",
        openai_model="",
        ollama_model="qwen2.5-coder:7b",
        timeout_sec=30,
        cursor_model="composer-2.5",
    )
    assert out.get("error") in (None, "")
    assert seen["provider"] == "cursor"
    assert seen["locked"] == "1"


def test_http_chat_send_uses_qt_settings_over_dotenv(tmp_path, monkeypatch) -> None:
    from eurika.api import chat as chat_mod

    (tmp_path / ".env").write_text("EURIKA_CHAT_PROVIDER=openai\n", encoding="utf-8")
    settings = tmp_path / "qt_settings.json"
    settings.write_text(json.dumps({"chat_provider": "cursor"}), encoding="utf-8")
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(settings))
    monkeypatch.delenv(LLM_ENV_LOCK_KEY, raising=False)
    monkeypatch.setenv("EURIKA_CHAT_PROVIDER", "openai")
    chat_mod._ENV_LOADED_ROOTS.clear()
    chat_mod._load_project_env_once(tmp_path.resolve())
    chat_mod._apply_chat_llm_routing()
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "cursor"


def test_dotenv_reload_keeps_qt_cursor_after_openai_env(tmp_path, monkeypatch) -> None:
    """Restart path: load_project_dotenv(.env openai) must not leave Groq as provider."""
    (tmp_path / ".env").write_text("EURIKA_CHAT_PROVIDER=openai\n", encoding="utf-8")
    settings = tmp_path / "qt_settings.json"
    settings.write_text(json.dumps({"chat_provider": "cursor"}), encoding="utf-8")
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(settings))
    monkeypatch.delenv(LLM_ENV_LOCK_KEY, raising=False)
    load_project_dotenv(tmp_path)
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "cursor"
