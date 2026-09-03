"""Tests for unified holistic cash pool."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.ml.earn_monitor import apply_earn_actions, ensure_earn_portfolio
from eurika.ml.holistic_portfolio import (
    ensure_holistic,
    load_holistic,
    reconcile_holistic,
    total_equity,
)
from eurika.ml.assistant_paper import apply_assistant_actions, ensure_portfolio, load_portfolio
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


def test_holistic_earn_and_trade_share_cash(tmp_path: Path) -> None:
    ensure_holistic(tmp_path)
    rates = {"products": [{"asset": "USDT", "kind": "flexible", "apr": 0.05, "product_id": "x"}]}
    dep = apply_earn_actions(
        tmp_path,
        [{"product": "earn", "action": "deposit", "asset": "USDT", "amount_usdt": 300}],
        rates=rates,
    )
    assert int(dep["applied"]["deposit"]) == 1
    h = load_holistic(tmp_path)
    assert float(h["cash_free_usdt"]) == 700.0
    assert float(h["earn_principal_usdt"]) == 300.0

    save_ticker_lists(tmp_path, futures=["BTCUSDT"])
    bars = _bars(50, 50000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol="BTCUSDT", interval=iv, market="futures")
    ensure_portfolio(tmp_path)
    trade = apply_assistant_actions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": 40000.0,
                "tp_pct": 0.01,
                "sl_pct": 0.02,
            }
        ],
    )
    assert int(trade["applied"]["place"]) == 1
    h2 = reconcile_holistic(tmp_path)
    assert float(h2["cash_free_usdt"]) < 700.0
    assert float(h2["trade_margin_usdt"]) > 0.0
    assert abs(total_equity(h2) - 1000.0) < 0.01


def test_migrate_legacy_consolidates_to_one_pool(tmp_path: Path) -> None:
    ensure_earn_portfolio(tmp_path)
    ensure_portfolio(tmp_path)
    from eurika.ml.holistic_portfolio import migrate_legacy_if_needed

    assert migrate_legacy_if_needed(tmp_path) is True
    h = load_holistic(tmp_path)
    assert float(h["start_equity_usdt"]) == 1000.0
    assert float(h["cash_free_usdt"]) <= 1000.0


def test_migrate_legacy_subtracts_open_margin(tmp_path: Path) -> None:
    from eurika.ml.assistant_paper import save_opens, save_portfolio

    ensure_portfolio(tmp_path)
    port = load_portfolio(tmp_path)
    port["realized_pnl_usdt"] = 0.0
    save_portfolio(tmp_path, port)
    save_opens(
        tmp_path,
        [
            {
                "symbol": "XRPUSDT",
                "market": "futures",
                "action": "BUY",
                "entry": 1.38,
                "margin_usdt": 6.0,
                "notional_usdt": 12.0,
                "leverage": 2.0,
            }
        ],
    )
    from eurika.ml.holistic_portfolio import migrate_legacy_if_needed

    assert migrate_legacy_if_needed(tmp_path) is True
    h = load_holistic(tmp_path)
    assert float(h["trade_margin_usdt"]) == 6.0
    assert float(h["cash_free_usdt"]) == 994.0
    assert abs(total_equity(h) - 1000.0) < 0.01


def test_repair_legacy_margin_double_count(tmp_path: Path) -> None:
    from eurika.ml.earn_monitor import save_earn_positions
    from eurika.ml.holistic_portfolio import holistic_portfolio_path, save_holistic

    save_earn_positions(
        tmp_path,
        [
            {
                "id": "earn-test",
                "asset": "USDT",
                "kind": "flexible",
                "amount": 800.0,
                "apr": 0.0275,
                "accrued_usdt": 0.00086,
            }
        ],
    )
    save_holistic(
        tmp_path,
        {
            **ensure_holistic(tmp_path),
            "migrated_legacy": True,
            "cash_free_usdt": 206.168,
            "earn_principal_usdt": 800.0,
            "earn_accrued_usdt": 0.00086,
            "trade_margin_usdt": 0.0,
            "trade_realized_pnl_usdt": 0.168,
            "equity_usdt": 1006.16886,
        },
    )
    h = reconcile_holistic(tmp_path)
    assert h.get("legacy_margin_repaired") is True
    assert float(h.get("legacy_margin_repair_usdt") or 0) == pytest.approx(6.0, abs=0.01)
    assert float(h["cash_free_usdt"]) == pytest.approx(200.168, abs=0.01)
    assert float(h["equity_usdt"]) == pytest.approx(1000.16886, abs=0.001)
    assert holistic_portfolio_path(tmp_path).is_file()


def test_trade_auto_redeems_earn_when_cash_low(tmp_path: Path) -> None:
    from eurika.ml.earn_monitor import save_earn_positions, save_earn_portfolio
    from eurika.ml.holistic_portfolio import save_holistic

    save_earn_portfolio(
        tmp_path,
        {
            "version": 1,
            "start_equity_usdt": 1000.0,
            "equity_usdt": 800.0,
            "cash_usdt": 0.0,
            "principal_usdt": 800.0,
            "accrued_usdt": 0.0,
        },
    )
    save_earn_positions(
        tmp_path,
        [
            {
                "id": "earn-flex",
                "asset": "USDT",
                "kind": "flexible",
                "amount": 800.0,
                "apr": 0.03,
                "accrued_usdt": 0.0,
            }
        ],
    )
    save_holistic(
        tmp_path,
        {
            **ensure_holistic(tmp_path),
            "migrated_legacy": True,
            "cash_free_usdt": 0.17,
            "earn_principal_usdt": 800.0,
            "earn_accrued_usdt": 0.0,
            "trade_margin_usdt": 0.0,
            "equity_usdt": 1000.17,
        },
    )

    save_ticker_lists(tmp_path, futures=["BTCUSDT"])
    bars = _bars(50, 50000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol="BTCUSDT", interval=iv, market="futures")
    ensure_portfolio(tmp_path)

    trade = apply_assistant_actions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": 40000.0,
                "tp_pct": 0.01,
                "sl_pct": 0.02,
            }
        ],
    )
    assert int(trade["applied"]["place"]) == 1
    h = reconcile_holistic(tmp_path)
    assert float(h["trade_margin_usdt"]) > 0.0
    assert float(h["earn_principal_usdt"]) < 800.0
    assert float(h["cash_free_usdt"]) >= 0.0


def test_place_replace_releases_old_pending_margin(tmp_path: Path) -> None:
    from eurika.ml.earn_monitor import save_earn_positions, save_earn_portfolio
    from eurika.ml.holistic_portfolio import save_holistic

    save_earn_portfolio(
        tmp_path,
        {
            "version": 1,
            "start_equity_usdt": 1000.0,
            "equity_usdt": 0.0,
            "cash_usdt": 0.0,
            "principal_usdt": 0.0,
            "accrued_usdt": 0.0,
        },
    )
    save_earn_positions(tmp_path, [])
    save_holistic(
        tmp_path,
        {
            **ensure_holistic(tmp_path),
            "migrated_legacy": True,
            "legacy_margin_repaired": True,
            "cash_free_usdt": 1000.0,
            "earn_principal_usdt": 0.0,
            "earn_accrued_usdt": 0.0,
            "trade_margin_usdt": 0.0,
            "equity_usdt": 1000.0,
        },
    )
    save_ticker_lists(tmp_path, futures=["BTCUSDT"])
    bars = _bars(50, 50000.0)
    for iv in ("15m", "1h", "1m"):
        save_candles(tmp_path, bars, symbol="BTCUSDT", interval=iv, market="futures")
    ensure_portfolio(tmp_path)

    first = apply_assistant_actions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": 40000.0,
                "tp_pct": 0.01,
                "sl_pct": 0.02,
            }
        ],
    )
    assert int(first["applied"]["place"]) == 1
    h1 = reconcile_holistic(tmp_path)
    m1 = float(h1["trade_margin_usdt"])
    assert m1 > 0

    second = apply_assistant_actions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": 39000.0,
                "tp_pct": 0.01,
                "sl_pct": 0.02,
            }
        ],
    )
    assert int(second["applied"]["place"]) == 1
    h2 = reconcile_holistic(tmp_path)
    assert abs(float(h2["equity_usdt"]) - 1000.0) < 0.05
    assert float(h2["trade_margin_usdt"]) > 0
    # one pending only — margin not double-locked
    assert float(h2["cash_free_usdt"]) + float(h2["trade_margin_usdt"]) == pytest.approx(1000.0, abs=0.05)


def test_restore_holistic_start_equity(tmp_path: Path) -> None:
    from eurika.ml.holistic_portfolio import restore_holistic_start_equity, save_holistic

    save_holistic(
        tmp_path,
        {
            **ensure_holistic(tmp_path),
            "migrated_legacy": True,
            "legacy_margin_repaired": True,
            "cash_free_usdt": 980.0,
            "earn_principal_usdt": 0.0,
            "earn_accrued_usdt": 0.0,
            "trade_margin_usdt": 0.0,
            "trade_realized_pnl_usdt": 0.168,
            "equity_usdt": 980.0,
        },
    )
    h = restore_holistic_start_equity(tmp_path)
    assert float(h["equity_usdt"]) == pytest.approx(1000.168, abs=0.01)
