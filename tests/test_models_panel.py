"""Models-tab snapshot + safe prefs (no API secrets, Market freeze)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eurika.api.models_panel import apply_models_prefs, build_models_state


def test_models_state_hides_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(tmp_path / "qt_settings.json"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-do-not-leak")
    monkeypatch.setenv("BINANCE_API_SECRET", "binance-secret-do-not-leak")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test-secret-do-not-leak\n"
        "BINANCE_API_SECRET=binance-secret-do-not-leak\n",
        encoding="utf-8",
    )
    state = build_models_state(tmp_path)
    blob = json.dumps(state)
    assert state["panel"] == "models"
    assert "sk-test-secret" not in blob
    assert "binance-secret" not in blob
    keys = state["llm"]["keys_present"]
    assert keys["OPENAI_API_KEY"] is True
    assert keys["BINANCE_API_SECRET"] is True
    assert isinstance(state["ml"]["market"], dict)
    assert "trading control" in state["ml"]["market"]["note"]


def test_apply_models_prefs_writes_preset_url_not_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EURIKA_QT_SETTINGS_PATH", str(tmp_path / "qt_settings.json"))
    (tmp_path / ".env").write_text("OPENAI_API_KEY=keep-me\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        apply_models_prefs(tmp_path, {"OPENAI_API_KEY": "stolen"})
    state = apply_models_prefs(
        tmp_path,
        {
            "provider": "openai",
            "api_preset": "groq",
            "openai_model": "openai/gpt-oss-20b",
            "timeout_sec": 90,
            "torch_device": "cpu",
        },
    )
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=keep-me" in env_text
    assert "OPENAI_BASE_URL=" in env_text
    assert "api.groq.com" in env_text
    assert "stolen" not in env_text
    settings = json.loads((tmp_path / "qt_settings.json").read_text(encoding="utf-8"))
    assert settings["chat_timeout_sec"] == 90
    assert state["llm"]["timeout_sec"] == 90
    assert state["ml"]["torch_device"] == "cpu"
