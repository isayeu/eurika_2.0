"""Tests for Binance read-only helpers (mocked HTTP; no live orders)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from eurika.integrations import binance_readonly as br


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_ping_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br, "binance_base_url", lambda: "https://api.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        return _FakeResp({})

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    out = br.ping()
    assert out["ok"] is True
    assert out["error"] is None
    assert out["base_url"] == "https://api.binance.com"


def test_ticker_price_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br, "binance_base_url", lambda: "https://api.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        return _FakeResp({"symbol": "BTCUSDT", "price": "65000.12"})

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    out = br.ticker_price("btcusdt")
    assert out["ok"] is True
    assert out["symbol"] == "BTCUSDT"
    assert out["price"] == "65000.12"


def test_account_balances_filters_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "k" * 64)
    monkeypatch.setenv("BINANCE_API_SECRET", "s" * 64)
    monkeypatch.setattr(br, "binance_base_url", lambda: "https://api.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        return _FakeResp(
            {
                "balances": [
                    {"asset": "BTC", "free": "0.01", "locked": "0"},
                    {"asset": "USDT", "free": "0", "locked": "0"},
                    {"asset": "ETH", "free": "0", "locked": "1.5"},
                ]
            }
        )

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    out = br.account_balances()
    assert out["ok"] is True
    assert out["count"] == 2
    assets = {r["asset"] for r in out["balances"]}
    assert assets == {"BTC", "ETH"}
    # Never leak secrets in payload
    blob = json.dumps(out)
    assert "k" * 64 not in blob
    assert "s" * 64 not in blob


def test_account_balances_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    out = br.account_balances()
    assert out["ok"] is False
    assert out["error"] == "credentials not ready"


def test_probe_readonly_skips_balances_without_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.setattr(br, "binance_base_url", lambda: "https://api.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        url = getattr(req, "full_url", "") or str(req)
        if "ticker" in url:
            return _FakeResp({"symbol": "BTCUSDT", "price": "1"})
        return _FakeResp({})

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    out = br.probe_readonly(include_balances=True)
    assert out["ping"]["ok"] is True
    assert out["ticker"]["ok"] is True
    assert out["balances"] is None


def test_base_url_testnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET", "1")
    monkeypatch.delenv("BINANCE_BASE_URL", raising=False)
    assert br.binance_base_url() == "https://testnet.binance.vision"


def test_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_BASE_URL", "https://example.test/")
    assert br.binance_base_url() == "https://example.test"


def test_futures_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_FUTURES_BASE_URL", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET", raising=False)
    assert br.futures_base_url() == "https://fapi.binance.com"
    monkeypatch.setenv("BINANCE_TESTNET", "1")
    assert br.futures_base_url() == "https://testnet.binancefuture.com"
    monkeypatch.setenv("BINANCE_FUTURES_BASE_URL", "https://fut.example/")
    assert br.futures_base_url() == "https://fut.example"


def test_futures_ticker_price_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br, "futures_base_url", lambda: "https://fapi.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        return _FakeResp({"symbol": "ETHUSDT", "price": "3500.1"})

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    out = br.futures_ticker_price("ethusdt")
    assert out["ok"] is True
    assert out["symbol"] == "ETHUSDT"
    assert out["price"] == "3500.1"


def test_futures_premium_index_and_funding_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(br, "futures_base_url", lambda: "https://fapi.binance.com")

    def fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        url = getattr(req, "full_url", "") or str(req)
        if "premiumIndex" in url:
            return _FakeResp(
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "65000",
                    "lastFundingRate": "0.0001",
                    "nextFundingTime": 1_700_000_000_000,
                }
            )
        if "fundingRate" in url:
            return _FakeResp(
                [
                    {"symbol": "BTCUSDT", "fundingRate": "0.0002", "fundingTime": 1_700_000_100_000},
                    {"symbol": "BTCUSDT", "fundingRate": "-0.00005", "fundingTime": 1_700_000_200_000},
                ]
            )
        return _FakeResp({})

    monkeypatch.setattr(br.urllib.request, "urlopen", fake_urlopen)
    prem = br.futures_premium_index("btcusdt")
    assert prem["ok"] is True
    assert abs(float(prem["last_funding_rate"]) - 0.0001) < 1e-12
    hist = br.futures_funding_rate_history("BTCUSDT", start_time=1, end_time=9, limit=10)
    assert hist["ok"] is True
    assert hist["count"] == 2
    assert hist["rows"][0]["funding_rate"] == pytest.approx(0.0002)
