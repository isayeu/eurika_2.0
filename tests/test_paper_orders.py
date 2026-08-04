"""Tests for paper pending entries + trailing stop."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.ml.exec_tf import simulate_exec_exit
from eurika.ml.paper_orders import (
    build_pending_order,
    choose_entry_style,
    load_pending_orders,
    process_pending_orders,
    save_pending_orders,
    simulate_pending_on_bar,
)


def _bar(ts: int, *, o: float = 100.0, h: float | None = None, l: float | None = None, c: float | None = None) -> dict:
    close = 100.0 if c is None else c
    return {
        "open_time": ts,
        "open": o,
        "high": close if h is None else h,
        "low": close if l is None else l,
        "close": close,
        "volume": 1.0,
    }


def test_choose_entry_style_breakout_vs_limit() -> None:
    assert choose_entry_style({"atr_burst": 0.8, "range_break": 0.0}) == "stop"
    assert choose_entry_style({"atr_burst": 0.0, "range_break": 0.0, "bb_pos": 0.9}) == "limit"
    assert choose_entry_style({"volatility": 0.01}) == "oco"
    assert choose_entry_style({}) == "market"


def test_retro_best_entry_style_prefers_better_buy_fill() -> None:
    from eurika.ml.paper_orders import retro_best_entry_style

    # Path dips to limit then recovers — limit BUY should beat market.
    t0 = 1_000
    candles = [
        _bar(t0, c=100.0, h=100.2, l=99.9),
        _bar(t0 + 60_000, c=99.7, h=100.0, l=99.6),  # touches ~0.15% limit
        _bar(t0 + 120_000, c=100.5, h=100.6, l=99.8),
    ]
    out = retro_best_entry_style(
        action="BUY",
        signal_px=100.0,
        candles_exec=candles,
        signal_ts=t0,
        pending_horizon_exec=5,
        limit_offset_pct=0.002,
        stop_offset_pct=0.002,
        invalidate_pct=0.05,
    )
    assert out["style"] in ("limit", "oco", "market")
    assert out["style"] is not None
    # Limit fill ~99.8 is better than market 100.0 for BUY
    lim = out["filled"].get("limit") or {}
    mkt = out["filled"].get("market") or {}
    if lim.get("status") == "filled" and mkt.get("status") == "filled":
        assert float(lim["entry"]) < float(mkt["entry"])
        assert out["style"] in ("limit", "oco")


def test_limit_buy_fill_and_invalidate() -> None:
    order = build_pending_order(
        symbol="BTCUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=1000,
        interval="15m",
        entry_style="limit",
        horizon=2,
        horizon_exec=30,
        exec_interval="1m",
        tp_pct=0.003,
        sl_pct=0.003,
        invalidate_pct=0.005,
        limit_offset_pct=0.002,
    )
    assert order["limit_px"] == pytest.approx(99.8, abs=1e-9)
    # Dump through invalidate before limit → cancel
    r = simulate_pending_on_bar(order, _bar(1060, h=99.6, l=99.4, c=99.5), bars_since_place=1)
    assert r["status"] == "cancelled"
    assert r["reason"] == "invalidate"
    # Touch limit
    order2 = dict(order)
    r2 = simulate_pending_on_bar(order2, _bar(1060, h=100.0, l=99.7, c=99.9), bars_since_place=1)
    assert r2["status"] == "filled"
    assert r2["entry"] == pytest.approx(99.8, abs=1e-9)


def test_stop_buy_and_oco_conflict() -> None:
    stop = build_pending_order(
        symbol="ETHUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=1000,
        interval="15m",
        entry_style="stop",
        horizon=2,
        horizon_exec=20,
        exec_interval="1m",
        tp_pct=0.003,
        sl_pct=0.003,
        stop_offset_pct=0.002,
    )
    r = simulate_pending_on_bar(stop, _bar(1060, h=100.3, l=100.0, c=100.2), bars_since_place=1)
    assert r["status"] == "filled"
    assert r["reason"] == "stop"

    oco = build_pending_order(
        symbol="ETHUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=1000,
        interval="15m",
        entry_style="oco",
        horizon=2,
        horizon_exec=20,
        exec_interval="1m",
        tp_pct=0.003,
        sl_pct=0.003,
        limit_offset_pct=0.002,
        stop_offset_pct=0.002,
    )
    # Wide bar hits both → cancel
    r2 = simulate_pending_on_bar(oco, _bar(1060, h=100.3, l=99.7, c=100.0), bars_since_place=1)
    assert r2["status"] == "cancelled"
    assert r2["reason"] == "oco_conflict"


def test_process_pending_fills(tmp_path: Path) -> None:
    t0 = 1_700_000_000_000
    order = build_pending_order(
        symbol="BTCUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=t0,
        interval="15m",
        entry_style="limit",
        horizon=2,
        horizon_exec=10,
        exec_interval="1m",
        tp_pct=0.003,
        sl_pct=0.003,
        trail_pct=0.002,
        limit_offset_pct=0.002,
        invalidate_pct=0.05,  # wide so fill wins
    )
    save_pending_orders(tmp_path, [order])
    candles = [
        _bar(t0, c=100.0),
        _bar(t0 + 60_000, h=100.0, l=99.7, c=99.85),
    ]
    cancels: list[dict] = []
    out = process_pending_orders(
        tmp_path,
        symbol="BTCUSDT",
        market="spot",
        candles_exec=candles,
        append_cancel_row=cancels.append,
    )
    assert out["cancelled"] == 0
    assert len(out["filled_positions"]) == 1
    pos = out["filled_positions"][0]
    assert pos["entry_style"] == "limit"
    assert pos["trail_pct"] == pytest.approx(0.002)


def test_trailing_stop_buy() -> None:
    t0 = 1_700_000_000_000
    bars = [_bar(t0 + i * 60_000, h=100.0, l=100.0, c=100.0) for i in range(6)]
    bars[1] = _bar(t0 + 60_000, h=100.8, l=100.55, c=100.6)
    bars[2] = _bar(t0 + 120_000, h=101.0, l=100.75, c=100.9)
    # Pull back into trail from extreme 101 with trail 0.3% → SL≈100.697
    bars[3] = _bar(t0 + 180_000, h=100.7, l=100.5, c=100.55)
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.05,
        sl_pct=0.02,
        trail_pct=0.003,
    )
    assert sim and sim["ready"]
    assert sim["reason"] == "trail"
    assert float(sim["exit"]) == pytest.approx(101.0 * (1.0 - 0.003), abs=1e-6)


def test_trail_does_not_fire_before_favorable_move() -> None:
    """Trail must not act as a tighter SL from entry (MFE=0 case)."""
    t0 = 1_700_000_000_000
    bars = [
        _bar(t0, h=100.0, l=100.0, c=100.0),
        _bar(t0 + 60_000, h=100.1, l=99.5, c=99.6),  # tiny uptick, then dip
    ]
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.05,
        sl_pct=0.02,
        trail_pct=0.008,
    )
    assert sim is not None
    assert not sim.get("ready"), sim
    assert sim.get("reason") == "wait"


def test_trail_activates_only_after_full_trail_distance() -> None:
    t0 = 1_700_000_000_000
    # Move +0.5% — less than trail 0.8% → still no trail; only hard SL matters
    bars = [
        _bar(t0, h=100.0, l=100.0, c=100.0),
        _bar(t0 + 60_000, h=100.5, l=100.2, c=100.4),
        _bar(t0 + 120_000, h=100.4, l=99.7, c=99.8),
    ]
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.05,
        sl_pct=0.02,
        trail_pct=0.008,
    )
    assert sim and not sim.get("ready")

    # Move +1.0% (>= trail 0.8%), then pull back through trail SL
    bars2 = [
        _bar(t0, h=100.0, l=100.0, c=100.0),
        _bar(t0 + 60_000, h=101.0, l=100.5, c=100.8),
        _bar(t0 + 120_000, h=100.7, l=100.1, c=100.2),  # trail SL = 101*0.992=100.192
    ]
    sim2 = simulate_exec_exit(
        bars2,
        entry_ts=bars2[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.05,
        sl_pct=0.02,
        trail_pct=0.008,
    )
    assert sim2 and sim2["ready"]
    assert sim2["reason"] == "trail"
    assert float(sim2["exit"]) == pytest.approx(101.0 * (1.0 - 0.008), abs=1e-6)


def test_trail_seed_ignored_when_entry_bar_in_window() -> None:
    """Persisted future extreme must not false-trigger trail on an early re-walk bar.

    Repro: tick N walks to a deep favorable low and saves trail_extreme; tick N+1
    re-walks from entry with that seed → early bar high hits phantom trail SL.
    """
    t0 = 1_700_000_000_000
    entry = 63118.08065
    bars = [
        _bar(t0, h=63155.81, l=63116.96, c=63116.96),
        _bar(t0 + 60_000, h=63144.0, l=63116.96, c=63143.99),  # early bar
        _bar(t0 + 120_000, h=63170.0, l=63148.0, c=63157.0),
        # Deep favorable low (≥ trail 0.2%) — only exists later
        _bar(t0 + 180_000, h=63023.48, l=62976.0, c=63000.0),
    ]
    # First pass: discover extreme, still waiting (no bounce to trail SL)
    sim1 = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=entry,
        action="SELL",
        horizon_exec=120,
        tp_pct=0.003,
        sl_pct=0.003,
        trail_pct=0.002,
        trail_extreme=entry,
    )
    assert sim1 and not sim1.get("ready")
    assert float(sim1["trail_extreme"]) == pytest.approx(62976.0, abs=1e-6)

    # Second pass with persisted extreme — must NOT exit on early bar
    sim2 = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=entry,
        action="SELL",
        horizon_exec=120,
        tp_pct=0.003,
        sl_pct=0.003,
        trail_pct=0.002,
        trail_extreme=float(sim1["trail_extreme"]),
    )
    assert sim2 and not sim2.get("ready"), sim2
    assert float(sim2["trail_extreme"]) == pytest.approx(62976.0, abs=1e-6)


def test_sibling_fill_cancels_other_pending(tmp_path: Path) -> None:
    """When one pending fills, other pendings on the same pair are cancelled."""
    t0 = 1_700_000_000_000
    lim = build_pending_order(
        symbol="BTCUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=t0,
        interval="15m",
        entry_style="limit",
        horizon=2,
        horizon_exec=20,
        exec_interval="1m",
        tp_pct=0.01,
        sl_pct=0.01,
        limit_offset_pct=0.002,
        invalidate_pct=0.05,
    )
    stop = build_pending_order(
        symbol="BTCUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=t0,
        interval="15m",
        entry_style="stop",
        horizon=2,
        horizon_exec=20,
        exec_interval="1m",
        tp_pct=0.01,
        sl_pct=0.01,
        stop_offset_pct=0.002,
        invalidate_pct=0.05,
    )
    save_pending_orders(tmp_path, [lim, stop])
    # Bar dips to fill limit only (not stop above)
    candles = [
        _bar(t0, c=100.0),
        _bar(t0 + 60_000, h=100.0, l=99.7, c=99.85),
    ]
    cancels: list[dict] = []
    out = process_pending_orders(
        tmp_path,
        symbol="BTCUSDT",
        market="spot",
        candles_exec=candles,
        append_cancel_row=cancels.append,
    )
    assert len(out["filled_positions"]) == 1
    assert out["pending_left"] == 0
    assert any(r.get("exit_reason") == "cancel_sibling_fill" for r in cancels)
    assert load_pending_orders(tmp_path) == []
