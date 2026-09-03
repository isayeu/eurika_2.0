"""Tests for holistic portfolio agent."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.ml.earn_monitor import ensure_earn_portfolio
from eurika.ml.market_store import save_candles
from eurika.ml.portfolio_agent import (
    build_portfolio_prompt,
    parse_portfolio_actions,
    run_portfolio_cycle,
)
from eurika.ml.portfolio_snapshot import collect_portfolio_pairs
from eurika.ml.universe import save_ticker_lists
from eurika.ml.assistant_paper import ensure_portfolio


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


def test_parse_portfolio_actions_mixed() -> None:
    text = (
        '{"portfolio_actions":[{"product":"earn","action":"deposit","asset":"USDT","amount_usdt":100},'
        '{"product":"trade","symbol":"BTCUSDT","market":"fut","action":"hold"}]}'
    )
    rows = parse_portfolio_actions(text)
    assert len(rows) == 2
    assert rows[0]["product"] == "earn"


def test_split_actions_futures_only_drops_earn_and_spot() -> None:
    from eurika.ml.portfolio_agent import _split_actions

    earn, trade = _split_actions(
        [
            {"product": "earn", "action": "deposit", "asset": "USDT", "amount_usdt": 50},
            {"product": "trade", "symbol": "ETHUSDT", "market": "spot", "action": "hold"},
            {"product": "trade", "symbol": "BTCUSDT", "market": "fut", "action": "place", "side": "BUY"},
        ]
    )
    assert earn == []
    assert len(trade) == 1
    assert trade[0]["symbol"] == "BTCUSDT"
    assert trade[0]["market"] == "futures"


def test_collect_portfolio_pairs_futures_only(tmp_path: Path, monkeypatch) -> None:
    save_ticker_lists(tmp_path, spot=["ETHUSDT"], futures=["BTCUSDT"])
    monkeypatch.setattr(
        "eurika.ml.portfolio_snapshot.load_futures_universe",
        lambda *a, **k: {
            "ok": True,
            "symbols": ["BTCUSDT", "SOLUSDT", "XRPUSDT"],
            "source": "test",
            "fetched_ms": 1,
            "error": None,
        },
    )
    monkeypatch.setattr(
        "eurika.ml.portfolio_snapshot.fetch_futures_24hr_rows",
        lambda: {
            "ok": True,
            "rows": [
                {"symbol": "SOLUSDT", "price_change_pct": 5.0, "quote_volume": 9e9},
                {"symbol": "BTCUSDT", "price_change_pct": 0.1, "quote_volume": 1e9},
                {"symbol": "XRPUSDT", "price_change_pct": -3.0, "quote_volume": 2e9},
            ],
        },
    )
    pairs = collect_portfolio_pairs(tmp_path)
    keys = {(s, m) for s, m in pairs}
    assert ("ETHUSDT", "spot") not in keys
    assert all(m == "fut" for _, m in pairs)
    assert ("SOLUSDT", "fut") in keys


def test_select_detail_book_priority() -> None:
    from eurika.ml.portfolio_snapshot import select_detail_futures_symbols

    uni = [f"S{i}USDT" for i in range(50)] + ["ADAUSDT", "BTCUSDT"]
    rows = [
        {"symbol": "S1USDT", "price_change_pct": 9.0, "quote_volume": 1e9},
        {"symbol": "ADAUSDT", "price_change_pct": 0.1, "quote_volume": 1e6},
        {"symbol": "BTCUSDT", "price_change_pct": 0.2, "quote_volume": 1e8},
    ]
    chosen = select_detail_futures_symbols(uni, rows, book=["ADAUSDT"], limit=5)
    assert chosen[0] == "ADAUSDT"
    assert "S1USDT" in chosen


def test_build_portfolio_prompt_full(tmp_path: Path, monkeypatch) -> None:
    save_ticker_lists(tmp_path, spot=["ETHUSDT"], futures=["BTCUSDT"])
    bars = _bars(40, 3000.0)
    for sym in ("ETHUSDT", "BTCUSDT"):
        for iv in ("15m", "1h", "1m"):
            save_candles(tmp_path, bars, symbol=sym, interval=iv, market="futures")
            save_candles(tmp_path, bars, symbol=sym, interval=iv, market="spot")
    ensure_portfolio(tmp_path)
    ensure_earn_portfolio(tmp_path)
    monkeypatch.setattr(
        "eurika.ml.portfolio_snapshot.load_futures_universe",
        lambda *a, **k: {"ok": True, "symbols": ["BTCUSDT", "ETHUSDT"], "source": "test", "fetched_ms": 1, "error": None},
    )
    monkeypatch.setattr(
        "eurika.ml.portfolio_snapshot.fetch_futures_24hr_rows",
        lambda: {
            "ok": True,
            "rows": [
                {"symbol": "BTCUSDT", "price_change_pct": 1.0, "quote_volume": 1e9, "last_price": 50000.0},
                {"symbol": "ETHUSDT", "price_change_pct": -2.0, "quote_volume": 5e8, "last_price": 3000.0},
            ],
        },
    )
    prompt = build_portfolio_prompt(tmp_path, now_ms=1_700_000_000_000)
    assert "FUTURES UNIVERSE" in prompt or "MARKET SNAPSHOT" in prompt
    assert "portfolio_actions" in prompt
    assert "FUTURES ONLY" in prompt or "futures" in prompt.lower()


def test_format_portfolio_digest_human(tmp_path: Path) -> None:
    from eurika.ml.assistant_paper import ensure_portfolio, save_pending
    from eurika.ml.holistic_portfolio import ensure_holistic, save_holistic
    from eurika.ml.market_store import save_candles
    from eurika.ml.portfolio_agent import format_portfolio_digest
    from eurika.ml.universe import save_ticker_lists

    ensure_holistic(tmp_path)
    ensure_portfolio(tmp_path)
    save_holistic(
        tmp_path,
        {
            **ensure_holistic(tmp_path),
            "cash_free_usdt": 994.0,
            "trade_margin_usdt": 6.0,
            "trade_realized_pnl_usdt": 0.17,
            "equity_usdt": 1000.17,
            "earn_principal_usdt": 0.0,
            "migrated_legacy": True,
            "legacy_margin_repaired": True,
        },
    )
    save_ticker_lists(tmp_path, futures=["ADAUSDT"])
    bars = _bars(40, 0.205)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol="ADAUSDT", interval=iv, market="futures")
    save_pending(
        tmp_path,
        [
            {
                "symbol": "ADAUSDT",
                "market": "futures",
                "action": "BUY",
                "entry_style": "limit",
                "limit_px": 0.2015,
                "invalidate_px": 0.2043,
                "margin_usdt": 6.0,
                "status": "pending",
            }
        ],
    )
    text = format_portfolio_digest(
        tmp_path,
        cycle={
            "ok": True,
            "body": "**Вердикт:** Держим ADA limit, cash в пуле.",
            "actions_n": 1,
            "trade": {"place": 0, "open": 0, "close": 0, "hold": 1},
            "earn": {},
        },
    )
    assert "Банк:" in text
    assert "cash" in text
    assert "realized" in text
    assert "ADAUSDT" in text
    assert "Pending:" in text
    assert "до входа" in text or "лимит" in text
    assert "Вердикт:" in text
    assert "place=0" in text
    assert "толь…" not in text or "только" in text
    # long verdict should not hard-cut at 280
    long_body = (
        "**Вердикт:** " + ("слово " * 80) + "конец."
    )
    text2 = format_portfolio_digest(tmp_path, cycle={"ok": True, "body": long_body, "actions_n": 0, "trade": {}, "earn": {}})
    vline = [ln for ln in text2.split("\n") if ln.startswith("Вердикт:")][0]
    assert "конец" in vline or len(vline) > 300
    assert "⚠ inv≥лимит" in text or "до отмены вниз" in text


def test_run_portfolio_cycle_mock(tmp_path: Path, monkeypatch) -> None:
    save_ticker_lists(tmp_path, spot=["ETHUSDT"], futures=[])
    bars = _bars(50, 3000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol="ETHUSDT", interval=iv, market="spot")
    ensure_portfolio(tmp_path)
    ensure_earn_portfolio(tmp_path)

    def fake_chat(_prompt: str) -> tuple[str, None]:
        return (
            "Futures only: ждём сетап, кэш в cash_free.\n"
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
        lambda *a, **k: {"stored": 1, "parsed": 1},
    )

    out = run_portfolio_cycle(tmp_path, now_ms=1_700_000_000_000, complete_chat=fake_chat, fetch_rates=False)
    assert out["ok"] is True
    assert int(out["trade"].get("hold") or 0) == 1
    assert int(out["earn"].get("deposit") or 0) == 0

    journal = (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").read_text(encoding="utf-8")
    last = json.loads(journal.strip().splitlines()[-1])
    assert last["kind"] == "portfolio_cycle"
