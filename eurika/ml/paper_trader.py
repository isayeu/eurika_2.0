"""Paper BUY/SELL over stored candles; label correct/incorrect after horizon.

No live Binance orders.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from eurika.ml.features import (
    DEFAULT_IMPULSE_HORIZON,
    DEFAULT_WINDOW,
    feature_vector,
    features_dict,
    impulse_horizon,
)
from eurika.ml.market_store import (
    DEFAULT_INTERVAL,
    DEFAULT_SYMBOL,
    load_candles,
    ml_root,
)

ACTIONS = ("HOLD", "BUY", "SELL")
DEFAULT_HORIZON = 4
# Round-trip taker-ish paper fees (subtracted once from directional return).
DEFAULT_FEE_SPOT = 0.001  # ~0.1% RT (legacy paper default)
DEFAULT_FEE_FUTURES = 0.0008  # ~0.04%×2 USDT-M taker
DEFAULT_FEE = DEFAULT_FEE_SPOT
DEFAULT_THR = 0.0


def paper_trades_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "paper_trades.jsonl"


def fee_for_market(market: str | None) -> float:
    """Spot vs futures commission for paper edge/PnL."""
    from eurika.ml.market_store import normalize_market

    if normalize_market(market) == "futures":
        return float(DEFAULT_FEE_FUTURES)
    return float(DEFAULT_FEE_SPOT)


def funding_edge_delta(
    bars_held_1m: int,
    action: str,
    *,
    rate_8h: float | None = None,
) -> float:
    """Signed funding impact on edge (fraction of price).

    Binance USDT-M: positive ``rate_8h`` → longs pay shorts.
    Without a known rate → 0 (do not invent always-negative drag).
    Returned value is **added** to directional edge (BUY/SELL already signed).
    """
    if rate_8h is None:
        return 0.0
    bars = max(0, int(bars_held_1m))
    periods = (float(bars) / 60.0) / 8.0
    paid_by_longs = float(rate_8h) * periods
    act = (action or "").upper()
    if act == "BUY":
        return -paid_by_longs
    if act == "SELL":
        return paid_by_longs
    return 0.0


def funding_edge_from_settlements(
    action: str,
    settlements: Sequence[Mapping[str, Any]] | None,
) -> float:
    """Sum signed funding from actual 8h settlements (each rate is one period)."""
    if not settlements:
        return 0.0
    paid = 0.0
    for row in settlements:
        raw = row.get("funding_rate") if isinstance(row, Mapping) else row
        if not isinstance(raw, (int, float, str)):
            continue
        try:
            paid += float(raw)
        except (TypeError, ValueError):
            continue
    act = (action or "").upper()
    if act == "BUY":
        return -paid
    if act == "SELL":
        return paid
    return 0.0


def resolve_funding_edge(
    action: str,
    *,
    entry_ts_ms: int,
    exit_ts_ms: int,
    bars_held_1m: int = 0,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    last_funding_rate: float | None = None,
) -> dict[str, Any]:
    """Prefer history settlements in (entry, exit]; else pro-rata last rate; else 0."""
    t0 = int(entry_ts_ms)
    t1 = int(exit_ts_ms)
    in_window: list[Mapping[str, Any]] = []
    for row in settlements or ():
        if not isinstance(row, Mapping):
            continue
        raw_rate = row.get("funding_rate")
        if not isinstance(raw_rate, (int, float, str)):
            continue
        try:
            ts = int(row.get("funding_time") or 0)
            rate = float(raw_rate)
        except (TypeError, ValueError):
            continue
        if t0 < ts <= t1:
            in_window.append({"funding_rate": rate, "funding_time": ts})
    if in_window:
        edge = funding_edge_from_settlements(action, in_window)
        last_rate = in_window[-1]["funding_rate"]
        return {
            "funding": edge,
            "source": "history",
            "n_settlements": len(in_window),
            "last_funding_rate": float(last_rate) if isinstance(last_rate, (int, float, str)) else None,
        }
    if last_funding_rate is not None:
        bars = int(bars_held_1m)
        if bars <= 0 and t1 > t0:
            bars = max(0, int((t1 - t0) // 60_000))
        edge = funding_edge_delta(bars, action, rate_8h=float(last_funding_rate))
        return {
            "funding": edge,
            "source": "premium_prorata",
            "n_settlements": 0,
            "last_funding_rate": float(last_funding_rate),
        }
    return {
        "funding": 0.0,
        "source": "none",
        "n_settlements": 0,
        "last_funding_rate": None,
    }


# Back-compat name: was always-negative; now 0 unless rate given via funding_edge_delta.
def funding_drag_frac(
    bars_held_1m: int,
    *,
    per_8h: float | None = None,
) -> float:
    """Deprecated always-drag stub. Prefer ``funding_edge_delta`` with signed rate."""
    if per_8h is None:
        return 0.0
    bars = max(0, int(bars_held_1m))
    periods = (float(bars) / 60.0) / 8.0
    return max(0.0, float(per_8h) * periods)


def label_trade(
    entry: float,
    exit_px: float,
    action: str,
    *,
    fee: float = DEFAULT_FEE,
    thr: float = DEFAULT_THR,
    funding: float = 0.0,
) -> dict[str, Any]:
    """Compute directional return and correctness for BUY/SELL.

    ``fee`` is round-trip commission; ``funding`` is signed futures funding
    already expressed as an edge delta (see ``funding_edge_delta``).
    """
    act = (action or "").upper()
    if entry <= 0 or exit_px <= 0:
        return {"ret": 0.0, "correct": False, "edge": 0.0}
    raw = (exit_px / entry) - 1.0
    fee_c = max(0.0, float(fee))
    fund = float(funding)
    if act == "BUY":
        edge = raw - fee_c + fund
    elif act == "SELL":
        edge = (-raw) - fee_c + fund
    else:
        return {"ret": raw, "correct": False, "edge": 0.0}
    return {"ret": raw, "correct": bool(edge > thr), "edge": edge}


def momentum_policy(features: Sequence[float]) -> str:
    """Bootstrap policy: sign of window return → BUY/SELL, else HOLD."""
    if not features:
        return "HOLD"
    # features[2] == ret_window
    rw = float(features[2]) if len(features) > 2 else 0.0
    if rw > 0:
        return "BUY"
    if rw < 0:
        return "SELL"
    return "HOLD"


def run_paper_backfill(
    project_root: str | Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    window: int = DEFAULT_WINDOW,
    horizon: int = DEFAULT_HORIZON,
    fee: float = DEFAULT_FEE,
    thr: float = DEFAULT_THR,
    policy: Optional[Callable[[Sequence[float]], str]] = None,
    append: bool = True,
    max_trades: Optional[int] = None,
    market: str | None = "spot",
) -> dict[str, Any]:
    """Walk history; emit labeled paper trades. HOLD skipped."""
    from eurika.ml.market_store import normalize_market

    kind = normalize_market(market)
    candles = load_candles(project_root, symbol, interval, market=kind)
    w = max(8, int(window))
    h = max(1, int(horizon))
    choose = policy or momentum_policy
    h_max = max(h, int(DEFAULT_IMPULSE_HORIZON))
    if len(candles) < w + h_max + 1:
        return {
            "ok": False,
            "written": 0,
            "correct": 0,
            "incorrect": 0,
            "skipped_hold": 0,
            "error": f"need >= {w + h_max + 1} candles, have {len(candles)}",
            "path": str(paper_trades_path(project_root)),
        }

    rows: list[dict[str, Any]] = []
    skipped_hold = 0
    last_i = len(candles) - 1 - h_max
    for i in range(w - 1, last_i + 1):
        window_candles = candles[: i + 1]
        vec = feature_vector(window_candles, window=w)
        if vec is None:
            continue
        action = choose(vec)
        if action not in ("BUY", "SELL"):
            skipped_hold += 1
            continue
        feat = features_dict(window_candles, window=w) or {}
        h_eff = impulse_horizon(h, feat)
        if i + h_eff >= len(candles):
            continue
        entry = float(candles[i]["close"])
        exit_px = float(candles[i + h_eff]["close"])
        lab = label_trade(entry, exit_px, action, fee=fee, thr=thr)
        rows.append(
            {
                "ts": int(candles[i]["open_time"]),
                "exit_ts": int(candles[i + h_eff]["open_time"]),
                "symbol": (symbol or DEFAULT_SYMBOL).strip().upper(),
                "interval": interval,
                "market": kind,
                "action": action,
                "entry": entry,
                "exit": exit_px,
                "ret": lab["ret"],
                "edge": lab["edge"],
                "correct": lab["correct"],
                "horizon": h_eff,
                "fee": fee,
                "features": feat,
                "feature_vec": vec,
                "policy": "momentum" if policy is None else "custom",
            }
        )
        if max_trades is not None and len(rows) >= max_trades:
            break

    path = paper_trades_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.is_file() else "w"
    with path.open(mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    correct = sum(1 for r in rows if r.get("correct"))
    return {
        "ok": True,
        "written": len(rows),
        "correct": correct,
        "incorrect": len(rows) - correct,
        "skipped_hold": skipped_hold,
        "accuracy": (correct / len(rows)) if rows else None,
        "path": str(path),
        "market": kind,
        "error": None,
    }


def load_paper_trades(project_root: str | Path) -> list[dict[str, Any]]:
    path = paper_trades_path(project_root)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def paper_status(project_root: str | Path) -> dict[str, Any]:
    rows = load_paper_trades(project_root)
    correct = sum(1 for r in rows if r.get("correct"))
    buys = sum(1 for r in rows if r.get("action") == "BUY")
    sells = sum(1 for r in rows if r.get("action") == "SELL")
    return {
        "path": str(paper_trades_path(project_root)),
        "count": len(rows),
        "correct": correct,
        "incorrect": len(rows) - correct,
        "buys": buys,
        "sells": sells,
        "accuracy": (correct / len(rows)) if rows else None,
    }
