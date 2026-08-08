"""Tests for paper market ML loop (mocked network; no live orders)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.ml import features as feat
from eurika.ml import market_store as ms
from eurika.ml import paper_trader as pt


def _synthetic_candles(n: int = 80, *, start: float = 100.0, drift: float = 0.01) -> list[dict]:
    rows = []
    px = start
    t0 = 1_700_000_000_000
    for i in range(n):
        o = px
        px = px * (1.0 + drift if i % 3 else 1.0 - drift * 0.5)
        h = max(o, px) * 1.001
        l = min(o, px) * 0.999
        rows.append(
            {
                "open_time": t0 + i * 3_600_000,
                "open": o,
                "high": h,
                "low": l,
                "close": px,
                "volume": 10.0 + i,
                "close_time": t0 + (i + 1) * 3_600_000 - 1,
            }
        )
    return rows


def test_label_buy_sell() -> None:
    buy = pt.label_trade(100.0, 110.0, "BUY", fee=0.001, thr=0.0)
    assert buy["correct"] is True
    sell = pt.label_trade(100.0, 90.0, "SELL", fee=0.001, thr=0.0)
    assert sell["correct"] is True
    bad_buy = pt.label_trade(100.0, 90.0, "BUY", fee=0.001, thr=0.0)
    assert bad_buy["correct"] is False


def test_fee_for_market_and_funding() -> None:
    assert pt.fee_for_market("spot") == pt.DEFAULT_FEE_SPOT
    assert pt.fee_for_market("futures") == pt.DEFAULT_FEE_FUTURES
    assert pt.DEFAULT_FEE_FUTURES < pt.DEFAULT_FEE_SPOT
    assert pt.DEFAULT_FEE_SPOT == pytest.approx(0.002)
    assert pt.DEFAULT_FEE_FUTURES == pytest.approx(0.001)
    spot = pt.commission_breakdown(
        "spot", entry_style="market", exit_reason="model"
    )
    assert spot == {
        "entry_liquidity": "taker",
        "exit_liquidity": "taker",
        "entry_fee": pytest.approx(0.001),
        "exit_fee": pytest.approx(0.001),
        "fee": pytest.approx(0.002),
    }
    fut_maker = pt.commission_breakdown(
        "futures", entry_style="oco", fill_leg="limit", exit_reason="tp"
    )
    assert fut_maker["entry_liquidity"] == "maker"
    assert fut_maker["exit_liquidity"] == "maker"
    assert fut_maker["fee"] == pytest.approx(0.0004)
    fut_model = pt.commission_breakdown(
        "futures", entry_style="oco", fill_leg="limit", exit_reason="model"
    )
    assert fut_model["fee"] == pytest.approx(0.0007)
    fut_stop = pt.commission_breakdown(
        "futures", entry_style="oco", fill_leg="stop", exit_reason="sl"
    )
    assert fut_stop["fee"] == pytest.approx(0.001)
    # Legacy OCO rows lack the filled leg: charge taker rather than assume maker.
    assert pt.entry_liquidity("oco", None) == "taker"
    assert pt.funding_edge_delta(480, "BUY", rate_8h=None) == 0.0
    assert pt.funding_edge_delta(480, "BUY", rate_8h=0.0001) < 0
    assert pt.funding_edge_delta(480, "SELL", rate_8h=0.0001) > 0
    # Settlements in window win over pro-rata
    t0, t1 = 1_700_000_000_000, 1_700_000_000_000 + 9 * 3_600_000
    settled = pt.resolve_funding_edge(
        "BUY",
        entry_ts_ms=t0,
        exit_ts_ms=t1,
        bars_held_1m=540,
        settlements=[
            {"funding_rate": 0.0002, "funding_time": t0 + 8 * 3_600_000},
        ],
        last_funding_rate=0.0001,
    )
    assert settled["source"] == "history"
    assert settled["n_settlements"] == 1
    assert abs(float(settled["funding"]) - (-0.0002)) < 1e-12
    prorata = pt.resolve_funding_edge(
        "SELL",
        entry_ts_ms=t0,
        exit_ts_ms=t0 + 60_000,
        bars_held_1m=1,
        settlements=[],
        last_funding_rate=0.0001,
    )
    assert prorata["source"] == "premium_prorata"
    assert float(prorata["funding"]) > 0


def test_feature_vector_length() -> None:
    candles = _synthetic_candles(50)
    vec = feat.feature_vector(candles, window=feat.DEFAULT_WINDOW)
    assert vec is not None
    assert len(vec) == len(feat.FEATURE_NAMES)
    assert len(feat.FEATURE_NAMES) == 24
    assert "rsi_14" in feat.FEATURE_NAMES
    assert "bb_pos" in feat.FEATURE_NAMES
    assert "macd_hist" in feat.FEATURE_NAMES
    assert "rsi_delta" in feat.FEATURE_NAMES
    assert "dist_to_low_40" in feat.FEATURE_NAMES
    assert "sma_slope" in feat.FEATURE_NAMES
    assert "price_vs_sma_slow" in feat.FEATURE_NAMES


def test_rich_feature_dynamics_finite() -> None:
    candles = _synthetic_candles(60, drift=0.02)
    fd = feat.features_dict(candles, window=feat.DEFAULT_WINDOW)
    assert fd is not None
    for key in (
        "rsi_delta",
        "bb_pos_delta",
        "macd_hist_delta",
        "bb_width",
        "dist_to_low_20",
        "dist_to_high_20",
        "dist_to_low_40",
        "dist_to_high_40",
        "dist_to_low_win",
        "dist_to_high_win",
        "sma_slope",
        "price_vs_sma_slow",
    ):
        assert key in fd
        assert fd[key] == fd[key]  # not NaN
    assert 0.0 <= fd["dist_to_low_40"] <= 1.0
    assert 0.0 <= fd["dist_to_high_40"] <= 1.0
    assert fd["bb_width"] >= 0.0


def test_indicator_features_finite() -> None:
    candles = _synthetic_candles(60, drift=0.02)
    fd = feat.features_dict(candles, window=feat.DEFAULT_WINDOW)
    assert fd is not None
    assert -2.0 <= fd["rsi_14"] <= 2.0
    assert -2.0 <= fd["bb_pos"] <= 2.0
    assert abs(fd["macd_hist"]) < 0.5  # relative to price


def test_breakout_features_and_impulse_horizon() -> None:
    # Flat range then a sharp upside breakout bar.
    t0 = 1_700_000_000_000
    candles: list[dict] = []
    for i in range(45):
        candles.append(
            {
                "open_time": t0 + i * 3_600_000,
                "open": 100.0,
                "high": 100.2,
                "low": 99.8,
                "close": 100.0,
                "volume": 10.0,
                "close_time": t0 + (i + 1) * 3_600_000 - 1,
            }
        )
    candles.append(
        {
            "open_time": t0 + 45 * 3_600_000,
            "open": 100.0,
            "high": 108.0,
            "low": 99.9,
            "close": 107.0,
            "volume": 50.0,
            "close_time": t0 + 46 * 3_600_000 - 1,
        }
    )
    fd = feat.features_dict(candles, window=feat.DEFAULT_WINDOW)
    assert fd is not None
    assert fd["range_break"] > 0.002
    assert fd["atr_burst"] > 0.5
    assert feat.impulse_horizon(2, fd) == 4
    assert feat.impulse_horizon(5, fd) == 5

    calm = feat.features_dict(candles[:-1], window=feat.DEFAULT_WINDOW)
    assert calm is not None
    assert abs(calm["range_break"]) < 1e-9
    assert abs(calm["atr_burst"]) < 0.2
    assert feat.impulse_horizon(2, calm) == 2


def test_rows_to_xy_pads_legacy_feature_vec() -> None:
    from eurika.ml.market_model import _rows_to_xy

    legacy = [0.01, 0.02, 0.03, 0.0, 0.01, 0.02, 0.5]  # 7-dim
    rows = [
        {
            "feature_vec": legacy,
            "action": "BUY",
            "correct": True,
        }
        for _ in range(8)
    ]
    xs, ys, ws = _rows_to_xy(rows)
    assert len(xs) == 8
    assert len(ws) == 8
    assert all(len(x) == len(feat.FEATURE_NAMES) for x in xs)
    assert xs[0][:7] == legacy
    assert xs[0][7:] == [0.0] * (len(feat.FEATURE_NAMES) - 7)
    assert ys[0] == 1
    assert all(w == pytest.approx(1.0) for w in ws)


def test_rows_to_xy_timing_filter() -> None:
    from eurika.ml.market_model import ACTION_TO_IDX, _rows_to_xy

    vec = [0.0] * len(feat.FEATURE_NAMES)
    good = {
        "feature_vec": vec,
        "action": "BUY",
        "correct": True,
        "mfe_pct": 0.005,
        "tp_pct": 0.003,
        "entry_timing_score": 0.002,
    }
    bad_timing = {
        "feature_vec": vec,
        "action": "BUY",
        "correct": True,
        "mfe_pct": 0.0001,
        "tp_pct": 0.003,
        "entry_timing_score": -0.01,
    }
    xs, ys, ws = _rows_to_xy([good, bad_timing])
    assert ys[0] == ACTION_TO_IDX["BUY"]
    assert ys[1] == ACTION_TO_IDX["HOLD"]
    assert len(ws) == 2


def test_sample_weight_from_row_pnl_and_edge() -> None:
    from eurika.ml.market_model import (
        SAMPLE_WEIGHT_MAX,
        sample_weight_from_row,
    )

    assert sample_weight_from_row({}) == pytest.approx(1.0)
    # $2 PnL → 1 + 0.5*2 = 2.0
    assert sample_weight_from_row({"pnl_usdt": 2.0}) == pytest.approx(2.0)
    assert sample_weight_from_row({"pnl_usdt": -2.0}) == pytest.approx(2.0)
    # pnl preferred over edge
    assert sample_weight_from_row({"pnl_usdt": 1.0, "edge": 0.5}) == pytest.approx(1.5)
    # 2% edge → 1 + 50*0.02 = 2.0
    assert sample_weight_from_row({"edge": 0.02}) == pytest.approx(2.0)
    assert sample_weight_from_row({"pnl_usdt": 100.0}) == pytest.approx(SAMPLE_WEIGHT_MAX)


def test_exit_sample_weight_mfe_giveback() -> None:
    from eurika.ml.market_model import (
        SAMPLE_WEIGHT_MAX,
        _exit_rows_to_xy,
        exit_sample_weight_from_row,
    )

    hold = exit_sample_weight_from_row({"exit_label": "HOLD", "mfe_pct": 0.0, "giveback": 0.0})
    assert hold == pytest.approx(1.0)
    close_flat = exit_sample_weight_from_row(
        {"exit_label": "CLOSE", "mfe_pct": 0.0, "giveback": 0.0}
    )
    assert close_flat == pytest.approx(1.0)
    close_fade = exit_sample_weight_from_row(
        {"exit_label": "CLOSE", "mfe_pct": 0.01, "giveback": 0.005}
    )
    assert close_fade > close_flat
    assert close_fade < SAMPLE_WEIGHT_MAX
    hold_after = exit_sample_weight_from_row(
        {"exit_label": "HOLD", "mfe_pct": 0.01, "giveback": 0.004}
    )
    assert hold_after < 1.0
    xs, ys, ws = _exit_rows_to_xy(
        [
            {"feature_vec": [0.0] * 6, "exit_label": "HOLD", "mfe_pct": 0.0, "giveback": 0.0},
            {
                "feature_vec": [0.0] * 6,
                "exit_label": "CLOSE",
                "mfe_pct": 0.01,
                "giveback": 0.005,
            },
        ]
    )
    assert len(ws) == 2
    assert ws[1] > ws[0]


def test_rows_to_xy_weights_by_pnl() -> None:
    from eurika.ml.market_model import _rows_to_xy

    vec = [0.0] * len(feat.FEATURE_NAMES)
    tiny = {"feature_vec": vec, "action": "BUY", "correct": True, "pnl_usdt": 0.1}
    big = {"feature_vec": vec, "action": "SELL", "correct": False, "pnl_usdt": -4.0}
    xs, ys, ws = _rows_to_xy([tiny, big])
    assert ws[0] < ws[1]
    assert ws[1] == pytest.approx(3.0)  # 1 + 0.5*4


def test_predict_levels_heuristic_and_train(tmp_path: Path) -> None:
    from eurika.ml import market_model as mm
    from eurika.ml.paper_trader import paper_trades_path

    pred = mm.predict_levels(tmp_path, {"volatility": 0.004, "atr_burst": 0.2})
    assert pred["source"] == "heuristic"
    assert pred["tp_pct"] > 0
    assert pred["sl_pct"] > 0

    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    vec = [0.01] * len(feat.FEATURE_NAMES)
    with path.open("w", encoding="utf-8") as fh:
        for i in range(10):
            row = {
                "feature_vec": vec,
                "action": "BUY",
                "correct": True,
                "mfe_pct": 0.006 + i * 0.0001,
                "mae_pct": 0.002,
                "entry_timing_score": 0.004,
                "live": True,
            }
            fh.write(__import__("json").dumps(row) + "\n")
    trained = mm.train_market_levels_policy(tmp_path, epochs=20)
    assert trained["ok"], trained.get("error")
    pred2 = mm.predict_levels(tmp_path, vec, fallback_tp=0.02, fallback_sl=0.02, fallback_trail=0.01)
    assert pred2["source"] == "model"
    assert 0 < pred2["tp_pct"] <= 0.02


def test_market_store_merge_and_sync(tmp_path: Path) -> None:
    candles = _synthetic_candles(20)
    ms.save_candles(tmp_path, candles[:10], symbol="BTCUSDT", interval="1h")

    def fake_fetch(symbol, *, interval="1h", limit=500, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": candles[10:], "error": None}

    out = ms.sync_klines(tmp_path, symbol="BTCUSDT", interval="1h", fetch=fake_fetch)
    assert out["ok"] is True
    assert out["total"] == 20
    loaded = ms.load_candles(tmp_path, "BTCUSDT", "1h")
    assert len(loaded) == 20


def test_paper_backfill_writes_labels(tmp_path: Path) -> None:
    candles = _synthetic_candles(80)
    ms.save_candles(tmp_path, candles, symbol="BTCUSDT", interval="1h")
    out = pt.run_paper_backfill(
        tmp_path,
        symbol="BTCUSDT",
        interval="1h",
        window=16,
        horizon=4,
        append=False,
    )
    assert out["ok"] is True
    assert out["written"] > 0
    rows = pt.load_paper_trades(tmp_path)
    assert len(rows) == out["written"]
    assert all(r["action"] in ("BUY", "SELL") for r in rows)
    assert all("correct" in r and "feature_vec" in r for r in rows)


def test_train_market_policy(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    _ = torch
    candles = _synthetic_candles(120)
    ms.save_candles(tmp_path, candles, symbol="BTCUSDT", interval="1h")
    paper = pt.run_paper_backfill(tmp_path, window=16, horizon=4, append=False)
    assert paper["ok"]
    from eurika.ml.market_model import POLICY_ARCH, predict_action, train_market_policy

    trained = train_market_policy(tmp_path, epochs=20)
    assert trained["ok"] is True
    assert trained.get("arch") == POLICY_ARCH
    assert trained.get("sample_weight") == "pnl_usdt|edge"
    assert Path(trained["weights"]).is_file()
    vec = feat.feature_vector(candles, window=16)
    assert vec is not None
    pred = predict_action(tmp_path, vec)
    assert pred["action"] in ("HOLD", "BUY", "SELL")
    assert pred["source"] == "model"


def test_legacy_linear_weights_fall_back_to_momentum(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    import torch as th
    import torch.nn as nn

    from eurika.ml.market_model import predict_action, weights_dir, weights_path

    wdir = weights_dir(tmp_path)
    wdir.mkdir(parents=True, exist_ok=True)
    model = nn.Linear(12, 3)
    th.save({"state_dict": model.state_dict(), "n_features": 12}, weights_path(tmp_path))
    vec = [0.01] * len(feat.FEATURE_NAMES)
    pred = predict_action(tmp_path, vec)
    assert pred["source"] == "momentum"


def test_train_entry_style_policy(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    _ = torch
    from eurika.ml.market_model import (
        append_style_samples,
        predict_entry_style,
        train_entry_style_policy,
    )

    vec = [0.01] * len(feat.FEATURE_NAMES)
    samples = []
    for i, style in enumerate(["market", "limit", "stop", "oco"] * 3):
        samples.append(
            {
                "style_label": style,
                "feature_vec": [v + (i * 0.001) for v in vec],
                "features": {},
            }
        )
    append_style_samples(tmp_path, samples)
    trained = train_entry_style_policy(tmp_path, epochs=30)
    assert trained["ok"], trained.get("error")
    pred = predict_entry_style(tmp_path, vec)
    assert str(pred["source"]).startswith("model")
    assert pred["style"] in ("market", "limit", "stop", "oco")


def test_predict_entry_style_heuristic_bootstrap(tmp_path: Path) -> None:
    from eurika.ml.market_model import predict_entry_style

    pred = predict_entry_style(tmp_path, {"atr_burst": 0.9, "range_break": 0.0})
    assert pred["source"] == "heuristic"
    assert pred["style"] == "stop"


def test_prefer_cancelable_entry_style_margin() -> None:
    from eurika.ml.market_model import prefer_cancelable_entry_style

    # Market clear winner → keep market
    keep = prefer_cancelable_entry_style(
        "market",
        {"market": 0.55, "limit": 0.20, "stop": 0.15, "oco": 0.10},
        margin=0.08,
    )
    assert keep["style"] == "market"
    assert keep["biased"] is False

    # Limit within 0.08 of market → switch to limit
    bias = prefer_cancelable_entry_style(
        "market",
        {"market": 0.34, "limit": 0.30, "stop": 0.20, "oco": 0.16},
        margin=0.08,
    )
    assert bias["style"] == "limit"
    assert bias["biased"] is True

    # Already cancelable → unchanged
    stop = prefer_cancelable_entry_style(
        "stop",
        {"market": 0.40, "limit": 0.10, "stop": 0.35, "oco": 0.15},
    )
    assert stop["style"] == "stop"
    assert stop["biased"] is False



def test_klines_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.integrations import binance_readonly as br

    payload = [
        [1, "1", "2", "0.5", "1.5", "10", 2, "0", 0, "0", "0", "0"],
        [3, "1.5", "2", "1", "1.8", "11", 4, "0", 0, "0", "0", "0"],
    ]

    def fake_get(path, *, params=None, signed=False, timeout=10.0, base_url=None):
        assert path == "/api/v3/klines"
        return payload

    monkeypatch.setattr(br, "_http_get", fake_get)
    out = br.klines("btcusdt", interval="1h", limit=2)
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["candles"][0]["close"] == 1.5


def test_futures_klines_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.integrations import binance_readonly as br

    payload = [[10, "100", "101", "99", "100.5", "5", 11]]

    def fake_get(path, *, params=None, signed=False, timeout=10.0, base_url=None):
        assert path == "/fapi/v1/klines"
        assert base_url == br.futures_base_url()
        return payload

    monkeypatch.setattr(br, "_http_get", fake_get)
    out = br.futures_klines("btcusdt", interval="15m", limit=1)
    assert out["ok"] is True
    assert out["market"] == "futures"
    assert out["candles"][0]["close"] == 100.5


def test_market_store_futures_path_and_legacy_spot(tmp_path: Path) -> None:
    candles = _synthetic_candles(12)
    # Legacy flat path
    legacy = ms.legacy_candles_path(tmp_path, "BTCUSDT", "1h")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        __import__("json").dumps({"symbol": "BTCUSDT", "interval": "1h", "candles": candles[:5]}),
        encoding="utf-8",
    )
    loaded = ms.load_candles(tmp_path, "BTCUSDT", "1h", market="spot")
    assert len(loaded) == 5

    def fake_fetch(symbol, *, interval="1h", limit=500, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": candles[5:], "error": None}

    out = ms.sync_klines(tmp_path, symbol="BTCUSDT", interval="1h", market="futures", fetch=fake_fetch)
    assert out["ok"] is True
    assert out["market"] == "futures"
    fut_path = ms.candles_path(tmp_path, "BTCUSDT", "1h", market="futures")
    assert fut_path.is_file()
    assert "futures" in str(fut_path)
    assert len(ms.load_candles(tmp_path, "BTCUSDT", "1h", market="futures")) == 7
    # Spot still reads legacy until rewritten
    assert len(ms.load_candles(tmp_path, "BTCUSDT", "1h", market="spot")) == 5


def test_parse_markets() -> None:
    assert ms.parse_markets("both") == ("spot", "futures")
    assert ms.parse_markets("futures") == ("futures",)
    assert ms.parse_markets("spot") == ("spot",)

def test_market_status_skips_legacy_when_spot_subdir_exists(tmp_path: Path) -> None:
    candles = _synthetic_candles(8)
    ms.save_candles(tmp_path, candles, symbol="ADAUSDT", interval="15m", market="spot")
    legacy = ms.legacy_candles_path(tmp_path, "ADAUSDT", "15m")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        __import__("json").dumps({"symbol": "ADAUSDT", "interval": "15m", "count": 3, "candles": candles[:3]}),
        encoding="utf-8",
    )
    ms.save_candles(tmp_path, candles, symbol="ONGUSDT", interval="15m", market="futures")
    leg_btc = ms.legacy_candles_path(tmp_path, "BTCUSDT", "1h")
    leg_btc.write_text(
        __import__("json").dumps({"symbol": "BTCUSDT", "interval": "1h", "count": 5, "candles": candles[:5]}),
        encoding="utf-8",
    )
    st = ms.market_status(tmp_path)
    series = st["series"]
    ada = [s for s in series if s.get("symbol") == "ADAUSDT" and s.get("market") == "spot"]
    assert len(ada) == 1
    assert ada[0]["count"] == 8
    assert any(s.get("symbol") == "ONGUSDT" and s.get("market") == "futures" for s in series)
    assert any(s.get("symbol") == "BTCUSDT" and s.get("interval") == "1h" for s in series)


def test_soften_entry_action_breaks_hold_deadlock() -> None:
    from eurika.ml.market_model import entry_setup_ok, soften_entry_action

    pred = {
        "action": "HOLD",
        "source": "model",
        "probs": {"HOLD": 0.52, "BUY": 0.26, "SELL": 0.22},
    }
    out = soften_entry_action(pred)
    assert out["action"] == "BUY"
    assert out["source"] == "model/soft"
    assert out.get("soft_entry") is True

    strong_hold = soften_entry_action(
        {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.70, "BUY": 0.20, "SELL": 0.10}}
    )
    assert strong_hold["action"] == "HOLD"

    assert entry_setup_ok("BUY", {"dist_to_low_40": 0.2, "atr_burst": 0.1}) is True
    assert entry_setup_ok("BUY", {"dist_to_low_40": 0.95, "atr_burst": 0.1}) is False
    assert entry_setup_ok("SELL", {"dist_to_high_40": 0.95, "atr_burst": 0.0}) is False
    # +burst still blocks SELL unless momentum fading (culmination).
    assert (
        entry_setup_ok(
            "SELL",
            {
                "dist_to_high_40": 0.4,
                "atr_burst": 2.5,
                "rsi_delta": 1.0,
                "macd_hist_delta": 0.1,
                "bb_pos_delta": 0.05,
            },
        )
        is False
    )
    assert (
        entry_setup_ok(
            "SELL",
            {
                "dist_to_high_40": 0.4,
                "atr_burst": 2.5,
                "rsi_delta": -1.0,
                "macd_hist_delta": -0.05,
                "bb_pos_delta": -0.03,
            },
        )
        is True
    )
    # −burst BUY allowed on bounce deltas.
    assert (
        entry_setup_ok(
            "BUY",
            {
                "dist_to_low_40": 0.3,
                "atr_burst": -2.5,
                "rsi_delta": 1.0,
                "macd_hist_delta": 0.05,
                "bb_pos_delta": 0.03,
            },
        )
        is True
    )
