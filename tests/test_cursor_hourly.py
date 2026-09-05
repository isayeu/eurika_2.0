"""Hourly Cursor teacher: facts in, journal out, no paper opens."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from eurika.ml import cursor_hourly as ch
from eurika.ml.market_journal import load_market_journal, market_journal_path
from eurika.ml.paper_trader import paper_trades_path
from eurika.ml.paper_portfolio import ensure_portfolio


def test_module_does_not_open_or_tick() -> None:
    src = inspect.getsource(ch)
    assert "run_live_universe_tick" not in src
    assert "run_live_tick" not in src
    assert "open_paper" not in src
    from eurika.ml import cursor_hourly_brief as brief

    brief_src = inspect.getsource(brief)
    assert "run_live_universe_tick" not in brief_src


def test_is_due_without_stamp(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    assert ch.is_due(tmp_path, now_ms=1_000_000) is True


def test_is_due_after_recent_stamp(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    ch.save_stamp(tmp_path, {"last_ms": 1_000_000, "ok": True})
    assert ch.is_due(tmp_path, now_ms=1_000_000 + 10 * 60_000) is False
    assert ch.is_due(tmp_path, now_ms=1_000_000 + ch.INTERVAL_MS) is True


def test_hour_snapshot_splits_live_and_shadow(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    t0 = 2_000_000_000_000
    trades = paper_trades_path(tmp_path)
    trades.parent.mkdir(parents=True, exist_ok=True)
    trades.write_text(
        "\n".join(
            [
                '{"live":true,"symbol":"BTCUSDT","action":"BUY","edge":0.004,'
                '"exit_ts":%d,"exit_reason":"sl","pnl_usdt":-0.4}' % (t0 + 10_000),
                '{"live":true,"shadow":true,"symbol":"ETHUSDT","action":"SELL","edge":0.01,'
                '"exit_ts":%d,"exit_reason":"model","pnl_usdt":1.0}' % (t0 + 20_000),
                '{"live":true,"symbol":"SOLUSDT","action":"BUY","edge":-0.002,'
                '"exit_ts":%d,"exit_reason":"trail","pnl_usdt":-0.2}' % (t0 + 30_000),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    from eurika.ml.market_journal import append_market_journal

    append_market_journal(
        tmp_path,
        "BTCUSDT: ПОКУПКА отклонён — expansion ниже порога",
        kind="hold",
    )
    # Rewrite ts on last journal row to sit inside the hour window.
    path = market_journal_path(tmp_path)
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    import json

    last = json.loads(rows[-1])
    last["ts"] = t0 + 40_000
    rows[-1] = json.dumps(last, ensure_ascii=False)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    snap = ch.hour_snapshot(tmp_path, now_ms=t0 + 50_000, lookback_ms=60_000)
    assert snap["live_n"] == 2
    assert snap["shadow_n"] == 1
    assert snap["by_exit"].get("sl") == 1
    assert snap["by_exit"].get("trail") == 1
    assert snap["gate_rejects"] == 1
    names = [item[0] for item in snap["best_symbols"]]
    assert "BTCUSDT" in names


def test_run_writes_journal_not_trades(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    trades = paper_trades_path(tmp_path)
    before = trades.read_text(encoding="utf-8") if trades.is_file() else ""

    def fake_chat(prompt: str) -> tuple[str | None, str | None]:
        assert "независимый разбор" in prompt
        assert "MARKET SNAPSHOT" in prompt
        assert "MLP EXAM" in prompt
        assert "плечо" in prompt
        return (
            "тикер BTCUSDT [fut] вход=нет когда=ждать сторона=HOLD "
            "почему=плоский импульс. Вердикт часа: ждать расширения.",
            None,
        )

    out = ch.run_hourly_critique(
        tmp_path,
        now_ms=3_000_000,
        force=True,
        complete_chat=fake_chat,
        train=False,
    )
    assert out["ok"] is True
    assert out["kind"] == "cursor_hour"
    assert out["persisted"] is True
    rows = load_market_journal(tmp_path)
    assert rows[-1]["kind"] == "cursor_hour"
    assert "вход" in rows[-1]["message"]
    after = trades.read_text(encoding="utf-8") if trades.is_file() else ""
    assert after == before
    skipped = ch.run_hourly_critique(
        tmp_path,
        now_ms=3_000_000 + 1000,
        complete_chat=fake_chat,
        train=False,
    )
    assert skipped["skipped"] == "not_due"


def test_prompt_asks_independent_read(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    prompt = ch.build_prompt(tmp_path, now_ms=1)
    assert "независимый разбор" in prompt
    assert "explore" in prompt.lower() or "Исследование" in prompt
    assert "MARKET SNAPSHOT" in prompt
    assert "MLP EXAM" in prompt
    assert "MARKET LEARNING" not in prompt
    assert "ворота отклонили" in prompt
    assert "argmax" in prompt
    assert '"samples"' in prompt
    assert '"shadow_actions"' in prompt
    assert "Prose never places orders" in prompt
    assert "action\":\"place\"" in prompt or '"action":"place"' in prompt
    assert "limit_px" in prompt
    assert "TICKER CARDS" not in prompt
    assert "TF1" in prompt
    assert "15 минут" in prompt
    assert "LLM SHADOW" in prompt
    assert "проза" in prompt.lower() or "Prose" in prompt


def test_ticker_cards_use_candles_not_mlp_analysis(tmp_path: Path) -> None:
    from eurika.ml.cursor_hourly_brief import collect_ticker_cards, format_ticker_cards
    from eurika.ml.live_paper import save_open_positions
    from eurika.ml.market_journal import append_market_journal
    from eurika.ml.market_store import save_candles
    from eurika.ml.universe import save_ticker_lists

    ensure_portfolio(tmp_path)
    save_ticker_lists(tmp_path, spot=[], futures=["ETHUSDT", "BTCUSDT"])
    bars = [
        {
            "open_time": i * 60_000,
            "open": 100.0 + i * 0.01,
            "high": 101.0 + i * 0.01,
            "low": 99.0 + i * 0.01,
            "close": 100.2 + i * 0.01,
            "volume": 10.0,
        }
        for i in range(40)
    ]
    save_candles(tmp_path, bars, symbol="ETHUSDT", interval="15m", market="futures")
    save_candles(tmp_path, bars, symbol="ETHUSDT", interval="1h", market="futures")
    save_open_positions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "BUY",
                "entry": 64000.0,
                "leverage": 2.0,
                "tp_pct": 0.03,
                "sl_pct": 0.01,
                "levels_source": "model",
                "shadow": False,
            }
        ],
    )
    append_market_journal(
        tmp_path,
        "анализ: ETHUSDT fut окно=+0.2%, burst=+1.10 → совет: ПОКУПКА "
        "(источник: модель) — отклонён воротами",
        kind="analysis",
    )
    cards = collect_ticker_cards(tmp_path)
    by_sym = {c["symbol"]: c for c in cards}
    assert "ETHUSDT" in by_sym
    assert by_sym["ETHUSDT"].get("model_action") is None
    assert by_sym["ETHUSDT"].get("gate_reject") is None
    assert by_sym["ETHUSDT"]["feature_vec"]
    assert by_sym["ETHUSDT"]["close"]
    assert by_sym["BTCUSDT"]["book"] == "open"
    text = format_ticker_cards(cards)
    assert "MARKET SNAPSHOT" in text
    assert "TF1=15m" in text
    assert "TF2=1h" in text
    assert "rsi_14=" in text
    assert "модель:" not in text
    assert "ворота: ОТКЛОНЁН" not in text
    assert "LIVE BOOK" in text
    prompt = ch.build_prompt(tmp_path, now_ms=1)
    assert "ОТКЛОНЁН" not in prompt.split("LIVE BOOK")[0]
    assert "совет: ПОКУПКА" not in prompt


def test_ticker_cards_include_full_market_list(tmp_path: Path) -> None:
    from eurika.ml.cursor_hourly_brief import collect_ticker_cards, save_analysis_prefs
    from eurika.ml.market_store import save_candles
    from eurika.ml.universe import save_ticker_lists

    ensure_portfolio(tmp_path)
    symbols = [f"T{i}USDT" for i in range(10)]
    save_ticker_lists(tmp_path, spot=[], futures=symbols)
    bars = [
        {
            "open_time": i * 60_000,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0 + (i % 3) * 0.01,
            "volume": 10.0,
        }
        for i in range(40)
    ]
    for symbol in symbols:
        save_candles(tmp_path, bars, symbol=symbol, interval="15m", market="futures")
        save_candles(tmp_path, bars, symbol=symbol, interval="1h", market="futures")
    save_analysis_prefs(tmp_path, "15m", "1h", markets="futures")
    cards = collect_ticker_cards(tmp_path)
    assert len(cards) == 10
    assert {c["symbol"] for c in cards} == set(symbols)


def test_ticker_cards_respect_futures_only(tmp_path: Path) -> None:
    from eurika.ml.cursor_hourly_brief import (
        collect_ticker_cards,
        format_ticker_cards,
        save_analysis_prefs,
    )
    from eurika.ml.market_store import save_candles
    from eurika.ml.universe import save_ticker_lists

    ensure_portfolio(tmp_path)
    save_ticker_lists(
        tmp_path,
        spot=["EURUSDT", "SPCXBUSDT"],
        futures=["MUUSDT", "SNDKUSDT"],
    )
    bars = [
        {
            "open_time": i * 60_000,
            "open": 100.0 + i * 0.01,
            "high": 101.0 + i * 0.01,
            "low": 99.0 + i * 0.01,
            "close": 100.2 + i * 0.01,
            "volume": 10.0,
        }
        for i in range(40)
    ]
    for symbol, market in (
        ("EURUSDT", "spot"),
        ("SPCXBUSDT", "spot"),
        ("MUUSDT", "futures"),
        ("SNDKUSDT", "futures"),
    ):
        save_candles(tmp_path, bars, symbol=symbol, interval="15m", market=market)
        save_candles(tmp_path, bars, symbol=symbol, interval="1h", market=market)
    save_analysis_prefs(tmp_path, "15m", "1h", markets="futures")
    cards = collect_ticker_cards(tmp_path)
    assert {c["symbol"] for c in cards} == {"MUUSDT", "SNDKUSDT"}
    assert all(c["market"] == "fut" for c in cards)
    text = format_ticker_cards(cards, markets="futures")
    assert "markets=futures" in text
    assert "[spot]" not in text
    prompt = ch.build_prompt(tmp_path, now_ms=1)
    assert "EURUSDT" not in prompt
    assert "SPCXBUSDT" not in prompt
    assert "MUUSDT" in prompt


def _seed_futures_snapshot(tmp_path: Path) -> None:
    from eurika.ml.cursor_hourly_brief import save_analysis_prefs
    from eurika.ml.market_store import save_candles
    from eurika.ml.universe import save_ticker_lists

    ensure_portfolio(tmp_path)
    save_ticker_lists(tmp_path, spot=[], futures=["MUUSDT", "SNDKUSDT"])
    bars = [
        {
            "open_time": i * 60_000,
            "open": 100.0 + i * 0.01,
            "high": 101.0 + i * 0.01,
            "low": 99.0 + i * 0.01,
            "close": 100.2 + i * 0.01,
            "volume": 10.0,
        }
        for i in range(40)
    ]
    for symbol in ("MUUSDT", "SNDKUSDT"):
        save_candles(tmp_path, bars, symbol=symbol, interval="15m", market="futures")
        save_candles(tmp_path, bars, symbol=symbol, interval="1h", market="futures")
    save_analysis_prefs(tmp_path, "15m", "1h", markets="futures")


def test_labels_read_before_journal_truncation(tmp_path: Path, monkeypatch: Any) -> None:
    from eurika.ml.llm_teacher import load_teacher_samples

    _seed_futures_snapshot(tmp_path)
    monkeypatch.setattr(ch, "_ensure_analysis_candles", lambda root: None)
    prose = "разбор импульса и структуры на двух ТФ. " * 400
    answer = (
        "### MUUSDT [fut]\n"
        + prose
        + '\nВердикт: брать импульс.\n{"samples":[{"symbol":"MUUSDT","market":"fut",'
        '"enter":"yes","side":"BUY","when":"now","leverage":2.0,'
        '"tp_pct":0.01,"sl_pct":0.008}]}'
    )
    assert len(answer) > ch.MAX_TEXT_CHARS

    out = ch.run_hourly_critique(
        tmp_path,
        now_ms=9_000_000,
        force=True,
        complete_chat=lambda _p: (answer, None),
        train=False,
    )
    assert out["teacher"]["stored"] == 1
    rows = load_teacher_samples(tmp_path)
    assert [r["symbol"] for r in rows] == ["MUUSDT"]
    assert rows[0]["side"] == "BUY"
    assert rows[0]["market"] == "futures"
    message = load_market_journal(tmp_path)[-1]["message"]
    assert '"samples"' not in message
    assert "метки MLP=1" in message


def test_labels_fall_back_to_prose_without_json(tmp_path: Path, monkeypatch: Any) -> None:
    from eurika.ml.llm_teacher import load_teacher_samples

    _seed_futures_snapshot(tmp_path)
    monkeypatch.setattr(ch, "_ensure_analysis_candles", lambda root: None)
    answer = (
        "### MUUSDT [fut]\n"
        "* **Вход**: да\n"
        "* **Когда**: сейчас\n"
        "* **Сторона**: BUY\n"
        "* **Почему**: импульсный отскок от нижней границы.\n"
        "* **Плечо**: 10.0\n"
        "* **Свои TP·SL**: TP: 984.80 (доля 0.015), SL: 960.50 (доля 0.010)\n"
        "\n---\n\n"
        "### SNDKUSDT\n"
        "* **Вход**: ждать\n"
        "* **Когда**: при откате к 1685.00\n"
        "* **Сторона**: HOLD\n"
        "* **Плечо**: не применимо\n"
        "\nВердикт: один вход, остальное ждать.\n"
    )

    out = ch.run_hourly_critique(
        tmp_path,
        now_ms=9_000_000,
        force=True,
        complete_chat=lambda _p: (answer, None),
        train=False,
    )
    assert out["teacher"]["stored"] == 2
    rows = {r["symbol"]: r for r in load_teacher_samples(tmp_path)}
    assert rows["MUUSDT"]["side"] == "BUY"
    assert rows["MUUSDT"]["enter"] == "yes"
    assert rows["MUUSDT"]["leverage"] == 10.0
    assert rows["MUUSDT"]["tp_pct"] == 0.015
    assert rows["MUUSDT"]["sl_pct"] == 0.010
    # No book tag in the header: the snapshot has one book for this symbol.
    assert rows["SNDKUSDT"]["market"] == "futures"
    assert rows["SNDKUSDT"]["side"] == "HOLD"


def test_markdown_parser_ignores_prices_and_bare_words() -> None:
    from eurika.ml.llm_teacher import parse_markdown_samples

    text = (
        "**XAUUSDT [fut]**\n"
        "* Вход: нет\n"
        "* Сторона: HOLD\n"
        "BUY\n"
        "* Свои TP·SL: TP = 1.5% (65738.10), SL = 0.8% (64248.93)\n"
    )
    samples = parse_markdown_samples(text)
    assert len(samples) == 1
    assert samples[0]["symbol"] == "XAUUSDT"
    assert samples[0]["market"] == "fut"
    assert samples[0]["tp_pct"] == 0.015
    assert samples[0]["sl_pct"] == 0.008
