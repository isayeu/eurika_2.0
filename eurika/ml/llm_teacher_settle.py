"""Settle LLM teacher rows against later profit, not against MLP's book.

Prefer a live paper close when one exists. Otherwise walk later candles with
the teacher's TP/SL and venue fees — so reasoning can be graded even when
MLP/gates never entered. Never opens trades.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eurika.ml.llm_teacher import (
    TEACHER_WEIGHT,
    load_teacher_samples,
    samples_path,
)
from eurika.ml.paper_trader import is_executed_trade, load_paper_trades

MATCH_WINDOW_MS = 24 * 60 * 60 * 1000
BONUS_MAX = 2.0
SETTLED_MAX_FRAC = 1.0
DEFAULT_TP_PCT = 0.01
DEFAULT_SL_PCT = 0.01


def _mk(market: object) -> str:
    text = str(market or "spot").strip().lower()
    if text in {"futures", "fut", "perp"}:
        return "futures"
    return "spot"


def _trade_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row.get("symbol") or "").upper(),
        _mk(row.get("market")),
        int(row.get("exit_ts") or 0),
    )


def _live_closes(project_root: str | Path, *, since_ms: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in load_paper_trades(project_root):
        if not is_executed_trade(row) or row.get("shadow") or not row.get("live"):
            continue
        exit_ts = int(row.get("exit_ts") or 0)
        if exit_ts < since_ms:
            continue
        if not str(row.get("symbol") or "").strip():
            continue
        out.append(row)
    out.sort(key=lambda r: int(r.get("exit_ts") or 0))
    return out


def _mean_edge(rows: list[dict[str, Any]]) -> float | None:
    vals = [float(r["edge"]) for r in rows if isinstance(r.get("edge"), (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def profit_bonus(llm_mean: float | None, paper_mean: float | None) -> float:
    """Scale >1 when LLM settled edge beats paper mean edge."""
    if llm_mean is None or paper_mean is None:
        return 1.0
    if llm_mean <= paper_mean:
        return 1.0
    gap = llm_mean - paper_mean
    denom = max(abs(paper_mean), 0.001)
    return min(BONUS_MAX, 1.0 + gap / denom)


def _grade(sample: dict[str, Any], trade: dict[str, Any]) -> dict[str, Any]:
    from eurika.ml.market_model import sample_weight_from_row

    side = str(sample.get("side") or "HOLD").upper()
    edge = trade.get("edge")
    edge_f = float(edge) if isinstance(edge, (int, float)) else None
    won = edge_f is not None and edge_f > 0
    if side in {"BUY", "SELL"}:
        label = side if won else "HOLD"
        skip = False
    else:
        # HOLD was right if the next live fill lost money.
        label = "HOLD"
        skip = bool(won)
    out = dict(sample)
    out["settled"] = True
    out["skip"] = skip
    out["side"] = label
    out["edge"] = edge_f
    out["pnl_usdt"] = trade.get("pnl_usdt")
    out["match_exit_ts"] = int(trade.get("exit_ts") or 0)
    out["match_action"] = str(trade.get("action") or "")
    out["settle_source"] = str(trade.get("source") or "live")
    if skip:
        out["weight"] = TEACHER_WEIGHT
    else:
        out["weight"] = float(sample_weight_from_row(trade))
    return out


def _horizon_bars(interval: str) -> int:
    return {"5m": 12, "15m": 4, "1h": 1, "4h": 1}.get(interval, 4)


def _load_path_candles(
    project_root: str | Path,
    sample: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    from eurika.ml.market_store import load_candles, normalize_market

    symbol = str(sample.get("symbol") or "").strip().upper()
    if not symbol:
        return "", []
    kind = normalize_market(sample.get("market"))
    hint = str(sample.get("interval") or "").strip()
    hint2 = str(sample.get("interval2") or "").strip()
    order: list[str] = []
    for iv in (hint, hint2, "15m", "1h", "5m", "4h"):
        if iv and iv not in order:
            order.append(iv)
    ts = int(sample.get("ts") or 0)
    best: tuple[str, list[dict[str, Any]]] = ("", [])
    for iv in order:
        rows = load_candles(project_root, symbol, iv, market=kind)
        future = [c for c in rows if int(c.get("open_time") or 0) >= ts]
        if len(future) > len(best[1]):
            best = (iv, future)
        if len(future) >= 1 + _horizon_bars(iv):
            return iv, future
    return best


def _hit_levels(
    *,
    side: str,
    entry: float,
    high: float,
    low: float,
    tp: float,
    sl: float,
) -> tuple[float, str] | None:
    if side == "BUY":
        hit_tp = high >= entry * (1.0 + tp)
        hit_sl = low <= entry * (1.0 - sl)
        if hit_sl:
            return entry * (1.0 - sl), "sl"
        if hit_tp:
            return entry * (1.0 + tp), "tp"
        return None
    hit_tp = low <= entry * (1.0 - tp)
    hit_sl = high >= entry * (1.0 + sl)
    if hit_sl:
        return entry * (1.0 + sl), "sl"
    if hit_tp:
        return entry * (1.0 - tp), "tp"
    return None


def simulate_teacher_path(
    project_root: str | Path,
    sample: dict[str, Any],
    *,
    now_ms: int,
) -> dict[str, Any] | None:
    """Virtual fill of the teacher's advice on later candles. None = still waiting."""
    from eurika.ml.paper_trader import fee_for_market, label_trade

    interval, candles = _load_path_candles(project_root, sample)
    if len(candles) < 2:
        return None
    need = _horizon_bars(interval)
    path = candles[1:]
    timed_out = now_ms - int(sample.get("ts") or 0) > MATCH_WINDOW_MS
    if len(path) < need and not timed_out:
        return None
    path = path[: max(1, need)]
    try:
        entry = float(candles[0]["close"])
    except (TypeError, ValueError, KeyError):
        return None
    if entry <= 0:
        return None
    side = str(sample.get("side") or "HOLD").upper()
    fee = fee_for_market(sample.get("market"))
    last = path[-1]
    try:
        last_close = float(last.get("close") or 0)
        last_ts = int(last.get("open_time") or 0)
    except (TypeError, ValueError):
        return None
    if side not in {"BUY", "SELL"}:
        buy = label_trade(entry, last_close, "BUY", fee=fee)
        sell = label_trade(entry, last_close, "SELL", fee=fee)
        missed = max(float(buy.get("edge") or 0), float(sell.get("edge") or 0))
        return {
            "action": "HOLD",
            "edge": missed,
            "exit_ts": last_ts,
            "exit_reason": "horizon",
            "source": "llm_path",
        }
    try:
        tp = float(sample.get("tp_pct") or DEFAULT_TP_PCT)
        sl = float(sample.get("sl_pct") or DEFAULT_SL_PCT)
    except (TypeError, ValueError):
        tp, sl = DEFAULT_TP_PCT, DEFAULT_SL_PCT
    tp = max(0.001, min(0.2, tp))
    sl = max(0.001, min(0.2, sl))
    exit_px = last_close
    reason = "horizon"
    for bar in path:
        try:
            high = float(bar.get("high") or bar.get("close") or 0)
            low = float(bar.get("low") or bar.get("close") or 0)
            ts = int(bar.get("open_time") or 0)
        except (TypeError, ValueError):
            continue
        hit = _hit_levels(side=side, entry=entry, high=high, low=low, tp=tp, sl=sl)
        if hit is None:
            continue
        exit_px, reason = hit
        last_ts = ts
        break
    lab = label_trade(entry, exit_px, side, fee=fee)
    return {
        "action": side,
        "edge": lab.get("edge"),
        "exit_ts": last_ts,
        "exit_reason": reason,
        "source": "llm_path",
    }


def _pick_trade(
    sample: dict[str, Any],
    closes: list[dict[str, Any]],
    used: set[tuple[str, str, int]],
) -> dict[str, Any] | None:
    ts = int(sample.get("ts") or 0)
    deadline = ts + MATCH_WINDOW_MS
    want_sym = str(sample.get("symbol") or "").upper()
    want_mkt = _mk(sample.get("market"))
    side = str(sample.get("side") or "HOLD").upper()
    for trade in closes:
        exit_ts = int(trade.get("exit_ts") or 0)
        if exit_ts < ts or exit_ts > deadline:
            continue
        if str(trade.get("symbol") or "").upper() != want_sym:
            continue
        if _mk(trade.get("market")) != want_mkt:
            continue
        key = _trade_key(trade)
        if key in used:
            continue
        action = str(trade.get("action") or "").upper()
        if side in {"BUY", "SELL"} and action != side:
            continue
        return trade
    return None


def save_teacher_samples(project_root: str | Path, rows: list[dict[str, Any]]) -> Path:
    path = samples_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def settle_teacher(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Match pending LLM rows to live closes, else to the later candle path."""
    import time

    now = int(now_ms if now_ms is not None else time.time() * 1000)
    rows = load_teacher_samples(project_root)
    if not rows:
        return {"settled": 0, "pending": 0, "expired": 0, "bonus": 1.0}
    pending_idx = [i for i, r in enumerate(rows) if not r.get("settled")]
    if pending_idx:
        min_ts = min(int(rows[i].get("ts") or 0) for i in pending_idx)
        closes = _live_closes(project_root, since_ms=min_ts)
    else:
        closes = []
    used = {
        (str(r.get("symbol") or "").upper(), _mk(r.get("market")), int(r.get("match_exit_ts") or 0))
        for r in rows
        if r.get("settled") and int(r.get("match_exit_ts") or 0) > 0
    }
    n_new = 0
    n_exp = 0
    changed = False
    for i in pending_idx:
        sample = rows[i]
        trade = _pick_trade(sample, closes, used)
        if trade is None:
            path = simulate_teacher_path(project_root, sample, now_ms=now)
            if path is not None:
                trade = path
        if trade is not None:
            graded = _grade(sample, trade)
            rows[i] = graded
            if not trade.get("source"):
                used.add(_trade_key(trade))
            n_new += 1
            changed = True
            continue
        ts = int(sample.get("ts") or 0)
        if now - ts > MATCH_WINDOW_MS:
            expired = dict(sample)
            expired["settled"] = True
            expired["skip"] = True
            expired["expired"] = True
            rows[i] = expired
            n_exp += 1
            changed = True
    if changed:
        save_teacher_samples(project_root, rows)
    settled_ok = [
        r
        for r in rows
        if r.get("settled") and not r.get("skip") and isinstance(r.get("edge"), (int, float))
    ]
    paper = _live_closes(project_root, since_ms=min((int(r.get("ts") or 0) for r in rows), default=0))
    bonus = profit_bonus(_mean_edge(settled_ok), _mean_edge(paper))
    pending = sum(1 for r in rows if not r.get("settled"))
    return {
        "settled": n_new,
        "pending": pending,
        "expired": n_exp,
        "bonus": bonus,
        "llm_mean_edge": _mean_edge(settled_ok),
        "paper_mean_edge": _mean_edge(paper),
    }
