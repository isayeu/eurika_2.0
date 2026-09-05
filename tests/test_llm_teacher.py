"""LLM teacher samples mix into MLP train without opening paper."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.ml.features import FEATURE_NAMES
from eurika.ml.llm_teacher import (
    TEACHER_MAX_FRAC,
    TEACHER_WEIGHT,
    build_teacher_rows,
    harvest_teacher,
    mix_teacher_xy,
    parse_teacher_samples,
    samples_path,
)
from eurika.ml.paper_trader import paper_trades_path
from eurika.ml.paper_portfolio import ensure_portfolio


def _vec() -> list[float]:
    return [0.01] * len(FEATURE_NAMES)


def test_parse_teacher_json_from_prose() -> None:
    text = (
        "тикер ETHUSDT вход=да сторона=BUY\n"
        "```json\n"
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY",'
        '"tp_pct":0.01,"sl_pct":0.008}]}\n'
        "```"
    )
    rows = parse_teacher_samples(text)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "ETHUSDT"
    assert rows[0]["side"] == "BUY"


def test_build_keeps_independent_yes_despite_gate() -> None:
    cards = [
        {
            "symbol": "BTCUSDT",
            "market": "fut",
            "book": "open",
            "feature_vec": _vec(),
        },
        {
            "symbol": "ETHUSDT",
            "market": "fut",
            "book": "flat",
            "gate_reject": True,
            "feature_vec": _vec(),
        },
        {
            "symbol": "SOLUSDT",
            "market": "fut",
            "book": "flat",
            "feature_vec": _vec(),
        },
        {"symbol": "ADAUSDT", "market": "fut", "book": "flat"},
    ]
    payload = [
        {"symbol": "BTCUSDT", "market": "fut", "enter": "open", "side": "BUY"},
        {"symbol": "ETHUSDT", "market": "fut", "enter": "yes", "side": "BUY"},
        {"symbol": "SOLUSDT", "market": "fut", "enter": "no", "side": "BUY"},
        {"symbol": "ADAUSDT", "market": "fut", "enter": "yes", "side": "SELL"},
        {"symbol": "DOGEUSDT", "market": "fut", "enter": "yes", "side": "BUY"},
    ]
    rows = build_teacher_rows(payload, cards, now_ms=1)
    by_sym = {r["symbol"]: r for r in rows}
    assert set(by_sym) == {"ETHUSDT", "SOLUSDT"}
    assert by_sym["ETHUSDT"]["side"] == "BUY"
    assert by_sym["SOLUSDT"]["side"] == "HOLD"


def test_harvest_writes_teacher_not_paper(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    trades = paper_trades_path(tmp_path)
    before = trades.read_text(encoding="utf-8") if trades.is_file() else ""
    cards = [
        {
            "symbol": "ETHUSDT",
            "market": "fut",
            "feature_vec": _vec(),
            "tp_pct": 0.01,
            "sl_pct": 0.008,
        }
    ]
    text = '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY","tp_pct":0.01,"sl_pct":0.008}]}'
    out = harvest_teacher(tmp_path, text, cards, now_ms=9)
    assert out["stored"] == 1
    assert samples_path(tmp_path).is_file()
    after = trades.read_text(encoding="utf-8") if trades.is_file() else ""
    assert after == before


def test_mix_teacher_xy_caps_weight(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    cards = [{"symbol": "ETHUSDT", "market": "fut", "feature_vec": _vec()}]
    harvest_teacher(
        tmp_path,
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY"}]}',
        cards,
        now_ms=1_700_000_000_000,
    )
    xs = [[0.0] * len(FEATURE_NAMES) for _ in range(4)]
    ys = [0, 1, 2, 1]
    ws = [8.0, 8.0, 8.0, 8.0]
    mx, my, mw, n = mix_teacher_xy(tmp_path, xs, ys, ws, now_ms=1_700_000_000_000)
    assert n == 1
    assert len(mx) == 5
    assert my[-1] == 1  # BUY, still pending
    assert mw[-1] <= TEACHER_WEIGHT
    assert mw[-1] <= sum(ws) * TEACHER_MAX_FRAC + 1e-9


def test_settle_win_uses_paper_weight(tmp_path: Path) -> None:
    from eurika.ml.llm_teacher_settle import settle_teacher
    from eurika.ml.market_model import sample_weight_from_row

    ensure_portfolio(tmp_path)
    cards = [{"symbol": "ETHUSDT", "market": "fut", "feature_vec": _vec()}]
    t0 = 1_700_000_000_000
    harvest_teacher(
        tmp_path,
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY"}]}',
        cards,
        now_ms=t0,
    )
    trades = paper_trades_path(tmp_path)
    trades.parent.mkdir(parents=True, exist_ok=True)
    trades.write_text(
        '{"live":true,"symbol":"ETHUSDT","market":"futures","action":"BUY",'
        '"edge":0.01,"pnl_usdt":2.0,"exit_ts":%d,"exit_reason":"tp"}\n' % (t0 + 50_000),
        encoding="utf-8",
    )
    info = settle_teacher(tmp_path, now_ms=t0 + 50_000)
    assert info["settled"] == 1
    xs = [[0.0] * len(FEATURE_NAMES)]
    ys = [0]
    ws = [8.0]
    _, my, mw, n = mix_teacher_xy(tmp_path, xs, ys, ws, now_ms=t0 + 50_000)
    assert n == 1
    assert my[-1] == 1
    expect = sample_weight_from_row({"pnl_usdt": 2.0})
    assert mw[-1] == pytest.approx(expect)


def test_settle_loss_relabels_hold(tmp_path: Path) -> None:
    from eurika.ml.llm_teacher_settle import settle_teacher

    ensure_portfolio(tmp_path)
    cards = [{"symbol": "ETHUSDT", "market": "fut", "feature_vec": _vec()}]
    t0 = 1_700_000_000_000
    harvest_teacher(
        tmp_path,
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY"}]}',
        cards,
        now_ms=t0,
    )
    trades = paper_trades_path(tmp_path)
    trades.parent.mkdir(parents=True, exist_ok=True)
    trades.write_text(
        '{"live":true,"symbol":"ETHUSDT","market":"futures","action":"BUY",'
        '"edge":-0.02,"pnl_usdt":-1.5,"exit_ts":%d,"exit_reason":"sl"}\n' % (t0 + 50_000),
        encoding="utf-8",
    )
    settle_teacher(tmp_path, now_ms=t0 + 50_000)
    _, my, _, n = mix_teacher_xy(
        tmp_path, [[0.0] * len(FEATURE_NAMES)], [0], [1.0], now_ms=t0 + 50_000
    )
    assert n == 1
    assert my[-1] == 0  # HOLD


def test_profit_bonus_when_llm_beats_paper() -> None:
    from eurika.ml.llm_teacher_settle import profit_bonus

    assert profit_bonus(0.01, 0.01) == 1.0
    assert profit_bonus(-0.01, 0.02) == 1.0
    bonus = profit_bonus(0.02, -0.015)
    assert 1.5 <= bonus <= 2.0


def test_settle_expires_without_close(tmp_path: Path) -> None:
    from eurika.ml.llm_teacher_settle import MATCH_WINDOW_MS, settle_teacher

    ensure_portfolio(tmp_path)
    cards = [{"symbol": "ETHUSDT", "market": "fut", "feature_vec": _vec()}]
    t0 = 1_700_000_000_000
    harvest_teacher(
        tmp_path,
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY"}]}',
        cards,
        now_ms=t0,
    )
    info = settle_teacher(tmp_path, now_ms=t0 + MATCH_WINDOW_MS + 1)
    assert info["expired"] == 1
    _, _, _, n = mix_teacher_xy(
        tmp_path, [[0.0] * len(FEATURE_NAMES)], [0], [1.0], now_ms=t0 + MATCH_WINDOW_MS + 1
    )
    assert n == 0


def _bars(start_ms: int, n: int, *, px: float, step: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(n):
        close = px + i * step
        rows.append(
            {
                "open_time": start_ms + i * 900_000,
                "open": close,
                "high": close + abs(step) * 2,
                "low": close - abs(step) * 0.1,
                "close": close,
                "volume": 10.0,
            }
        )
    return rows


def test_settle_grades_candle_path_without_mlp_fill(tmp_path: Path) -> None:
    from eurika.ml.llm_teacher_settle import settle_teacher
    from eurika.ml.market_store import save_candles

    ensure_portfolio(tmp_path)
    t0 = 1_700_000_000_000
    cards = [
        {
            "symbol": "ETHUSDT",
            "market": "fut",
            "interval": "15m",
            "feature_vec": _vec(),
        }
    ]
    harvest_teacher(
        tmp_path,
        '{"samples":[{"symbol":"ETHUSDT","market":"fut","enter":"yes","side":"BUY",'
        '"tp_pct":0.01,"sl_pct":0.01}]}',
        cards,
        now_ms=t0,
    )
    save_candles(
        tmp_path,
        _bars(t0, 6, px=100.0, step=0.6),
        symbol="ETHUSDT",
        interval="15m",
        market="futures",
    )
    info = settle_teacher(tmp_path, now_ms=t0 + 5 * 900_000)
    assert info["settled"] == 1
    assert info["expired"] == 0
    xs = [[0.0] * len(FEATURE_NAMES)]
    ys = [0]
    ws = [8.0]
    _, my, mw, n = mix_teacher_xy(tmp_path, xs, ys, ws, now_ms=t0 + 5 * 900_000)
    assert n == 1
    assert my[-1] == 1  # BUY kept — path paid
    assert mw[-1] > TEACHER_WEIGHT
