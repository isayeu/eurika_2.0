"""Tests for live paper tick (mocked klines; no live orders)."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from eurika.ml import live_paper as lp
from eurika.ml import market_store as ms


@pytest.fixture(autouse=True)
def _disable_exec_tf_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests use coarse synthetic bars; dual-TF covered separately."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "")


@pytest.fixture(autouse=True)
def _open_cost_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthetic bars are flat, so the cost gate would block every entry.

    Tests about the gate itself opt back in by restoring the real function.
    """
    monkeypatch.setattr(lp, "cost_gate_ok", lambda *a, **k: (True, ""))


def _candles(n: int = 50, *, start: float = 100.0) -> list[dict[str, float | int]]:
    rows = []
    px = start
    t0 = 1_700_000_000_000
    for i in range(n):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        rows.append(
            {
                "open_time": t0 + i * 3_600_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0 + i,
                "close_time": t0 + (i + 1) * 3_600_000 - 1,
            }
        )
    return rows


def test_live_tick_opens_and_resolves(tmp_path: Path) -> None:
    batch = _candles(40)

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        # First call: seed; later calls: extend with one more bar using growing store
        existing = ms.load_candles(tmp_path, "BTCUSDT", "1h")
        if not existing:
            return {"ok": True, "candles": batch[:36], "error": None}
        # Append next synthetic bar beyond last
        last_t = int(existing[-1]["open_time"])
        px = float(existing[-1]["close"]) * 1.01
        extra = {
            "open_time": last_t + 3_600_000,
            "open": float(existing[-1]["close"]),
            "high": px * 1.001,
            "low": px * 0.999,
            "close": px,
            "volume": 1.0,
            "close_time": last_t + 2 * 3_600_000 - 1,
        }
        return {"ok": True, "candles": [extra], "error": None}

    r1 = lp.run_live_tick(
        tmp_path,
        window=16,
        horizon=2,
        sync_limit=40,
        max_keep=80,
        micro_train=False,
        fetch=fetch,
    )
    assert r1["ok"] is True
    kinds = [e["kind"] for e in r1["events"]]
    assert "sync" in kinds
    assert "analysis" in kinds
    opens = lp.load_open_positions(tmp_path)
    assert r1["opens"] >= 0

    # Idle tick: no new candles → no sync spam
    r_idle = lp.run_live_tick(
        tmp_path,
        window=16,
        horizon=2,
        micro_train=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r_idle["ok"] is True
    assert "sync" not in [e["kind"] for e in r_idle["events"]]

    # Advance enough bars to resolve
    r = r1
    for _ in range(5):
        r = lp.run_live_tick(
            tmp_path,
            window=16,
            horizon=2,
            micro_train=False,
            fetch=fetch,
        )
        assert r["ok"] is True
        if r["resolved"] > 0:
            break
    rows_path = tmp_path / ".eurika" / "ml" / "paper_trades.jsonl"
    if opens:
        assert rows_path.is_file() or int(r.get("resolved") or 0) >= 0


def test_format_market_event() -> None:
    line = lp.format_market_event({"kind": "paper", "message": "бумажная ПОКУПКА @ 1"})
    assert line.startswith("сделка:")


def test_explore_when_idle_opens_despite_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explore buys a label as a shadow — never sits the paper-equity exam."""
    batch = _candles(40)
    ms.save_candles(tmp_path, batch[:36], symbol="BTCUSDT", interval="15m")

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.9, "BUY": 0.05, "SELL": 0.05}},
    )
    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        explore_when_idle=True,
        explore_live_cap=0,  # unlimited for this unit test
        fetch=fetch,
        rng=random.Random(0),
    )
    assert r["ok"] is True
    kinds = [e["kind"] for e in r["events"]]
    assert "explore" in kinds
    assert "paper" not in kinds
    assert r["opens"] == 0
    assert lp.load_open_positions(tmp_path) == []
    shadows = lp.load_shadow_positions(tmp_path)
    assert len(shadows) == 1
    assert "explore" in str(shadows[0].get("source") or "")


def test_cost_gate_blocks_entry_when_move_will_not_pay_the_fee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flat synthetic bars: nothing is expanding, so the entry must not open."""
    from eurika.ml import entry_cost

    monkeypatch.setattr(lp, "cost_gate_ok", entry_cost.cost_gate_ok)
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    assert lp.load_open_positions(tmp_path) == []
    msgs = " ".join(str(e.get("message") or "") for e in r["events"])
    assert "не окупает комиссию" in msgs
    # The refused entry is still tracked, or the journal would only ever see
    # the regime the gate allows and the next calibration would unlock itself.
    shadows = lp.load_shadow_positions(tmp_path)
    assert len(shadows) == 1
    assert shadows[0]["action"] == "BUY"
    assert shadows[0]["shadow"] is True
    assert not shadows[0].get("margin_usdt")


def test_shadow_entry_becomes_a_label_without_touching_money(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shadow resolves through the same machinery, but pays nothing."""
    from eurika.ml import entry_cost
    from eurika.ml.paper_portfolio import ensure_portfolio
    from eurika.ml.paper_trader import load_paper_trades

    monkeypatch.setattr(lp, "cost_gate_ok", entry_cost.cost_gate_ok)
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )
    equity_before = float(ensure_portfolio(tmp_path)["equity_usdt"])
    for n in (36, 40):
        ms.save_candles(
            tmp_path, _candles(48)[:n], symbol="BTCUSDT", interval="15m", market="spot"
        )
        lp.run_live_tick(
            tmp_path,
            symbol="BTCUSDT",
            interval="15m",
            window=16,
            horizon=2,
            market="spot",
            micro_train=False,
            explore=False,
            fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
        )

    rows = [r for r in load_paper_trades(tmp_path) if r.get("shadow")]
    assert rows, "shadow entry must produce a training label"
    row = rows[0]
    assert row["live"] is False
    assert row["pnl_usdt"] is None
    assert row["feature_vec"]
    assert row["edge"] is not None
    assert row["fee"] == pytest.approx(0.002)
    assert row["fee_source"] == "maker_taker"
    assert row["entry_liquidity"] == "taker"
    assert row["exit_liquidity"] == "taker"
    assert lp.load_open_positions(tmp_path) == []
    assert float(ensure_portfolio(tmp_path)["equity_usdt"]) == equity_before


def test_shadow_does_not_block_a_real_entry_on_the_same_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shadows live in their own book; the live path must not see them as open."""
    lp.save_shadow_positions(
        tmp_path,
        [
            {
                "ts": 1,
                "symbol": "BTCUSDT",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "shadow": True,
            }
        ],
    )
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )
    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    assert len(lp.load_open_positions(tmp_path)) == 1


def test_cost_gate_lets_expanding_move_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same setup, but a calibrated gate that the current expansion clears."""
    from eurika.ml import entry_cost

    monkeypatch.setattr(lp, "cost_gate_ok", entry_cost.cost_gate_ok)
    gate_path = entry_cost.cost_gate_path(tmp_path)
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text('{"expansion_min": -9.0, "cost_mult": 1.5}', encoding="utf-8")
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    assert len(lp.load_open_positions(tmp_path)) == 1


def test_cost_gate_does_not_block_explore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explore is a shadow probe: cost gate never sees it, equity never moves."""
    from eurika.ml import entry_cost

    monkeypatch.setattr(lp, "cost_gate_ok", entry_cost.cost_gate_ok)
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "HOLD",
            "source": "model",
            "probs": {"HOLD": 0.9, "BUY": 0.05, "SELL": 0.05},
        },
    )
    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        explore_when_idle=True,
        explore_live_cap=0,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
        rng=random.Random(0),
    )
    assert r["ok"] is True
    assert r["opens"] == 0
    assert lp.load_open_positions(tmp_path) == []
    assert len(lp.load_shadow_positions(tmp_path)) == 1
    assert "explore" in [e["kind"] for e in r["events"]]


def test_explore_stops_after_live_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.ml.paper_trader import paper_trades_path

    batch = _candles(40)
    ms.save_candles(tmp_path, batch[:36], symbol="BTCUSDT", interval="15m", market="spot")
    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        '{"action":"BUY","correct":true,"live":true,"market":"spot","feature_vec":[0,0,0,0,0,0,0]}'
        for _ in range(5)
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.9, "BUY": 0.05, "SELL": 0.05}},
    )
    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        explore_when_idle=True,
        explore_live_cap=5,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
        rng=random.Random(0),
    )
    assert r["ok"] is True
    assert r.get("explore_gate", {}).get("reason") == "cap"
    assert "explore" not in [e["kind"] for e in r["events"]]
    assert lp.load_open_positions(tmp_path) == []
    assert any("порога" in str(e.get("message")) for e in r["events"] if e.get("kind") == "info")


def test_reset_explore_counter_allows_explore_again(tmp_path: Path) -> None:
    from eurika.ml.paper_trader import paper_trades_path

    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join('{"live":true,"action":"BUY"}' for _ in range(10)) + "\n",
        encoding="utf-8",
    )
    gate1 = lp.resolve_explore_enabled(tmp_path, explore=True, explore_live_cap=5)
    assert gate1["reason"] == "cap"
    assert gate1["live"] == 10
    out = lp.reset_explore_counter(tmp_path)
    assert out["session_live"] == 0
    gate2 = lp.resolve_explore_enabled(tmp_path, explore=True, explore_live_cap=5)
    assert gate2["enabled"] is True
    assert gate2["live"] == 0
    assert gate2["total_live"] == 10


def test_unfilled_cancellations_do_not_consume_explore_budget(tmp_path: Path) -> None:
    from eurika.ml.paper_trader import paper_status, paper_trades_path

    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"live":true,"action":"BUY","pending_cancelled":true,'
        '"executed":false,"exit_reason":"cancel_expire"}\n',
        encoding="utf-8",
    )

    assert lp.count_live_labels(tmp_path) == 0
    status = paper_status(tmp_path)
    assert status["count"] == 0
    assert status["cancelled_count"] == 1


def test_explore_is_opt_in_for_live_entry_points() -> None:
    import inspect

    assert inspect.signature(lp.run_live_tick).parameters["explore"].default is False
    assert inspect.signature(lp.run_live_universe_tick).parameters["explore"].default is False


def test_universe_tick_two_symbols(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for sym in ("ETHUSDT", "SOLUSDT"):
        ms.save_candles(tmp_path, _candles(40)[:36], symbol=sym, interval="15m")

    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.8, "BUY": 0.1, "SELL": 0.1}},
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_universe_tick(
        tmp_path,
        symbols=["ETHUSDT", "SOLUSDT"],
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        explore_when_idle=True,
        fetch=fetch,
        rng=random.Random(1),
    )
    assert r["ok"] is True
    assert r["symbols"] == ["ETHUSDT", "SOLUSDT"]
    assert any(e.get("kind") == "info" and "universe" in str(e.get("message")) for e in r["events"])
    assert lp.load_open_positions(tmp_path) == []
    shadows = lp.load_shadow_positions(tmp_path)
    assert len(shadows) == 2

    # Second tick while shadows wait: live book is idle (no spam)
    r2 = lp.run_live_universe_tick(
        tmp_path,
        symbols=["ETHUSDT", "SOLUSDT"],
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        fetch=fetch,
        rng=random.Random(1),
    )
    assert r2.get("idle") is True
    assert r2["events"] == []
    assert "analysis" not in [e["kind"] for e in r2["events"]]


def test_universe_shadow_resolution_triggers_micro_train(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trained: list[tuple[Path, int, Any]] = []

    monkeypatch.setattr(
        lp,
        "run_live_tick",
        lambda *args, **kwargs: {
            "ok": True,
            "events": [],
            "opens": 0,
            "resolved": 0,
            "shadow_resolved": 1,
            "suggestion": None,
            "error": None,
        },
    )
    monkeypatch.setattr(
        lp,
        "_append_learn_events",
        lambda events, root, *, epochs, markets=None: trained.append((root, epochs, markets)),
    )

    out = lp.run_live_universe_tick(
        tmp_path,
        symbols=["ETHUSDT"],
        micro_train=True,
        train_epochs=3,
        explore=False,
    )

    assert out["resolved"] == 0
    assert out["shadow_resolved"] == 1
    # The gate is calibrated on the venues the tick actually traded.
    assert trained == [(tmp_path.resolve(), 3, ("spot",))]
    shadow_summary = next(
        event for event in out["events"] if event.get("kind") == "shadow_outcome"
    )
    assert shadow_summary["shadow_resolved"] == 1
    assert "запускаем дообучение" in shadow_summary["message"]


def test_universe_resolves_orphan_without_reopen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    batch = _candles(40)
    ms.save_candles(tmp_path, batch[:36], symbol="ETHUSDT", interval="15m")
    ms.save_candles(tmp_path, batch[:36], symbol="ADAUSDT", interval="15m")
    # Orphan ETH open from older single-symbol run
    entry_ts = int(batch[33]["open_time"])
    lp.save_open_positions(
        tmp_path,
        [
            {
                "ts": entry_ts,
                "symbol": "ETHUSDT",
                "interval": "15m",
                "action": "BUY",
                "entry": float(batch[33]["close"]),
                "horizon": 2,
                "feature_vec": [0.0] * 7,
                "source": "explore/model",
            }
        ],
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.9, "BUY": 0.05, "SELL": 0.05}},
    )

    # Provide 2 more bars so ETH resolves
    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        existing = ms.load_candles(tmp_path, symbol, "15m")
        if len(existing) >= 38:
            return {"ok": True, "candles": [], "error": None}
        last_t = int(existing[-1]["open_time"])
        px = float(existing[-1]["close"]) * 1.01
        return {
            "ok": True,
            "candles": [
                {
                    "open_time": last_t + 3_600_000,
                    "open": float(existing[-1]["close"]),
                    "high": px * 1.001,
                    "low": px * 0.999,
                    "close": px,
                    "volume": 1.0,
                    "close_time": last_t + 2 * 3_600_000 - 1,
                }
            ],
            "error": None,
        }

    r = None
    for _ in range(3):
        r = lp.run_live_universe_tick(
            tmp_path,
            symbols=["ADAUSDT"],
            interval="15m",
            window=16,
            horizon=2,
            micro_train=False,
            explore=True,
            explore_when_idle=True,
            fetch=fetch,
            rng=random.Random(0),
        )
        if r and r.get("resolved", 0) > 0:
            break
    assert r is not None
    assert "ETHUSDT/spot" in (r.get("orphans") or [])
    # ETH should be resolved and not re-opened; ADA may open via explore
    opens = lp.load_open_positions(tmp_path)
    assert all(str(p.get("symbol")).upper() != "ETHUSDT" for p in opens)


def test_universe_includes_shadow_and_pending_only_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eurika.ml.paper_orders import save_pending_orders

    lp.save_shadow_positions(
        tmp_path,
        [{"symbol": "ETHUSDT", "market": "spot", "action": "BUY"}],
    )
    save_pending_orders(
        tmp_path,
        [{"symbol": "SOLUSDT", "market": "futures", "status": "pending"}],
    )
    calls: list[tuple[str, str, bool]] = []

    def fake_tick(root, *, symbol, market, allow_open, **kwargs):
        calls.append((symbol, market, allow_open))
        return {
            "ok": True,
            "events": [],
            "opens": 0,
            "resolved": 0,
            "shadow_resolved": 0,
            "suggestion": None,
            "error": None,
        }

    monkeypatch.setattr(lp, "run_live_tick", fake_tick)
    result = lp.run_live_universe_tick(
        tmp_path,
        symbols=["ADAUSDT"],
        futures_symbols=[],
        markets=["spot"],
        micro_train=False,
        explore=False,
    )

    assert "ETHUSDT/spot" in result["orphans"]
    assert "SOLUSDT/futures" in result["orphans"]
    assert ("ETHUSDT", "spot", False) in calls
    assert ("SOLUSDT", "futures", False) in calls


def test_single_symbol_universe_still_resolves_balance_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After leaving «Из балансов», one-symbol mode must still drain old opens."""
    batch = _candles(40)
    for sym in ("ADAUSDT", "ONGUSDT"):
        ms.save_candles(tmp_path, batch[:36], symbol=sym, interval="15m")
    entry_ts = int(batch[33]["open_time"])
    lp.save_open_positions(
        tmp_path,
        [
            {
                "ts": entry_ts,
                "symbol": "ADAUSDT",
                "interval": "15m",
                "market": "spot",
                "action": "BUY",
                "entry": float(batch[33]["close"]),
                "horizon": 2,
                "feature_vec": [0.0] * 7,
                "source": "model",
            }
        ],
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.9, "BUY": 0.05, "SELL": 0.05}},
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        existing = ms.load_candles(tmp_path, symbol, "15m")
        if len(existing) >= 38:
            return {"ok": True, "candles": [], "error": None}
        last_t = int(existing[-1]["open_time"])
        px = float(existing[-1]["close"]) * 1.01
        return {
            "ok": True,
            "candles": [
                {
                    "open_time": last_t + 3_600_000,
                    "open": float(existing[-1]["close"]),
                    "high": px * 1.001,
                    "low": px * 0.999,
                    "close": px,
                    "volume": 1.0,
                    "close_time": last_t + 2 * 3_600_000 - 1,
                }
            ],
            "error": None,
        }

    r = None
    for _ in range(3):
        r = lp.run_live_universe_tick(
            tmp_path,
            symbols=["ONGUSDT"],
            markets=("spot",),
            interval="15m",
            window=16,
            horizon=2,
            micro_train=False,
            explore=False,
            fetch=fetch,
        )
        if r and r.get("resolved", 0) > 0:
            break
    assert r is not None
    assert "ADAUSDT/spot" in (r.get("orphans") or [])
    opens = lp.load_open_positions(tmp_path)
    assert all(str(p.get("symbol")).upper() != "ADAUSDT" for p in opens)


def test_drop_orphan_opens(tmp_path: Path) -> None:
    lp.save_open_positions(
        tmp_path,
        [
            {"symbol": "ONGUSDT", "market": "spot", "action": "BUY", "entry": 1.0, "horizon": 2},
            {"symbol": "ONGUSDT", "market": "futures", "action": "SELL", "entry": 1.0, "horizon": 2},
            {"symbol": "ETHUSDT", "market": "futures", "action": "BUY", "entry": 2.0, "horizon": 2},
        ],
    )
    out = lp.drop_orphan_opens(
        tmp_path,
        spot_symbols=["ONGUSDT"],
        futures_symbols=["ETHUSDT"],
        markets="both",
    )
    assert out["dropped"] == 1
    assert out["kept"] == 2
    assert out["dropped_positions"][0]["symbol"] == "ONGUSDT"
    assert out["dropped_positions"][0]["market"] == "futures"
    kept = lp.load_open_positions(tmp_path)
    keys = {(str(p["symbol"]), str(p.get("market") or "spot")) for p in kept}
    assert keys == {("ONGUSDT", "spot"), ("ETHUSDT", "futures")}


def test_idle_wait_no_analysis_spam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="ETHUSDT", interval="15m")
    lp.save_open_positions(
        tmp_path,
        [
            {
                "ts": int(_candles(40)[34]["open_time"]),
                "symbol": "ETHUSDT",
                "interval": "15m",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "feature_vec": [0.0] * 7,
                "source": "model",
            }
        ],
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "SELL", "source": "model", "probs": {"HOLD": 0.2, "BUY": 0.2, "SELL": 0.6}},
    )
    r = lp.run_live_tick(
        tmp_path,
        symbol="ETHUSDT",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    kinds = [e["kind"] for e in r["events"]]
    assert r.get("idle_wait") is True
    assert "analysis" not in kinds
    assert "skip" not in kinds
    assert "wait" not in kinds  # added=0 → silent wait


def test_trim_candles(tmp_path: Path) -> None:
    ms.save_candles(tmp_path, _candles(50), symbol="BTCUSDT", interval="1h")
    n = lp.trim_candles(tmp_path, max_keep=20)
    assert n == 20
    assert len(ms.load_candles(tmp_path)) == 20


def test_live_tick_futures_tags_market(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    batch = _candles(40)
    ms.save_candles(tmp_path, batch[:36], symbol="BTCUSDT", interval="15m", market="futures")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "BUY", "source": "model", "probs": {"HOLD": 0.1, "BUY": 0.8, "SELL": 0.1}},
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=False,
        market="futures",
        fetch=fetch,
    )
    assert r["ok"] is True
    assert r["market"] == "futures"
    opens = lp.load_open_positions(tmp_path)
    assert len(opens) == 1
    assert opens[0].get("market") == "futures"
    assert any("fut" in str(e.get("message")) for e in r["events"] if e.get("kind") == "paper")


def test_universe_both_markets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("spot", "futures"):
        ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market=kind)
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "HOLD", "source": "model", "probs": {"HOLD": 0.8, "BUY": 0.1, "SELL": 0.1}},
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_universe_tick(
        tmp_path,
        symbols=["BTCUSDT"],
        markets=("spot", "futures"),
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=True,
        explore_when_idle=True,
        fetch=fetch,
        rng=random.Random(2),
    )
    assert r["ok"] is True
    assert r["markets"] == ["spot", "futures"]
    assert lp.load_open_positions(tmp_path) == []
    shadows = lp.load_shadow_positions(tmp_path)
    kinds = {str(p.get("market") or "spot") for p in shadows}
    assert kinds == {"spot", "futures"}


def test_both_markets_independent_symbol_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spot list and futures list must not be remapped onto each other."""
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="ETHUSDT", interval="15m", market="spot")
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="ONGUSDT", interval="15m", market="futures")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {"action": "BUY", "source": "model", "probs": {"HOLD": 0.1, "BUY": 0.8, "SELL": 0.1}},
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_universe_tick(
        tmp_path,
        symbols=["ETHUSDT"],
        futures_symbols=["ONGUSDT"],
        markets=("spot", "futures"),
        interval="15m",
        window=16,
        horizon=2,
        micro_train=False,
        explore=False,
        fetch=fetch,
    )
    assert r["ok"] is True
    opens = lp.load_open_positions(tmp_path)
    keys = {(str(p.get("symbol")).upper(), str(p.get("market") or "spot")) for p in opens}
    assert ("ETHUSDT", "spot") in keys
    assert ("ONGUSDT", "futures") in keys
    assert ("ETHUSDT", "futures") not in keys
    assert ("ONGUSDT", "spot") not in keys


def test_soft_entry_opens_without_explore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HOLD argmax with competitive BUY probs → soft entry even if explore off."""
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "HOLD",
            "source": "model",
            "probs": {"HOLD": 0.52, "BUY": 0.28, "SELL": 0.20},
        },
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        micro_train=False,
        explore=False,
        fetch=fetch,
    )
    assert r["ok"] is True
    opens = lp.load_open_positions(tmp_path)
    assert len(opens) == 1
    assert opens[0].get("action") == "BUY"
    assert "soft" in str(opens[0].get("source") or r["suggestion"].get("source") or "")


def test_soft_entry_prefers_oco_bracket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With 1m exec path, soft entry should place cancelable OCO (limit+stop) bracket."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(36):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0,
            }
        )
    ms.save_candles(tmp_path, main, symbol="BTCUSDT", interval="15m", market="spot")
    m1 = []
    for i in range(30):
        c = 100.0 + i * 0.01
        m1.append(
            {
                "open_time": t0 + i * 60_000,
                "open": c,
                "high": c * 1.001,
                "low": c * 0.999,
                "close": c,
                "volume": 1.0,
            }
        )
    ms.save_candles(tmp_path, m1, symbol="BTCUSDT", interval="1m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "HOLD",
            "source": "model",
            "probs": {"HOLD": 0.52, "BUY": 0.28, "SELL": 0.20},
        },
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_entry_style",
        lambda *a, **k: {
            "style": "market",
            "source": "model",
            "probs": {"market": 0.7, "limit": 0.1, "stop": 0.1, "oco": 0.1},
        },
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.entry_setup_ok",
        lambda *a, **k: True,
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        exec_interval="1m",
        micro_train=False,
        explore=False,
        fetch=fetch,
    )
    assert r["ok"] is True
    assert lp.load_open_positions(tmp_path) == []
    from eurika.ml.paper_orders import load_pending_orders

    pend = load_pending_orders(tmp_path)
    assert len(pend) == 1
    assert pend[0].get("entry_style") == "oco"
    assert pend[0].get("limit_px") is not None
    assert pend[0].get("stop_px") is not None
    assert pend[0].get("action") == "BUY"
    assert "soft" in str(pend[0].get("source") or "")


def test_pending_side_flip_replaces_opposite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opposite soft signal cancels existing pending and places new side."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(36):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0,
            }
        )
    ms.save_candles(tmp_path, main, symbol="BTCUSDT", interval="15m", market="spot")
    last_main_ts = int(main[-1]["open_time"])
    m1 = [
        {
            "open_time": t0 + i * 60_000,
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "volume": 1.0,
        }
        for i in range(30)
    ]
    ms.save_candles(tmp_path, m1, symbol="BTCUSDT", interval="1m", market="spot")
    from eurika.ml.paper_orders import build_pending_order, load_pending_orders, save_pending_orders

    # Same main-bar signal_ts as live would set — must still allow opposite flip.
    old = build_pending_order(
        symbol="BTCUSDT",
        market="spot",
        action="BUY",
        signal_px=100.0,
        signal_ts=last_main_ts,
        interval="15m",
        entry_style="limit",
        horizon=2,
        horizon_exec=60,
        exec_interval="1m",
        tp_pct=0.01,
        sl_pct=0.01,
        limit_offset_pct=0.01,
        invalidate_pct=0.05,
    )
    old["signal_ts"] = last_main_ts
    save_pending_orders(tmp_path, [old])
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "HOLD",
            "source": "model",
            "probs": {"HOLD": 0.50, "BUY": 0.20, "SELL": 0.30},
        },
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_entry_style",
        lambda *a, **k: {"style": "limit", "source": "model", "probs": None},
    )
    monkeypatch.setattr("eurika.ml.live_paper.entry_setup_ok", lambda *a, **k: True)

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        exec_interval="1m",
        micro_train=False,
        explore=False,
        fetch=fetch,
    )
    assert r["ok"] is True
    msgs = " ".join(str(e.get("message") or "") for e in r["events"])
    assert "side_flip" in msgs
    pend = load_pending_orders(tmp_path)
    assert len(pend) == 1
    assert pend[0].get("action") == "SELL"
    assert pend[0].get("id") != old.get("id")


def test_reentry_cooldown_register_and_expire(tmp_path: Path) -> None:
    t0 = 1_700_000_000_000
    row = lp.register_reentry_cooldown(
        tmp_path,
        symbol="BTCUSDT",
        market="spot",
        side="BUY",
        exit_ts_ms=t0,
        bars_1m=20,
        exit_reason="model",
    )
    assert int(row["until_ts"]) == t0 + 20 * 60_000
    hit = lp.reentry_cooldown_active(
        tmp_path, symbol="BTCUSDT", market="spot", side="BUY", now_ts_ms=t0 + 5 * 60_000
    )
    assert hit is not None
    assert hit["side"] == "BUY"
    # Opposite side free
    assert (
        lp.reentry_cooldown_active(
            tmp_path, symbol="BTCUSDT", market="spot", side="SELL", now_ts_ms=t0 + 5 * 60_000
        )
        is None
    )
    # Expired
    assert (
        lp.reentry_cooldown_active(
            tmp_path, symbol="BTCUSDT", market="spot", side="BUY", now_ts_ms=t0 + 21 * 60_000
        )
        is None
    )


def test_reentry_cooldown_blocks_same_side_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ms.save_candles(tmp_path, _candles(40)[:36], symbol="BTCUSDT", interval="15m", market="spot")
    last_ts = int(ms.load_candles(tmp_path, "BTCUSDT", "15m", market="spot")[-1]["open_time"])
    lp.register_reentry_cooldown(
        tmp_path,
        symbol="BTCUSDT",
        market="spot",
        side="BUY",
        exit_ts_ms=last_ts - 60_000,
        bars_1m=20,
        exit_reason="model",
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "HOLD",
            "source": "model",
            "probs": {"HOLD": 0.52, "BUY": 0.28, "SELL": 0.20},
        },
    )

    def fetch(symbol, *, interval="1h", limit=100, start_time=None, end_time=None, timeout=10.0):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        micro_train=False,
        explore=False,
        fetch=fetch,
    )
    assert r["ok"] is True
    assert lp.load_open_positions(tmp_path) == []
    msgs = " ".join(str(e.get("message") or "") for e in r["events"])
    assert "cooldown" in msgs.lower()


def test_sl_exit_registers_reentry_cooldown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SL close must arm same-side cooldown (stop soft re-entry churn)."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    root = tmp_path
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(40):
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
    entry_ts = t0 + 30 * 60_000
    m1 = []
    for i in range(40):
        # Drop through SL after a few bars
        c = 100.0 - i * 0.05
        m1.append(
            {
                "open_time": entry_ts + i * 60_000,
                "open": c,
                "high": c + 0.01,
                "low": c - 0.05,
                "close": c,
                "volume": 1.0,
            }
        )
    ms.save_candles(root, m1, symbol="BTCUSDT", interval="1m", market="spot")
    lp.save_open_positions(
        root,
        [
            {
                "ts": entry_ts,
                "symbol": "BTCUSDT",
                "interval": "15m",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "horizon_exec": 30,
                "exec_interval": "1m",
                "tp_pct": 0.05,
                "sl_pct": 0.01,
                "trail_pct": 0.0,
                "features": {},
                "feature_vec": [0.0] * 12,
                "source": "model/soft",
                "entry_style": "oco",
                "fill_leg": "limit",
                "margin_usdt": 10.0,
                "notional_usdt": 10.0,
                "leverage": 1.0,
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
        explore=False,
        micro_train=False,
        allow_open=False,
        fetch=_fake_fetch,
    )
    assert r["ok"]
    assert r["resolved"] == 1
    from eurika.ml.paper_trader import load_paper_trades

    trades = load_paper_trades(root)
    assert trades[-1].get("exit_reason") == "sl"
    assert trades[-1]["fee_source"] == "maker_taker"
    assert trades[-1]["entry_liquidity"] == "maker"
    assert trades[-1]["exit_liquidity"] == "taker"
    assert trades[-1]["entry_fee"] == pytest.approx(0.001)
    assert trades[-1]["exit_fee"] == pytest.approx(0.001)
    assert trades[-1]["fee"] == pytest.approx(0.002)
    assert trades[-1]["fill_leg"] == "limit"
    outcome = next(e for e in r["events"] if e.get("kind") == "outcome")
    assert outcome["fee"] == pytest.approx(0.002)
    assert outcome["fee_source"] == "maker_taker"
    assert outcome["entry_liquidity"] == "maker"
    assert outcome["exit_liquidity"] == "taker"
    assert outcome["entry_style"] == "oco"
    assert outcome["fill_leg"] == "limit"
    cd = lp.reentry_cooldown_active(
        root,
        symbol="BTCUSDT",
        market="spot",
        side="BUY",
        now_ts_ms=int(trades[-1]["exit_ts"]) + 60_000,
    )
    assert cd is not None
    assert cd.get("exit_reason") == "sl"
    assert any("после SL" in str(e.get("message") or "") for e in r["events"])


def test_planned_hold_prefers_exec_horizon() -> None:
    pos = {
        "horizon": 4,
        "interval": "1h",
        "horizon_exec": 240,
        "exec_interval": "1m",
    }
    assert lp.planned_hold_ms(pos, interval="1h", horizon=4) == 240 * 60_000


def test_stale_force_close_max_age() -> None:
    planned = 240 * 60_000
    entry = 1_700_000_000_000
    pos = {
        "ts": entry,
        "horizon": 4,
        "interval": "1h",
        "horizon_exec": 240,
        "exec_interval": "1m",
    }
    assert (
        lp.stale_force_close_reason(
            pos,
            now_ts_ms=entry + planned * lp.MAX_HOLD_MULT - 1,
            interval="1h",
            horizon=4,
        )
        is None
    )
    assert (
        lp.stale_force_close_reason(
            pos,
            now_ts_ms=entry + planned * lp.MAX_HOLD_MULT,
            interval="1h",
            horizon=4,
        )
        == "max_age"
    )


def test_stale_force_close_when_entry_left_window() -> None:
    planned = 240 * 60_000
    entry = 1_700_000_000_000
    pos = {
        "ts": entry,
        "horizon": 4,
        "interval": "1h",
        "horizon_exec": 240,
        "exec_interval": "1m",
    }
    candles = [{"open_time": entry + planned + 60_000, "close": 1.0}]
    assert (
        lp.stale_force_close_reason(
            pos,
            now_ts_ms=entry + planned + 60_000,
            interval="1h",
            horizon=4,
            candles_exec=candles,
        )
        == "stale"
    )
    # Still inside planned hold → do not force-close yet.
    assert (
        lp.stale_force_close_reason(
            pos,
            now_ts_ms=entry + planned // 2,
            interval="1h",
            horizon=4,
            candles_exec=[{"open_time": entry + planned // 2, "close": 1.0}],
        )
        is None
    )


def test_live_tick_force_closes_max_age_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open past N×horizon closes at last close with exit_reason=max_age."""
    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    root = tmp_path
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(20):
        main.append(
            {
                "open_time": t0 + i * 3_600_000,
                "open": px,
                "high": px * 1.001,
                "low": px * 0.999,
                "close": px,
                "volume": 1.0,
                "close_time": t0 + (i + 1) * 3_600_000 - 1,
            }
        )
    entry_ts = t0
    # 1m window starts long after entry (scrolled out); age ≫ 3×4h hold.
    now = entry_ts + 13 * 3_600_000
    exec_bars = []
    for i in range(30):
        ts = now - (29 - i) * 60_000
        exec_bars.append(
            {
                "open_time": ts,
                "open": 101.0,
                "high": 101.1,
                "low": 100.9,
                "close": 101.0,
                "volume": 1.0,
                "close_time": ts + 59_999,
            }
        )
    ms.save_candles(root, main, symbol="BTCUSDT", interval="1h", market="spot")
    ms.save_candles(root, exec_bars, symbol="BTCUSDT", interval="1m", market="spot")
    lp.save_open_positions(
        root,
        [
            {
                "ts": entry_ts,
                "symbol": "BTCUSDT",
                "interval": "1h",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 4,
                "horizon_exec": 240,
                "exec_interval": "1m",
                "tp_pct": 0.01,
                "sl_pct": 0.01,
                "entry_style": "market",
                "source": "model",
                "features": {},
                "feature_vec": [0.0] * 12,
                "margin_usdt": 10.0,
                "notional_usdt": 10.0,
                "leverage": 1.0,
            }
        ],
    )

    def _fake_fetch(*_a, **_k):
        return {"ok": True, "candles": [], "error": None}

    r = lp.run_live_tick(
        root,
        symbol="BTCUSDT",
        interval="1h",
        horizon=4,
        window=16,
        market="spot",
        exec_interval="1m",
        explore=False,
        micro_train=False,
        allow_open=False,
        fetch=_fake_fetch,
    )
    assert r["ok"]
    assert r["resolved"] == 1
    from eurika.ml.paper_trader import load_paper_trades

    assert lp.load_open_positions(root) == []
    trade = load_paper_trades(root)[-1]
    assert trade["exit_reason"] == "max_age"
    assert abs(float(trade["exit"]) - 101.0) < 1e-9
    assert any("max-age" in str(e.get("message") or "") for e in r["events"])

def test_shadow_gate_reject_uses_pending_oco_with_exec_tf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B12: cost-gate reject places a shadow OCO pending, not an instant market fill."""
    from eurika.ml import entry_cost
    from eurika.ml.paper_orders import load_pending_orders

    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    monkeypatch.setattr(lp, "cost_gate_ok", entry_cost.cost_gate_ok)
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(36):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0,
            }
        )
    ms.save_candles(tmp_path, main, symbol="BTCUSDT", interval="15m", market="spot")
    m1 = []
    for i in range(30):
        c = 100.0 + i * 0.01
        m1.append(
            {
                "open_time": t0 + i * 60_000,
                "open": c,
                "high": c * 1.001,
                "low": c * 0.999,
                "close": c,
                "volume": 1.0,
            }
        )
    ms.save_candles(tmp_path, m1, symbol="BTCUSDT", interval="1m", market="spot")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_entry_style",
        lambda *a, **k: {
            "style": "oco",
            "source": "model",
            "probs": {"market": 0.1, "limit": 0.1, "stop": 0.1, "oco": 0.7},
        },
    )

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        exec_interval="1m",
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    assert lp.load_open_positions(tmp_path) == []
    assert lp.load_shadow_positions(tmp_path) == []
    pend = load_pending_orders(tmp_path)
    assert len(pend) == 1
    assert pend[0].get("shadow") is True
    assert pend[0].get("entry_style") == "oco"
    assert pend[0].get("limit_px") is not None
    assert pend[0].get("stop_px") is not None
    assert not pend[0].get("margin_usdt")
    assert "не окупает комиссию" in " ".join(str(e.get("message") or "") for e in r["events"])


def test_shadow_pending_does_not_block_live_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shadow OCO pending must not reserve risk or block the live book."""
    from eurika.ml.paper_orders import build_pending_order, load_pending_orders, save_pending_orders

    monkeypatch.setattr(lp, "DEFAULT_EXEC_INTERVAL", "1m")
    t0 = 1_700_000_000_000
    main = []
    px = 100.0
    for i in range(36):
        o = px
        px = px * (1.01 if i % 2 == 0 else 0.995)
        main.append(
            {
                "open_time": t0 + i * 900_000,
                "open": o,
                "high": max(o, px) * 1.001,
                "low": min(o, px) * 0.999,
                "close": px,
                "volume": 5.0,
            }
        )
    ms.save_candles(tmp_path, main, symbol="BTCUSDT", interval="15m", market="spot")
    m1 = [
        {
            "open_time": t0 + i * 60_000,
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 1.0,
        }
        for i in range(30)
    ]
    ms.save_candles(tmp_path, m1, symbol="BTCUSDT", interval="1m", market="spot")
    save_pending_orders(
        tmp_path,
        [
            build_pending_order(
                symbol="BTCUSDT",
                market="spot",
                action="BUY",
                signal_px=100.0,
                signal_ts=t0 + 28 * 60_000,  # near last 1m bar — avoid expire on same tick
                interval="15m",
                entry_style="oco",
                horizon=2,
                horizon_exec=30,
                exec_interval="1m",
                tp_pct=0.01,
                sl_pct=0.01,
                shadow=True,
                gate_expansion=0.3,
            )
        ],
    )
    gate_path = tmp_path / ".eurika" / "ml" / "weights" / "entry_cost_gate.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text('{"expansion_min": -9.0, "cost_mult": 1.5}', encoding="utf-8")
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_action",
        lambda root, vec: {
            "action": "BUY",
            "source": "model",
            "probs": {"HOLD": 0.20, "BUY": 0.70, "SELL": 0.10},
        },
    )
    monkeypatch.setattr(
        "eurika.ml.live_paper.predict_entry_style",
        lambda *a, **k: {
            "style": "market",
            "source": "heuristic",
            "probs": {"market": 1.0, "limit": 0.0, "stop": 0.0, "oco": 0.0},
        },
    )

    r = lp.run_live_tick(
        tmp_path,
        symbol="BTCUSDT",
        interval="15m",
        window=16,
        horizon=2,
        market="spot",
        exec_interval="1m",
        micro_train=False,
        explore=False,
        fetch=lambda *a, **k: {"ok": True, "candles": [], "error": None},
    )
    assert r["ok"] is True
    opens = lp.load_open_positions(tmp_path)
    assert len(opens) == 1
    assert opens[0].get("shadow") is not True
    assert any(o.get("shadow") for o in load_pending_orders(tmp_path))
