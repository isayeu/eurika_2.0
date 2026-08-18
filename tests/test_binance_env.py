"""Tests for Binance credential presence helpers (no secret values)."""

from __future__ import annotations

import json
import os

import pytest

from eurika.utils.env import binance_credentials_status, load_project_dotenv


def test_binance_credentials_status_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "k" * 64)
    monkeypatch.setenv("BINANCE_API_SECRET", "s" * 64)
    monkeypatch.setenv("BINANCE_TESTNET", "0")
    st = binance_credentials_status()
    assert st["api_key_set"] is True
    assert st["api_secret_set"] is True
    assert st["testnet"] is False
    assert st["ready"] is True
    # never leak secrets
    assert "k" * 10 not in str(st)


def test_binance_credentials_status_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    st = binance_credentials_status()
    assert st["ready"] is False


def test_load_project_dotenv_loads_binance(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("dotenv")
    (tmp_path / ".env").write_text(
        "BINANCE_API_KEY=project-binance-key\nBINANCE_API_SECRET=project-binance-secret\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    load_project_dotenv(tmp_path)
    assert os.environ["BINANCE_API_KEY"] == "project-binance-key"
    assert os.environ["BINANCE_API_SECRET"] == "project-binance-secret"


def test_parse_env_file_and_chat_provider_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.utils.env import _parse_env_file

    (tmp_path / ".env").write_text(
        'OPENAI_API_KEY="groq-test-key"\nEURIKA_CHAT_PROVIDER=openai\n',
        encoding="utf-8",
    )
    parsed = _parse_env_file(tmp_path / ".env")
    assert parsed["OPENAI_API_KEY"] == "groq-test-key"
    assert parsed["EURIKA_CHAT_PROVIDER"] == "openai"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EURIKA_CHAT_PROVIDER", raising=False)

    # Force built-in path even if python-dotenv is installed.
    import builtins

    real_import = builtins.__import__

    def _no_dotenv(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dotenv" or (isinstance(name, str) and name.startswith("dotenv.")):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _no_dotenv)
    load_project_dotenv(tmp_path)
    assert os.environ["OPENAI_API_KEY"] == "groq-test-key"
    assert os.environ["EURIKA_CHAT_PROVIDER"] == "openai"


def test_load_project_dotenv_loads_cursor_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("CURSOR_API_KEY=crsr_test_not_real\n", encoding="utf-8")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    load_project_dotenv(tmp_path)
    assert os.environ["CURSOR_API_KEY"] == "crsr_test_not_real"


def test_cursor_key_status_does_not_leak_secret(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.agent.cursor_judge import cursor_key_status

    secret = "crsr_leakcheck_secret_value"
    (tmp_path / ".env").write_text(f"CURSOR_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    st = cursor_key_status(tmp_path)
    assert st["api_key_set"] is True
    assert secret not in json.dumps(st)
