"""Tests for Binance credential presence helpers (no secret values)."""

from __future__ import annotations

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
