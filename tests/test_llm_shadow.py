"""Tests for LLM shadow portfolio."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.ml.cursor_hourly import run_hourly_critique
from eurika.ml.llm_shadow import (
    apply_shadow_actions,
    ingest_pending_fills,
    load_shadow_opens,
    load_shadow_portfolio,
    load_shadow_trades,
    open_from_teacher_rows,
    parse_shadow_actions,
    resolve_llm_shadow,
)
from eurika.ml.llm_shadow_orders import load_shadow_pending
from eurika.ml.market_store import candles_path, load_candles, save_candles
from eurika.ml.paper_portfolio import ensure_portfolio, load_portfolio


def _seed_symbol(root: Path, symbol: str = "MUUSDT", market: str = "futures") -> None:
    bars_15m = []
    for i in range(20):
        ts = i * 900_000
        bars_15m.append(
            {
                "open_time": ts,
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "volume": 1.0,
            }
        )
    bars_1m = []
    for i in range(20):
        ts = 17_100_000 + i * 60_000
        bars_1m.append(
            {
                "open_time": ts,
                "open": 100.0,
                "high": 100.2,
                "low": 99.8,
                "close": 100.0,
                "volume": 1.0,
            }
        )
    save_candles(root, bars_15m, symbol=symbol, interval="15m", market=market)
    save_candles(root, bars_1m, symbol=symbol, interval="1m", market=market)


def _append_1m_rally(
    root: Path,
    *,
    start_ts: int = 18_300_000,
    n: int = 10,
    symbol: str = "MUUSDT",
    market: str = "futures",
) -> None:
    """Bars printed after the entry, tagging TP so the position can resolve."""
    bars = load_candles(root, symbol, "1m", market=market)
    bars += [
        {
            "open_time": start_ts + i * 60_000,
            "open": 100.0,
            "high": 101.5,
            "low": 99.9,
            "close": 101.2,
            "volume": 1.0,
        }
        for i in range(n)
    ]
    save_candles(root, bars, symbol=symbol, interval="1m", market=market)


def test_open_and_resolve_llm_shadow_keeps_paper_bank_isolated(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)

    teacher_rows = [
        {
            "ts": 17_100_000,
            "symbol": "MUUSDT",
            "market": "futures",
            "enter": "yes",
            "side": "BUY",
            "interval": "15m",
            "tp_pct": 0.01,
            "sl_pct": 0.01,
            "trail_pct": 0.0,
            "source": "cursor",
        }
    ]
    opened = open_from_teacher_rows(tmp_path, teacher_rows)
    assert opened["opened"] == 1
    assert len(load_shadow_opens(tmp_path)) == 1
    # Entry is stamped on the exec TF, so nothing can fill until new bars print.
    assert load_shadow_opens(tmp_path)[0]["entry_ts"] == 18_240_000
    assert resolve_llm_shadow(tmp_path, now_ms=18_300_000)["closed"] == 0

    _append_1m_rally(tmp_path)
    before_paper = load_portfolio(tmp_path)
    resolved = resolve_llm_shadow(tmp_path, now_ms=18_900_000)
    assert resolved["closed"] == 1
    assert load_shadow_opens(tmp_path) == []
    trades = load_shadow_trades(tmp_path)
    assert len(trades) == 1
    assert trades[0]["shadow_llm"] is True
    assert trades[0]["source"] == "llm_shadow"

    shadow_port = load_shadow_portfolio(tmp_path)
    assert shadow_port["equity_usdt"] > shadow_port["start_equity_usdt"]
    after_paper = load_portfolio(tmp_path)
    assert after_paper["equity_usdt"] == before_paper["equity_usdt"]


def test_hourly_hook_opens_llm_shadow_and_reports_it(tmp_path: Path, monkeypatch: object) -> None:
    _seed_symbol(tmp_path)
    monkeypatch.setattr("eurika.ml.cursor_hourly._ensure_analysis_candles", lambda root: None)
    monkeypatch.setattr(
        "eurika.ml.cursor_hourly_brief.collect_ticker_cards",
        lambda root, now_ms: [
            {
                "symbol": "MUUSDT",
                "market": "futures",
                "interval": "15m",
                "interval2": "1h",
                "feature_vec": [0.0] * 24,
                "tp_pct": 0.01,
                "sl_pct": 0.01,
                "trail_pct": 0.0,
            }
        ],
    )
    answer = (
        'анализ.\n{"samples":[{"symbol":"MUUSDT","market":"fut","enter":"yes","side":"BUY",'
        '"when":"now","tp_pct":0.01,"sl_pct":0.01}]}'
    )
    out = run_hourly_critique(
        tmp_path,
        now_ms=17_200_000,
        force=True,
        complete_chat=lambda _p: (answer, None),
        train=False,
    )
    assert out["teacher"]["stored"] == 1
    assert out["shadow"]["opened"] == 1
    assert "LLM shadow" in out["message"]
    opens = load_shadow_opens(tmp_path)
    assert len(opens) == 1
    assert opens[0]["market"] == "futures"

    _append_1m_rally(tmp_path)
    assert resolve_llm_shadow(tmp_path, now_ms=18_900_000)["closed"] == 1
    assert len(load_shadow_trades(tmp_path)) == 1


def test_shadow_actions_accept_percent_style_tp_sl(tmp_path: Path) -> None:
    """LLM sometimes sends tp_pct=1.0 meaning 1%; store as fraction, then R:R floor."""
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    res = apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"place","side":"BUY",'
            '"entry_style":"limit","limit_px":99.0,"tp_pct":1.0,"sl_pct":0.7,"trail_pct":0.5}]}'
        ),
    )
    assert res["applied"]["place"] == 1
    pending = load_shadow_pending(tmp_path)[0]
    # 1.0 → 0.01, 0.7 → 0.007; ratio 1.43 < 1.5 → TP bumped to 0.0105
    assert abs(pending["sl_pct"] - 0.007) < 1e-9
    assert pending["tp_pct"] >= pending["sl_pct"] * 1.5
    assert abs(pending["tp_pct"] - 0.0105) < 1e-9
    assert abs(pending["trail_pct"] - 0.005) < 1e-9


def test_teacher_row_does_not_duplicate_position_opened_by_action(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    actions = parse_shadow_actions(
        '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"open","side":"BUY",'
        '"tp_pct":0.01,"sl_pct":0.01}]}'
    )
    assert apply_shadow_actions(tmp_path, actions)["applied"]["open"] == 1

    # Teacher rows carry harvest wall-clock ts, so they must not re-open the
    # same symbol the LLM just opened by explicit action.
    opened = open_from_teacher_rows(
        tmp_path,
        [
            {
                "ts": 1_800_000_000_000,
                "symbol": "MUUSDT",
                "market": "futures",
                "enter": "yes",
                "side": "BUY",
                "interval": "15m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
            }
        ],
    )
    assert opened["opened"] == 0
    assert len(load_shadow_opens(tmp_path)) == 1

    add = parse_shadow_actions(
        '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"add","side":"BUY",'
        '"tp_pct":0.01,"sl_pct":0.01}]}'
    )
    assert apply_shadow_actions(tmp_path, add)["applied"]["add"] == 1
    assert len(load_shadow_opens(tmp_path)) == 2


def test_shadow_actions_accept_fut_market_alias(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    open_from_teacher_rows(
        tmp_path,
        [
            {
                "ts": 17_100_000,
                "symbol": "MUUSDT",
                "market": "futures",
                "enter": "yes",
                "side": "BUY",
                "interval": "15m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
            }
        ],
    )
    actions = parse_shadow_actions(
        '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"update","tp_pct":0.05}]}'
    )
    res = apply_shadow_actions(tmp_path, actions)
    assert res["applied"]["update"] == 1
    assert res["applied"]["ignored"] == 0
    assert load_shadow_opens(tmp_path)[0]["tp_pct"] == 0.05


def test_stale_entry_is_force_closed_and_releases_margin(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    open_from_teacher_rows(
        tmp_path,
        [
            {
                "ts": 17_100_000,
                "symbol": "MUUSDT",
                "market": "futures",
                "enter": "yes",
                "side": "BUY",
                "interval": "15m",
                "tp_pct": 0.9,
                "sl_pct": 0.9,
            }
        ],
    )
    assert load_shadow_portfolio(tmp_path)["margin_used_usdt"] > 0

    # Entry scrolls out of the retained 1m window: without a force close the
    # position would wait forever and keep its margin locked.
    far = [
        {
            "open_time": 40_000_000 + i * 60_000,
            "open": 100.0,
            "high": 100.2,
            "low": 99.9,
            "close": 100.1,
            "volume": 1.0,
        }
        for i in range(30)
    ]
    candles_path(tmp_path, "MUUSDT", "1m", market="futures").write_text(
        json.dumps(far), encoding="utf-8"
    )
    resolved = resolve_llm_shadow(tmp_path, now_ms=40_000_000 + 30 * 60_000)
    assert resolved["closed"] == 1
    assert load_shadow_opens(tmp_path) == []
    assert load_shadow_portfolio(tmp_path)["margin_used_usdt"] == 0.0
    assert load_shadow_trades(tmp_path)[-1]["exit_reason"] in {"stale", "max_age"}


def test_parse_and_apply_shadow_actions(tmp_path: Path) -> None:
    _seed_symbol(tmp_path)
    open_from_teacher_rows(
        tmp_path,
        [
            {
                "ts": 17_100_000,
                "symbol": "MUUSDT",
                "market": "futures",
                "enter": "yes",
                "side": "BUY",
                "interval": "15m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
            }
        ],
    )
    text = (
        '{"shadow_actions":['
        '{"symbol":"MUUSDT","market":"futures","action":"update","tp_pct":0.02,"sl_pct":0.005},'
        '{"symbol":"MUUSDT","market":"futures","action":"close"}]}'
    )
    actions = parse_shadow_actions(text)
    assert len(actions) == 2
    res = apply_shadow_actions(tmp_path, actions[:1])
    assert res["applied"]["update"] == 1
    assert load_shadow_opens(tmp_path)[0]["tp_pct"] == 0.02
    res = apply_shadow_actions(tmp_path, actions[1:])
    assert res["applied"]["close"] == 1
    assert len(load_shadow_trades(tmp_path)) == 1


def test_place_stop_pending_fills_then_resolves(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    before_paper = load_portfolio(tmp_path)
    actions = parse_shadow_actions(
        '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"place","side":"SELL",'
        '"entry_style":"stop","stop_px":99.5,"tp_pct":0.01,"sl_pct":0.01,'
        '"pending_horizon_exec":30}]}'
    )
    res = apply_shadow_actions(tmp_path, actions)
    assert res["applied"]["place"] == 1
    assert load_shadow_opens(tmp_path) == []
    pending = load_shadow_pending(tmp_path)
    assert len(pending) == 1
    assert pending[0]["entry_style"] == "stop"
    assert pending[0]["stop_px"] == 99.5
    assert load_shadow_portfolio(tmp_path)["margin_used_usdt"] > 0

    # Break down through the stop on later 1m bars.
    bars = load_candles(tmp_path, "MUUSDT", "1m", market="futures")
    place_ts = int(pending[0]["ts"])
    bars += [
        {
            "open_time": place_ts + (i + 1) * 60_000,
            "open": 100.0,
            "high": 100.1,
            "low": 99.4,
            "close": 99.45,
            "volume": 1.0,
        }
        for i in range(3)
    ]
    save_candles(tmp_path, bars, symbol="MUUSDT", interval="1m", market="futures")

    filled = ingest_pending_fills(tmp_path, now_ms=place_ts + 5 * 60_000)
    assert filled["filled"] == 1
    assert load_shadow_pending(tmp_path) == []
    opens = load_shadow_opens(tmp_path)
    assert len(opens) == 1
    assert opens[0]["action"] == "SELL"
    assert opens[0]["entry"] == 99.5
    assert opens[0]["entry_style"] == "stop"

    # Manage pending/open on next cycle: update TP on the open.
    upd = apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"update","tp_pct":0.02}]}'
        ),
    )
    assert upd["applied"]["update"] == 1
    assert load_shadow_opens(tmp_path)[0]["tp_pct"] == 0.02
    assert load_portfolio(tmp_path)["equity_usdt"] == before_paper["equity_usdt"]


def test_cancel_pending_releases_margin_without_opening(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"place","side":"BUY",'
            '"entry_style":"limit","limit_px":99.0,"tp_pct":0.01,"sl_pct":0.01}]}'
        ),
    )
    assert len(load_shadow_pending(tmp_path)) == 1
    assert load_shadow_portfolio(tmp_path)["margin_used_usdt"] > 0
    cancelled = apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"cancel"}]}'
        ),
    )
    assert cancelled["applied"]["cancel"] == 1
    assert load_shadow_pending(tmp_path) == []
    assert load_shadow_opens(tmp_path) == []
    assert load_shadow_portfolio(tmp_path)["margin_used_usdt"] == 0.0


def test_teacher_skips_when_pending_exists(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed_symbol(tmp_path)
    apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"MUUSDT","market":"fut","action":"place","side":"SELL",'
            '"entry_style":"stop","stop_px":99.0,"tp_pct":0.01,"sl_pct":0.01}]}'
        ),
    )
    opened = open_from_teacher_rows(
        tmp_path,
        [
            {
                "ts": 17_100_000,
                "symbol": "MUUSDT",
                "market": "futures",
                "enter": "yes",
                "side": "SELL",
                "interval": "15m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
            }
        ],
    )
    assert opened["opened"] == 0
    assert load_shadow_opens(tmp_path) == []
    assert len(load_shadow_pending(tmp_path)) == 1
