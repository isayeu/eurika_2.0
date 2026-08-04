"""Paper portfolio: 1000 USDT bank, risk sizing, leverage rule."""

from __future__ import annotations

from pathlib import Path

from eurika.ml import live_paper as lp
from eurika.ml import paper_portfolio as pp
from eurika.ml.learning_status import format_market_learning_block, market_learning_status


def test_ensure_creates_1000_bank(tmp_path: Path) -> None:
    port = pp.ensure_portfolio(tmp_path)
    assert abs(float(port["equity_usdt"]) - 1000.0) < 1e-9
    assert abs(float(port["start_equity_usdt"]) - 1000.0) < 1e-9
    assert pp.paper_portfolio_path(tmp_path).is_file()
    st = pp.portfolio_status(tmp_path)
    assert abs(float(st["session_pnl_usdt"])) < 1e-9
    assert abs(float(st["max_margin_usdt"]) - 300.0) < 1e-9


def test_propose_size_spot_1pct(tmp_path: Path) -> None:
    port = pp.ensure_portfolio(tmp_path)
    size = pp.propose_size(port, market="spot", features={"volatility": 0.01})
    assert size["ok"] is True
    assert abs(float(size["margin_usdt"]) - 10.0) < 1e-9
    assert abs(float(size["leverage"]) - 1.0) < 1e-9
    assert abs(float(size["notional_usdt"]) - 10.0) < 1e-9


def test_futures_leverage_from_vol() -> None:
    hi = pp.leverage_from_features("futures", {"volatility": 0.001})
    lo = pp.leverage_from_features("futures", {"volatility": 0.02})
    mid = pp.leverage_from_features("futures", {"volatility": 0.008})
    assert abs(hi - 5.0) < 1e-9
    assert abs(lo - 1.0) < 1e-9
    assert 1.0 < mid < 5.0
    assert pp.leverage_from_features("spot", {"volatility": 0.001}) == 1.0


def test_soft_lev_max_from_sl_series() -> None:
    # Helpers remain available but are not applied by default sizing.
    cap, tag = pp.soft_lev_max_from_sl(streak=0, count_in_window=0)
    assert abs(cap - 5.0) < 1e-9
    assert tag == "vol"
    cap, tag = pp.soft_lev_max_from_sl(streak=3, count_in_window=3)
    assert abs(cap - 2.0) < 1e-9
    assert tag.startswith("sl_soft")


def test_soft_futures_lev_cap_and_levels() -> None:
    assert pp.soft_futures_lev_cap(soft_entry=False, market="futures") is None
    assert pp.soft_futures_lev_cap(soft_entry=True, market="spot") is None
    soft_cap = pp.soft_futures_lev_cap(soft_entry=True, market="futures")
    assert soft_cap is not None
    assert abs(soft_cap - 2.0) < 1e-9
    soft_cap_h = pp.soft_futures_lev_cap(soft_entry=True, market="futures", utc_hour=8)
    assert soft_cap_h is not None
    assert abs(soft_cap_h - 1.0) < 1e-9
    # Vol-only path must not push soft to 5×
    soft_vol = pp.leverage_from_features(
        "futures", {"volatility": 0.001}, soft_entry=True
    )
    hard_vol = pp.leverage_from_features(
        "futures", {"volatility": 0.001}, soft_entry=False
    )
    assert abs(soft_vol - 2.0) < 1e-9
    assert abs(hard_vol - 5.0) < 1e-9
    sl, trail, tag = pp.adjust_soft_futures_levels(
        0.01, 0.006, soft_entry=True, market="futures"
    )
    assert abs(sl - 0.0075) < 1e-12
    assert abs(trail - 0.0042) < 1e-12
    assert tag == "soft_fut"
    sl_h, trail_h, tag_h = pp.adjust_soft_futures_levels(
        0.01, 0.006, soft_entry=True, market="futures", utc_hour=8
    )
    assert sl_h < sl and trail_h < trail
    assert tag_h.startswith("soft_fut_h")
    assert pp.utc_hour_from_ms(1_700_000_000_000) is not None


def test_propose_size_soft_futures_caps_lev(tmp_path: Path) -> None:
    port = pp.ensure_portfolio(tmp_path)
    # Missing probs → would be 5× vol-only; soft must cap.
    soft = pp.propose_size(
        port,
        market="futures",
        features={"volatility": 0.001},
        soft_entry=True,
    )
    assert soft["ok"]
    assert float(soft["leverage"]) <= 2.0 + 1e-9
    assert soft.get("lev_tag") == "soft_cap"
    risk_h = pp.propose_size(
        port,
        market="futures",
        features={"volatility": 0.001},
        soft_entry=True,
        utc_hour=8,
    )
    assert abs(float(risk_h["leverage"]) - 1.0) < 1e-9
    assert str(risk_h.get("lev_tag") or "").startswith("soft_h")


def test_propose_size_lev_from_confidence(tmp_path: Path) -> None:
    port = pp.ensure_portfolio(tmp_path)
    weak = pp.propose_size(
        port,
        market="futures",
        features={"volatility": 0.001},
        action="BUY",
        probs={"HOLD": 0.52, "BUY": 0.26, "SELL": 0.22},
    )
    strong = pp.propose_size(
        port,
        market="futures",
        features={"volatility": 0.001},
        action="BUY",
        probs={"HOLD": 0.20, "BUY": 0.65, "SELL": 0.15},
    )
    assert weak["ok"] and strong["ok"]
    assert float(strong["leverage"]) > float(weak["leverage"])
    assert strong.get("lev_tag") == "confidence"
    # SL history must not crush lev when confidence is high
    from eurika.ml.paper_trader import paper_trades_path
    import json

    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"exit_reason": "sl"}) + "\n" for _ in range(3)),
        encoding="utf-8",
    )
    after_sl = pp.propose_size(
        port,
        market="futures",
        features={"volatility": 0.001},
        action="BUY",
        probs={"HOLD": 0.20, "BUY": 0.65, "SELL": 0.15},
        project_root=tmp_path,
    )
    assert abs(float(after_sl["leverage"]) - float(strong["leverage"])) < 1e-9


def test_risk_budget_reject(tmp_path: Path) -> None:
    port = pp.ensure_portfolio(tmp_path)
    port["margin_used_usdt"] = 300.0  # full 30% of 1000
    size = pp.propose_size(port, market="spot")
    assert size["ok"] is False
    assert size["reason"] == "risk_budget"


def test_apply_close_updates_equity(tmp_path: Path) -> None:
    pp.ensure_portfolio(tmp_path)
    # +0.2% edge on notional 100 → +0.2 USDT
    closed = pp.apply_close(
        tmp_path,
        margin_usdt=20.0,
        edge=0.002,
        notional_usdt=100.0,
        opens=[],
    )
    assert abs(float(closed["pnl_usdt"]) - 0.2) < 1e-9
    assert abs(float(closed["equity_usdt"]) - 1000.2) < 1e-9
    assert abs(float(closed["margin_used_usdt"])) < 1e-9


def test_apply_close_clamps_loss_to_margin(tmp_path: Path) -> None:
    pp.ensure_portfolio(tmp_path)
    closed = pp.apply_close(
        tmp_path,
        margin_usdt=10.0,
        edge=-0.5,
        notional_usdt=50.0,
        opens=[],
    )
    # raw pnl = -25, clamp to -10
    assert abs(float(closed["pnl_usdt"]) - (-10.0)) < 1e-9
    assert abs(float(closed["equity_usdt"]) - 990.0) < 1e-9


def test_status_shows_equity(tmp_path: Path) -> None:
    pp.ensure_portfolio(tmp_path)
    pp.apply_close(tmp_path, margin_usdt=0.0, edge=0.01, notional_usdt=10.0, opens=[])
    st = market_learning_status(tmp_path)
    assert abs(float(st["portfolio"]["equity_usdt"]) - 1000.1) < 1e-9
    text = format_market_learning_block(st)
    assert "банк:" in text
    assert "equity=" in text
    assert "PnL USDT" in text


def test_live_reject_when_budget_exhausted(tmp_path: Path, monkeypatch) -> None:
    from eurika.ml import market_store as ms

    batch = []
    px = 100.0
    t0 = 1_700_000_000_000
    for i in range(40):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        batch.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0,
                "close_time": t0 + (i + 1) * 900_000 - 1,
            }
        )
    ms.save_candles(tmp_path, batch[:36], symbol="BTCUSDT", interval="15m", market="spot")
    # Another symbol holds the full margin budget (save syncs portfolio.margin_used).
    lp.save_open_positions(
        tmp_path,
        [
            {
                "symbol": "ETHUSDT",
                "market": "spot",
                "action": "BUY",
                "entry": 1.0,
                "horizon": 10,
                "bars_held": 0,
                "source": "model",
                "margin_usdt": 300.0,
                "notional_usdt": 300.0,
                "leverage": 1.0,
            }
        ],
    )

    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"BUY": 0.7, "SELL": 0.1, "HOLD": 0.2},
        },
    )
    monkeypatch.setattr("eurika.ml.live_paper.entry_setup_ok", lambda *a, **k: True)
    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        market="spot",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    opens = lp.load_open_positions(tmp_path)
    assert not any(str(p.get("symbol")) == "BTCUSDT" for p in opens)
    hold_msgs = [e["message"] for e in r["events"] if e.get("kind") == "hold"]
    assert any("бюджета риска" in m for m in hold_msgs)
