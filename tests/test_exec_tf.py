"""Tests for dual-TF execution (signal on main, TP/SL on 1m)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.ml.exec_tf import (
    EXIT_FEATURE_NAMES,
    find_entry_index,
    main_horizon_to_exec,
    path_excursions,
    retro_exit_samples,
    simulate_exec_exit,
)
from eurika.ml import live_paper as lp
from eurika.ml import market_store as ms
from eurika.ml import market_model as mm


def test_main_horizon_to_exec_15m() -> None:
    assert main_horizon_to_exec(2, "15m", "1m") == 30
    assert main_horizon_to_exec(1, "1h", "1m") == 60
    assert main_horizon_to_exec(1, "1m", "1m") == 1


def _m1(n: int, *, entry: float = 100.0, step_ms: int = 60_000) -> list[dict]:
    t0 = 1_700_000_000_000
    rows = []
    px = entry
    for i in range(n):
        rows.append(
            {
                "open_time": t0 + i * step_ms,
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": 1.0,
            }
        )
    return rows


def test_find_entry_index_scrolled_out_returns_minus_one() -> None:
    """Ancient entry must not remap to bar 0 (that restarts the horizon forever)."""
    bars = _m1(5, entry=100.0)
    assert find_entry_index(bars, bars[0]["open_time"]) == 0
    assert find_entry_index(bars, bars[0]["open_time"] - 60_000) == -1
    assert find_entry_index(bars, bars[-1]["open_time"] + 60_000) == -1
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"] - 60_000,
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.01,
        sl_pct=0.01,
    )
    assert sim is None


def test_simulate_buy_tp() -> None:
    bars = _m1(5, entry=100.0)
    bars[0]["close"] = 100.0
    bars[2]["high"] = 100.5  # +0.5%
    bars[2]["close"] = 100.4
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.003,
        sl_pct=0.003,
    )
    assert sim and sim["ready"]
    assert sim["reason"] == "tp"
    assert abs(float(sim["exit"]) - 100.3) < 1e-9


def test_simulate_buy_sl_pessimistic_same_bar() -> None:
    bars = _m1(3, entry=100.0)
    bars[1]["high"] = 100.5
    bars[1]["low"] = 99.5
    bars[1]["close"] = 100.0
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=10,
        tp_pct=0.003,
        sl_pct=0.003,
    )
    assert sim and sim["ready"]
    assert sim["reason"] == "sl"
    assert abs(float(sim["exit"]) - 99.7) < 1e-9


def test_simulate_wait_then_horizon() -> None:
    bars = _m1(3, entry=100.0)
    wait = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=5,
        tp_pct=0.05,
        sl_pct=0.05,
    )
    assert wait and not wait["ready"]
    assert wait["reason"] == "wait"

    bars = _m1(6, entry=100.0)
    done = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=5,
        tp_pct=0.05,
        sl_pct=0.05,
    )
    assert done and done["ready"]
    assert done["reason"] == "horizon"


def test_simulate_time_stop_after_mfe_fade() -> None:
    """Anti-horizon: after MFE arms, exit on close when move is given back."""
    bars = _m1(25, entry=100.0)
    for i in range(1, 6):
        bars[i]["high"] = 100.6
        bars[i]["close"] = 100.5
        bars[i]["low"] = 100.0
    for i in range(6, 20):
        bars[i]["high"] = 100.1
        bars[i]["low"] = 99.95
        bars[i]["close"] = 100.0
    sim = simulate_exec_exit(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        horizon_exec=40,
        tp_pct=0.01,
        sl_pct=0.02,
        trail_pct=0.0,
    )
    assert sim and sim["ready"]
    assert sim["reason"] == "time_stop"
    assert int(sim["bars_held"]) < 40
    assert abs(float(sim["exit"]) - 100.0) < 1e-9


def test_should_time_stop_helpers() -> None:
    from eurika.ml.exec_tf import should_time_stop, time_stop_arm_threshold

    assert abs(time_stop_arm_threshold(0.01) - 0.0028) < 1e-12
    assert should_time_stop(
        mfe_pct=0.006,
        cur_fav_pct=0.0,
        bars_held=10,
        horizon_exec=40,
        tp_pct=0.01,
    )
    assert not should_time_stop(
        mfe_pct=0.001,
        cur_fav_pct=0.0,
        bars_held=10,
        horizon_exec=40,
        tp_pct=0.01,
    )


def test_live_tick_exec_1m_resolves_tp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spot path: signal on 15m, exit on 1m TP."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    root = tmp_path
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(50):
        o = px
        px = px * (1.002 if i % 3 else 0.999)
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 10.0,
            }
        )
    ms.save_candles(root, main, symbol="BTCUSDT", interval="15m", market="spot")

    m1 = []
    for i in range(10):
        c = 100.0
        hi, lo = c, c
        if i == 2:
            hi = 100.5
            c = 100.4
        m1.append(
            {
                "open_time": t0 + i * 60_000,
                "open": 100.0,
                "high": hi,
                "low": lo,
                "close": c,
                "volume": 1.0,
            }
        )
    ms.save_candles(root, m1, symbol="BTCUSDT", interval="1m", market="spot")

    lp.save_open_positions(
        root,
        [
            {
                "ts": m1[0]["open_time"],
                "signal_ts": main[-1]["open_time"],
                "symbol": "BTCUSDT",
                "interval": "15m",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "horizon_exec": 30,
                "exec_interval": "1m",
                "tp_pct": 0.003,
                "sl_pct": 0.003,
                "features": {},
                "feature_vec": [0.0] * 12,
                "source": "test",
            }
        ],
    )

    def _fake_fetch(symbol, *, interval="15m", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        root,
        symbol="BTCUSDT",
        interval="15m",
        horizon=2,
        window=16,
        market="spot",
        exec_interval="1m",
        tp_pct=0.003,
        sl_pct=0.003,
        explore=False,
        micro_train=False,
        allow_open=False,
        fetch=_fake_fetch,
    )
    assert r["ok"]
    assert r["resolved"] == 1
    kinds = [e.get("kind") for e in r["events"]]
    assert "outcome" in kinds
    # Timing fields persisted on paper row
    from eurika.ml.paper_trader import load_paper_trades

    trades = load_paper_trades(root)
    assert trades
    assert "mfe_pct" in trades[-1]
    assert "entry_timing_score" in trades[-1]
    assert mm.load_exit_samples(root)  # retro samples written


def test_path_excursions_buy() -> None:
    bars = _m1(5, entry=100.0)
    bars[1]["high"] = 100.8
    bars[1]["close"] = 100.5
    bars[2]["low"] = 99.5
    bars[2]["close"] = 99.8
    bars[3]["high"] = 101.0
    bars[3]["close"] = 100.9
    exc = path_excursions(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        exit_ts=bars[3]["open_time"],
    )
    assert exc["mfe_pct"] == pytest.approx(0.01, abs=1e-9)
    assert exc["mae_pct"] == pytest.approx(0.005, abs=1e-9)
    assert exc["entry_timing_score"] == pytest.approx(0.005, abs=1e-9)


def test_retro_exit_samples_hold_then_close() -> None:
    bars = _m1(6, entry=100.0)
    # Rise then slip: peak at bar 3
    for i, c in enumerate([100.0, 100.2, 100.5, 100.8, 100.4, 100.3]):
        bars[i]["close"] = c
        bars[i]["high"] = c
        bars[i]["low"] = c
    samples = retro_exit_samples(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        exit_ts=bars[5]["open_time"],
        horizon_exec=10,
        tp_pct=0.01,
        sl_pct=0.01,
        fee=0.0,
    )
    assert samples
    assert all(len(s["feature_vec"]) == len(EXIT_FEATURE_NAMES) for s in samples)
    labels = [s["exit_label"] for s in samples]
    # bars 1,2 before peak(3) → HOLD; peak CLOSE; after slip CLOSE
    assert labels[0] == "HOLD"
    assert labels[1] == "HOLD"
    assert labels[2] == "CLOSE"  # peak
    assert "CLOSE" in labels[3:]


def test_train_exit_policy(tmp_path: Path) -> None:
    bars = _m1(8, entry=100.0)
    for i in range(8):
        bars[i]["close"] = 100.0 + i * 0.2
        bars[i]["high"] = bars[i]["close"]
        bars[i]["low"] = bars[i]["close"]
    samples = retro_exit_samples(
        bars,
        entry_ts=bars[0]["open_time"],
        entry=100.0,
        action="BUY",
        exit_ts=bars[7]["open_time"],
        horizon_exec=10,
        fee=0.0,
    )
    # Need >= 8 samples: duplicate path a few times
    for _ in range(3):
        mm.append_exit_samples(tmp_path, samples)
    out = mm.train_market_exit_policy(tmp_path, epochs=15)
    assert out["ok"], out.get("error")
    pred = mm.predict_exit(tmp_path, samples[-1]["feature_vec"])
    assert pred["action"] in ("HOLD", "CLOSE")
    assert pred["source"] == "model"


def test_live_tick_model_early_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    root = tmp_path
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(50):
        o = px
        px = px * 1.001
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px),
                "low": min(o, px),
                "close": px,
                "volume": 1.0,
            }
        )
    ms.save_candles(root, main, symbol="BTCUSDT", interval="15m", market="spot")
    m1 = []
    for i in range(8):
        # Peak ~0.6% — above half TP (0.5%) but below full TP (1%)
        c = 100.0 + min(i, 4) * 0.15
        m1.append(
            {
                "open_time": t0 + i * 60_000,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": 1.0,
            }
        )
    ms.save_candles(root, m1, symbol="BTCUSDT", interval="1m", market="spot")
    lp.save_open_positions(
        root,
        [
            {
                "ts": m1[0]["open_time"],
                "signal_ts": main[-1]["open_time"],
                "symbol": "BTCUSDT",
                "interval": "15m",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "horizon_exec": 30,
                "exec_interval": "1m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
                "features": {},
                "feature_vec": [0.0] * 12,
                "source": "test",
            }
        ],
    )

    def _always_close(_root, _vec):
        return {"action": "CLOSE", "source": "model", "probs": {"HOLD": 0.1, "CLOSE": 0.9}}

    monkeypatch.setattr(lp, "predict_exit", _always_close)

    def _fake_fetch(symbol, *, interval="15m", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        root,
        symbol="BTCUSDT",
        interval="15m",
        horizon=2,
        window=16,
        market="spot",
        exec_interval="1m",
        tp_pct=0.01,
        sl_pct=0.01,
        explore=False,
        micro_train=False,
        allow_open=False,
        fetch=_fake_fetch,
    )
    assert r["ok"]
    assert r["resolved"] == 1
    trades = __import__("eurika.ml.paper_trader", fromlist=["load_paper_trades"]).load_paper_trades(root)
    assert trades[-1].get("exit_reason") == "model"
    cd = lp.reentry_cooldown_active(
        root,
        symbol="BTCUSDT",
        market="spot",
        side="BUY",
        now_ts_ms=int(m1[-1]["open_time"]),
    )
    assert cd is not None
    assert any("cooldown" in str(e.get("message") or "").lower() for e in r["events"])



def test_should_model_exit_hard_soft_bank() -> None:
    from eurika.ml.exec_tf import should_model_exit

    # Hard CLOSE at 25% of TP=1% → need unreal >= 0.0025
    assert should_model_exit(
        {"action": "CLOSE", "probs": {"HOLD": 0.2, "CLOSE": 0.8}},
        0.003,
        0.01,
    )
    assert not should_model_exit(
        {"action": "CLOSE", "probs": {"HOLD": 0.2, "CLOSE": 0.8}},
        0.001,
        0.01,
    )
    # Soft lean CLOSE even if argmax HOLD
    assert should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.52, "CLOSE": 0.48}},
        0.0025,
        0.01,
    )
    # Bank when CLOSE>HOLD and unreal ≥ 30% TP
    assert should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.40, "CLOSE": 0.60}},
        0.004,
        0.01,
    )
    assert not should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.80, "CLOSE": 0.20}},
        0.003,
        0.01,
    )
    # MFE peak then giveback → bank with milder CLOSE lean
    assert should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.60, "CLOSE": 0.40}},
        0.002,
        0.01,
        mfe_pct=0.006,
    )
    # No bank if MFE not armed or giveback insufficient
    assert not should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.60, "CLOSE": 0.40}},
        0.0055,
        0.01,
        mfe_pct=0.006,
    )
    assert not should_model_exit(
        {"action": "HOLD", "probs": {"HOLD": 0.70, "CLOSE": 0.30}},
        0.002,
        0.01,
        mfe_pct=0.006,
    )
