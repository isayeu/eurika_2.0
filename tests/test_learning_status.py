"""Tests for market learning status aggregate."""

from __future__ import annotations

from pathlib import Path

from eurika.ml import learning_status as ls
from eurika.ml import market_store as ms
from eurika.ml.paper_trader import paper_trades_path


def test_market_learning_status_empty(tmp_path: Path) -> None:
    st = ls.market_learning_status(tmp_path)
    assert st["paper"]["count"] == 0
    assert st["opens"]["count"] == 0
    assert st["live"]["count"] == 0
    assert abs(float(st["portfolio"]["equity_usdt"]) - 1000.0) < 1e-9
    text = ls.format_market_learning_block(st)
    assert "MARKET LEARNING" in text
    assert "сделки всего: 0" in text
    assert "банк:" in text


def test_market_learning_status_with_live_row(tmp_path: Path) -> None:
    ms.save_candles(
        tmp_path,
        [
            {
                "open_time": 1,
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.0,
                "volume": 1.0,
                "close_time": 2,
            }
        ]
        * 5,
        symbol="ETHUSDT",
        interval="15m",
    )
    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"action":"SELL","correct":true,"live":true,"feature_vec":[0,0,0,0,0,0,0]}\n',
        encoding="utf-8",
    )
    st = ls.market_learning_status(tmp_path)
    assert st["paper"]["count"] == 1
    assert st["live"]["count"] == 1
    assert st["live"]["accuracy"] == 1.0
    assert any(s.get("symbol") == "ETHUSDT" for s in (st["market"].get("series") or []))


def test_format_lists_all_opens_with_market(tmp_path: Path) -> None:
    from eurika.ml.live_paper import save_open_positions

    positions = []
    for i, sym in enumerate(
        ["ADAUSDT", "ARBUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DASHUSDT", "PAXGUSDT", "RENDERUSDT", "ONGUSDT"]
    ):
        positions.append(
            {
                "symbol": sym,
                "market": "spot",
                "action": "BUY",
                "entry": 1.0 + i,
                "horizon": 2,
                "source": "model",
            }
        )
    save_open_positions(tmp_path, positions)
    st = ls.market_learning_status(tmp_path)
    assert st["opens"]["count"] == 9
    assert st["opens"]["spot"] == 9
    assert st["opens"]["futures"] == 0
    assert len(st["opens"]["positions"]) == 9
    text = ls.format_market_learning_block(st)
    assert "открыто paper: 9" in text
    assert "spot=9" in text
    assert "ONGUSDT [spot]" in text
    assert "ADAUSDT [spot]" in text


def test_live_split_spot_futures(tmp_path: Path) -> None:
    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"action":"BUY","correct":true,"live":true,"market":"spot","edge":0.01,"exit_ts":2000}',
                '{"action":"SELL","correct":false,"live":true,"market":"futures","edge":-0.02,"exit_ts":3000}',
                '{"action":"BUY","correct":true,"live":true,"market":"futures","edge":0.03,"exit_ts":4000}',
                '{"action":"SELL","correct":true,"live":false,"market":"spot","edge":0.05,"exit_ts":1000}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    st = ls.market_learning_status(tmp_path)
    assert st["live"]["count"] == 3
    assert st["live"]["spot"]["count"] == 1
    assert st["live"]["futures"]["count"] == 2
    assert st["live"]["futures"]["accuracy"] == 0.5
    assert abs(float(st["pnl"]["all"]["sum_edge"]) - 0.07) < 1e-9
    assert abs(float(st["pnl"]["live"]["sum_edge"]) - 0.02) < 1e-9
    assert abs(float(st["pnl"]["live_spot"]["sum_edge"]) - 0.01) < 1e-9
    assert abs(float(st["pnl"]["live_futures"]["sum_edge"]) - 0.01) < 1e-9
    text = ls.format_market_learning_block(st)
    assert "spot=1" in text
    assert "fut=2" in text
    assert "PnL Σ edge" in text


def test_pnl_session_since_live_start(tmp_path: Path) -> None:
    path = paper_trades_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '{"action":"BUY","correct":true,"live":true,"edge":0.01,"exit_ts":1000}',
                '{"action":"SELL","correct":true,"live":true,"edge":-0.02,"exit_ts":5000}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    sess = ls.mark_live_session_start(tmp_path)
    # Force session start between the two exits.
    sess_path = ls.live_session_path(tmp_path)
    sess_path.write_text('{"started_ms": 3000}\n', encoding="utf-8")
    st = ls.market_learning_status(tmp_path)
    assert st["pnl"]["session"]["n"] == 1
    assert abs(float(st["pnl"]["session"]["sum_edge"]) - (-0.02)) < 1e-9
    text = ls.format_market_learning_block(st)
    assert "сессия=" in text
    assert sess.get("started_ms")  # mark wrote something earlier


def test_format_market_situation_block(tmp_path: Path) -> None:
    from eurika.ml.live_paper import save_open_positions
    from eurika.ml.market_journal import append_market_journal
    from eurika.ml.paper_portfolio import ensure_portfolio

    ensure_portfolio(tmp_path)
    save_open_positions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "spot",
                "action": "BUY",
                "entry": 100.0,
                "horizon": 2,
                "source": "model/soft",
                "margin_usdt": 10.0,
                "leverage": 1.0,
            }
        ],
    )
    append_market_journal(
        tmp_path,
        "анализ: ETHUSDT fut окно=+1.0%, волат=0.002 → совет: ДЕРЖАТЬ (источник: модель), P: держать=0.55",
        kind="analysis",
    )
    append_market_journal(
        tmp_path,
        "анализ: ADAUSDT окно=+0.1% → совет: ПОКУПКА (источник: модель/мягкий), P: держать=0.50 покуп=0.30",
        kind="analysis",
    )
    text = ls.format_market_situation_block(tmp_path)
    assert "MARKET СЕЙЧАС" in text
    assert "equity=" in text
    assert "BTCUSDT" in text
    assert "ADAUSDT" in text and "BUY" in text
    assert "ETHUSDT" in text and "HOLD" in text
    assert "per-ticker" in text.lower() or "общая" in text