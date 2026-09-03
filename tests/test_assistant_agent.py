"""Tests for LLM-driven assistant paper agent (portfolio delegate)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.ml.assistant_agent import (
    build_agent_prompt,
    parse_assistant_actions,
    run_agent_cycle,
)
from eurika.ml.assistant_paper import ensure_portfolio, load_pending
from eurika.ml.earn_monitor import ensure_earn_portfolio
from eurika.ml.market_store import save_candles
from eurika.ml.universe import save_ticker_lists


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


def test_parse_assistant_actions_json_fence() -> None:
    text = (
        "BTC откат, жду лимит.\n"
        '```json\n{"assistant_actions":[{"symbol":"BTCUSDT","market":"futures",'
        '"action":"place","side":"BUY","entry_style":"limit","limit_px":70000}]}\n```'
    )
    rows = parse_assistant_actions(text)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["action"] == "place"


def test_build_agent_prompt_includes_book(tmp_path: Path) -> None:
    sym = "BTCUSDT"
    save_ticker_lists(tmp_path, futures=[sym])
    bars = _bars(50, 50000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol=sym, interval=iv, market="futures")
    ensure_portfolio(tmp_path)
    ensure_earn_portfolio(tmp_path)
    prompt = build_agent_prompt(tmp_path, now_ms=1_700_000_000_000)
    assert "ASSISTANT PAPER BOOK" in prompt
    assert "HOLISTIC CASH POOL" in prompt
    assert "EARN PAPER BOOK" in prompt
    assert "BTCUSDT" in prompt
    assert "portfolio_actions" in prompt


def test_run_agent_cycle_mock_hold(tmp_path: Path, monkeypatch) -> None:
    sym = "ETHUSDT"
    save_ticker_lists(tmp_path, futures=[sym])
    bars = _bars(50, 3000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol=sym, interval=iv, market="futures")
    ensure_portfolio(tmp_path)
    ensure_earn_portfolio(tmp_path)

    def fake_chat(prompt: str) -> tuple[str, None]:
        assert "ASSISTANT PAPER BOOK" in prompt
        return (
            "Ночь спокойная, держим кэш.\n"
            '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"no","side":"HOLD"}],'
            '"portfolio_actions":[{"product":"trade","symbol":"ETHUSDT","market":"futures","action":"hold"}]}',
            None,
        )

    monkeypatch.setattr("eurika.ml.portfolio_agent.fetch_earn_rates", lambda *a, **k: {"products": []})
    monkeypatch.setattr("eurika.ml.portfolio_agent.expand_portfolio_universe", lambda *a, **k: {})
    monkeypatch.setattr("eurika.ml.portfolio_agent.ensure_portfolio_candles", lambda *a, **k: None)
    monkeypatch.setattr("eurika.ml.portfolio_agent.sync_assistant_symbols", lambda *a, **k: [])
    monkeypatch.setattr(
        "eurika.ml.portfolio_agent._harvest_learning",
        lambda *a, **k: {"stored": 0},
    )

    out = run_agent_cycle(tmp_path, now_ms=1_700_000_000_000, complete_chat=fake_chat, fetch_rates=False)
    assert out["ok"] is True
    assert out["actions_n"] == 1
    assert load_pending(tmp_path) == []

    journal = (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").read_text(encoding="utf-8")
    last = json.loads(journal.strip().splitlines()[-1])
    assert last["kind"] == "portfolio_cycle"
    assert "Ночь спокойная" in last["text"]


def test_run_agent_cycle_place_pending(tmp_path: Path, monkeypatch) -> None:
    sym = "SOLUSDT"
    save_ticker_lists(tmp_path, futures=[sym])
    bars = _bars(50, 150.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol=sym, interval=iv, market="futures")
    ensure_portfolio(tmp_path)
    ensure_earn_portfolio(tmp_path)

    def fake_chat(_prompt: str) -> tuple[str, None]:
        return (
            "Лимит у поддержки.\n"
            '{"samples":[{"symbol":"SOLUSDT","market":"fut","enter":"wait","side":"BUY"}],'
            '"portfolio_actions":[{"product":"trade","symbol":"SOLUSDT","market":"futures","action":"place",'
            '"side":"BUY","entry_style":"limit","limit_px":140.0,"tp_pct":0.01,"sl_pct":0.02}]}',
            None,
        )

    monkeypatch.setattr("eurika.ml.portfolio_agent.fetch_earn_rates", lambda *a, **k: {"products": []})
    monkeypatch.setattr("eurika.ml.portfolio_agent.expand_portfolio_universe", lambda *a, **k: {})
    monkeypatch.setattr("eurika.ml.portfolio_agent.ensure_portfolio_candles", lambda *a, **k: None)
    monkeypatch.setattr("eurika.ml.portfolio_agent.sync_assistant_symbols", lambda *a, **k: [])
    monkeypatch.setattr(
        "eurika.ml.portfolio_agent._harvest_learning",
        lambda *a, **k: {"stored": 0},
    )

    out = run_agent_cycle(tmp_path, now_ms=1_700_000_000_000, complete_chat=fake_chat, fetch_rates=False)
    assert out["ok"] is True
    assert int((out.get("trade") or {}).get("place") or 0) == 1
