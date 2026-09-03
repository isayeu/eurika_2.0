"""Smoke tests for assistant thesis night paper."""

from __future__ import annotations

from pathlib import Path

from eurika.ml.assistant_paper import (
    ensure_portfolio,
    propose_thesis,
    run_cycle,
    seed_theses,
)
from eurika.ml.market_store import save_candles


def _bars(n: int, start: float = 100.0) -> list[dict]:
    out = []
    for i in range(n):
        px = start + i * 0.05
        out.append(
            {
                "open_time": i * 60_000,
                "open": px,
                "high": px + 0.2,
                "low": px - 0.1,
                "close": px + 0.05,
                "volume": 10.0,
            }
        )
    return out


def test_propose_thesis_trend_pullback() -> None:
    c15 = _bars(40, 100.0)
    c1h = _bars(40, 95.0)
    th = propose_thesis("BTCUSDT", candles_15m=c15, candles_1h=c1h)
    assert th is not None
    assert th["symbol"] == "BTCUSDT"
    assert th["side"] == "BUY"
    assert th["entry_style"] in {"limit", "stop"}


def test_assistant_cycle_smoke(tmp_path: Path) -> None:
    sym = "ETHUSDT"
    bars = _bars(50, 2000.0)
    save_candles(tmp_path, bars, symbol=sym, interval="15m", market="futures")
    save_candles(tmp_path, bars, symbol=sym, interval="1h", market="futures")
    save_candles(tmp_path, bars, symbol=sym, interval="1m", market="futures")
    ensure_portfolio(tmp_path)
    out = run_cycle(tmp_path)
    assert "equity_usdt" in out
    assert (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").is_file()


def test_seed_writes_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "eurika.ml.assistant_paper.sync_klines",
        lambda *a, **k: {"ok": True},
    )
    monkeypatch.setattr(
        "eurika.ml.assistant_paper.load_candles",
        lambda root, sym, iv, market="futures": _bars(45, 50000.0 if "BTC" in sym else 3000.0),
    )
    rows = seed_theses(tmp_path, symbols=["BTCUSDT", "ETHUSDT"])
    assert rows
    journal = (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").read_text(encoding="utf-8")
    assert "SEED" in journal
