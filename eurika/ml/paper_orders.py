"""Paper pending entries: market / limit / stop / OCO + cancel.

No live Binance orders — 1m simulation only.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


from eurika.ml.exec_tf import _bar_high_low, find_entry_index
from eurika.ml.market_store import ml_root, normalize_market

ENTRY_STYLES = ("market", "limit", "stop", "oco")
DEFAULT_LIMIT_OFFSET_PCT = 0.0015  # 0.15% pullback for limit leg
DEFAULT_STOP_OFFSET_PCT = 0.0015  # 0.15% breakout for stop leg
DEFAULT_INVALIDATE_PCT = 0.005  # 0.5% against plan → cancel pending
DEFAULT_TRAIL_PCT = 0.002  # 0.2% trailing distance
DEFAULT_PENDING_HORIZON_FRAC = 0.5  # pending lives half of position horizon_exec


def choose_entry_style(features: Mapping[str, Any] | None, *, rng: Any = None) -> str:
    """Heuristic bootstrap for entry style from main-TF features (until style ML ready)."""
    feat = features or {}
    burst = float(feat.get("atr_burst") or 0.0)
    brk = abs(float(feat.get("range_break") or 0.0))
    bb = float(feat.get("bb_pos") or 0.0)
    vol = float(feat.get("volatility") or 0.0)

    if burst >= 0.5 or brk >= 0.002:
        return "stop"  # breakout / impulse
    if abs(bb) >= 0.85:
        return "limit"  # mean-reversion toward mid
    if vol >= 0.008:
        return "oco"  # pullback or breakout
    return "market"


def _style_fill_score(action: str, signal_px: float, fill_px: float) -> float:
    """Higher is better: BUY wants lower fill, SELL wants higher fill (vs signal)."""
    if signal_px <= 0 or fill_px <= 0:
        return float("-inf")
    act = (action or "").upper()
    if act == "BUY":
        return (signal_px - fill_px) / signal_px
    if act == "SELL":
        return (fill_px - signal_px) / signal_px
    return float("-inf")


def simulate_style_fill_on_path(
    *,
    action: str,
    signal_px: float,
    style: str,
    candles_exec: Sequence[dict[str, Any]],
    start_idx: int = 0,
    pending_horizon_exec: int = 60,
    limit_offset_pct: float = DEFAULT_LIMIT_OFFSET_PCT,
    stop_offset_pct: float = DEFAULT_STOP_OFFSET_PCT,
    invalidate_pct: float = DEFAULT_INVALIDATE_PCT,
) -> dict[str, Any]:
    """Simulate one entry style on a known 1m path. Returns fill/cancel outcome."""
    act = (action or "").upper()
    st = (style or "market").strip().lower()
    if st not in ENTRY_STYLES:
        st = "market"
    px = float(signal_px)
    if px <= 0 or not candles_exec or start_idx < 0 or start_idx >= len(candles_exec):
        return {"status": "cancelled", "reason": "no_path", "entry": None, "style": st}

    order = build_pending_order(
        symbol="SIM",
        market="spot",
        action=act,
        signal_px=px,
        signal_ts=int(candles_exec[start_idx].get("open_time") or 0),
        interval="1h",
        entry_style=st,
        horizon=1,
        horizon_exec=max(1, int(pending_horizon_exec) * 2),
        exec_interval="1m",
        tp_pct=0.0,
        sl_pct=0.0,
        trail_pct=0.0,
        invalidate_pct=invalidate_pct,
        limit_offset_pct=limit_offset_pct,
        stop_offset_pct=stop_offset_pct,
    )
    # Override pending life to the window we evaluate.
    order["pending_horizon_exec"] = max(1, int(pending_horizon_exec))
    order["ts"] = int(candles_exec[start_idx].get("open_time") or 0)

    if st == "market":
        close = float(candles_exec[start_idx]["close"])
        return {"status": "filled", "reason": "market", "entry": close, "style": st}

    end = min(len(candles_exec), start_idx + max(1, int(pending_horizon_exec)) + 1)
    for i in range(start_idx, end):
        result = simulate_pending_on_bar(order, candles_exec[i], bars_since_place=i - start_idx)
        if result["status"] == "filled":
            return {
                "status": "filled",
                "reason": result.get("reason") or st,
                "entry": float(result["entry"]),
                "style": st,
            }
        if result["status"] == "cancelled":
            return {
                "status": "cancelled",
                "reason": result.get("reason") or "cancel",
                "entry": None,
                "style": st,
            }
    return {"status": "cancelled", "reason": "expire", "entry": None, "style": st}


def retro_best_entry_style(
    *,
    action: str,
    signal_px: float,
    candles_exec: Sequence[dict[str, Any]],
    signal_ts: int | None = None,
    pending_horizon_exec: int = 60,
    limit_offset_pct: float = DEFAULT_LIMIT_OFFSET_PCT,
    stop_offset_pct: float = DEFAULT_STOP_OFFSET_PCT,
    invalidate_pct: float = DEFAULT_INVALIDATE_PCT,
) -> dict[str, Any]:
    """Hindsight label: which style would have gotten the best fill on this 1m path.

    No hand-tuned trading thresholds — compares simulated fills only.
    """
    act = (action or "").upper()
    if act not in ("BUY", "SELL") or float(signal_px) <= 0 or not candles_exec:
        return {"style": None, "score": None, "filled": {}, "reason": "invalid"}

    start_idx = 0
    if signal_ts is not None:
        idx = find_entry_index(candles_exec, int(signal_ts))
        if idx >= 0:
            start_idx = idx

    best_style = "market"
    best_score = float("-inf")
    filled: dict[str, Any] = {}
    for style in ENTRY_STYLES:
        out = simulate_style_fill_on_path(
            action=act,
            signal_px=float(signal_px),
            style=style,
            candles_exec=candles_exec,
            start_idx=start_idx,
            pending_horizon_exec=pending_horizon_exec,
            limit_offset_pct=limit_offset_pct,
            stop_offset_pct=stop_offset_pct,
            invalidate_pct=invalidate_pct,
        )
        filled[style] = out
        if out.get("status") != "filled" or out.get("entry") is None:
            continue
        score = _style_fill_score(act, float(signal_px), float(out["entry"]))
        # Prefer better price; ties keep earlier style order with market first via init.
        if score > best_score + 1e-12:
            best_score = score
            best_style = style
        elif abs(score - best_score) <= 1e-12 and style == "market":
            best_style = "market"

    if best_score == float("-inf"):
        # Nothing filled — still label market as safe default teacher.
        return {
            "style": "market",
            "score": 0.0,
            "filled": filled,
            "reason": "fallback_market",
        }
    return {"style": best_style, "score": best_score, "filled": filled, "reason": "best_fill"}


def pending_orders_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "pending_orders.json"


def load_pending_orders(project_root: str | Path) -> list[dict[str, Any]]:
    path = pending_orders_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and isinstance(data.get("orders"), list):
        return [r for r in data["orders"] if isinstance(r, dict)]
    return []


def save_pending_orders(project_root: str | Path, orders: list[dict[str, Any]]) -> Path:
    path = pending_orders_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(orders, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_pending_order(
    *,
    symbol: str,
    market: str,
    action: str,
    signal_px: float,
    signal_ts: int,
    interval: str,
    entry_style: str,
    horizon: int,
    horizon_exec: int,
    exec_interval: str,
    tp_pct: float,
    sl_pct: float,
    trail_pct: float = 0.0,
    invalidate_pct: float = DEFAULT_INVALIDATE_PCT,
    limit_offset_pct: float = DEFAULT_LIMIT_OFFSET_PCT,
    stop_offset_pct: float = DEFAULT_STOP_OFFSET_PCT,
    features: Optional[dict[str, Any]] = None,
    feature_vec: Optional[list[float]] = None,
    source: str = "live",
) -> dict[str, Any]:
    """Create a pending (or immediately fillable market) paper order."""
    act = (action or "").upper()
    style = (entry_style or "market").strip().lower()
    if style not in ENTRY_STYLES:
        style = "market"
    px = float(signal_px)
    kind = normalize_market(market)
    lim_off = max(0.0, float(limit_offset_pct))
    stop_off = max(0.0, float(stop_offset_pct))
    inv = max(0.0, float(invalidate_pct))
    h_exec = max(1, int(horizon_exec))
    pending_h = max(1, int(h_exec * DEFAULT_PENDING_HORIZON_FRAC))

    limit_px: float | None = None
    stop_px: float | None = None
    if act == "BUY":
        limit_px = px * (1.0 - lim_off) if style in ("limit", "oco") else None
        stop_px = px * (1.0 + stop_off) if style in ("stop", "oco") else None
        invalidate_px = px * (1.0 - inv) if inv > 0 else None  # dump → cancel
    else:
        limit_px = px * (1.0 + lim_off) if style in ("limit", "oco") else None
        stop_px = px * (1.0 - stop_off) if style in ("stop", "oco") else None
        invalidate_px = px * (1.0 + inv) if inv > 0 else None  # rally against short

    return {
        "id": str(uuid.uuid4())[:12],
        "status": "pending",
        "entry_style": style if style != "market" else "market",
        "symbol": (symbol or "").strip().upper(),
        "market": kind,
        "action": act,
        "signal_px": px,
        "signal_ts": int(signal_ts),
        "ts": int(signal_ts),  # placed_ts on exec TF
        "interval": interval,
        "exec_interval": exec_interval,
        "horizon": max(1, int(horizon)),
        "horizon_exec": h_exec,
        "pending_horizon_exec": pending_h,
        "limit_px": limit_px,
        "stop_px": stop_px,
        "invalidate_px": invalidate_px,
        "invalidate_pct": inv,
        "tp_pct": max(0.0, float(tp_pct)),
        "sl_pct": max(0.0, float(sl_pct)),
        "trail_pct": max(0.0, float(trail_pct)),
        "features": features or {},
        "feature_vec": list(feature_vec or []),
        "source": source,
    }


def _filled_position_from_order(order: dict[str, Any], *, entry: float, entry_ts: int) -> dict[str, Any]:
    trail = max(0.0, float(order.get("trail_pct") or 0.0))
    pos = {
        "ts": int(entry_ts),
        "signal_ts": int(order.get("signal_ts") or entry_ts),
        "signal_px": float(order.get("signal_px") or entry),
        "symbol": order.get("symbol"),
        "interval": order.get("interval"),
        "market": order.get("market"),
        "action": order.get("action"),
        "entry": float(entry),
        "horizon": order.get("horizon"),
        "horizon_exec": order.get("horizon_exec"),
        "pending_horizon_exec": order.get("pending_horizon_exec"),
        "exec_interval": order.get("exec_interval"),
        "tp_pct": order.get("tp_pct"),
        "sl_pct": order.get("sl_pct"),
        "trail_pct": trail if trail > 0 else None,
        "trail_extreme": float(entry),
        "entry_style": order.get("entry_style") or "market",
        "style_source": order.get("style_source"),
        "pending_id": order.get("id"),
        "features": order.get("features") or {},
        "feature_vec": order.get("feature_vec") or [],
        "source": order.get("source") or "live",
        "levels_source": order.get("levels_source"),
    }
    for key in ("margin_usdt", "notional_usdt", "leverage"):
        if order.get(key) is not None:
            pos[key] = order.get(key)
    return pos


def simulate_pending_on_bar(
    order: dict[str, Any],
    bar: dict[str, Any],
    *,
    bars_since_place: int,
) -> dict[str, Any]:
    """Evaluate one 1m bar against a pending order.

    Returns {status: pending|filled|cancelled, reason?, entry?, entry_ts?, position?}.
    """
    act = str(order.get("action") or "").upper()
    style = str(order.get("entry_style") or "market").lower()
    high, low, close = _bar_high_low(bar)
    ts = int(bar.get("open_time") or 0)
    pending_h = max(1, int(order.get("pending_horizon_exec") or 1))

    if bars_since_place > pending_h:
        return {"status": "cancelled", "reason": "expire", "entry": None, "entry_ts": ts}

    inv_px = order.get("invalidate_px")
    if inv_px is not None:
        inv = float(inv_px)
        if act == "BUY" and low <= inv:
            return {"status": "cancelled", "reason": "invalidate", "entry": None, "entry_ts": ts}
        if act == "SELL" and high >= inv:
            return {"status": "cancelled", "reason": "invalidate", "entry": None, "entry_ts": ts}

    limit_px = order.get("limit_px")
    stop_px = order.get("stop_px")
    fill_px: float | None = None
    fill_leg: str | None = None

    if style == "market":
        fill_px = close
        fill_leg = "market"
    elif style == "limit" and limit_px is not None:
        lp = float(limit_px)
        if act == "BUY" and low <= lp:
            fill_px = lp
            fill_leg = "limit"
        elif act == "SELL" and high >= lp:
            fill_px = lp
            fill_leg = "limit"
    elif style == "stop" and stop_px is not None:
        sp = float(stop_px)
        if act == "BUY" and high >= sp:
            fill_px = sp
            fill_leg = "stop"
        elif act == "SELL" and low <= sp:
            fill_px = sp
            fill_leg = "stop"
    elif style == "oco":
        # Same bar: if both touch → pessimistic invalidate-cancel (no free lunch)
        hit_lim = False
        hit_stop = False
        if limit_px is not None:
            lp = float(limit_px)
            hit_lim = (act == "BUY" and low <= lp) or (act == "SELL" and high >= lp)
        if stop_px is not None:
            sp = float(stop_px)
            hit_stop = (act == "BUY" and high >= sp) or (act == "SELL" and low <= sp)
        if hit_lim and hit_stop:
            return {"status": "cancelled", "reason": "oco_conflict", "entry": None, "entry_ts": ts}
        if hit_lim and limit_px is not None:
            fill_px = float(limit_px)
            fill_leg = "limit"
        elif hit_stop and stop_px is not None:
            fill_px = float(stop_px)
            fill_leg = "stop"

    if fill_px is not None and fill_px > 0:
        pos = _filled_position_from_order(order, entry=fill_px, entry_ts=ts)
        pos["fill_leg"] = fill_leg
        return {
            "status": "filled",
            "reason": fill_leg or "fill",
            "entry": fill_px,
            "entry_ts": ts,
            "position": pos,
        }
    return {"status": "pending", "reason": "wait", "entry": None, "entry_ts": None}


def cancel_pending_orders_for_symbol(
    project_root: str | Path,
    *,
    symbol: str,
    market: str,
    reason: str = "cancel",
    append_cancel_row: Any = None,
    only_actions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Cancel pending orders for one symbol/market. Returns {cancelled, events, orders_left}."""
    sym = (symbol or "").strip().upper()
    kind = normalize_market(market)
    reason_s = str(reason or "cancel")
    allow = None
    if only_actions:
        allow = {str(a).upper() for a in only_actions}

    orders = load_pending_orders(project_root)
    events: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    cancelled_n = 0
    for order in orders:
        if str(order.get("symbol") or "").upper() != sym or normalize_market(order.get("market")) != kind:
            kept.append(order)
            continue
        if str(order.get("status") or "pending") != "pending":
            continue
        act = str(order.get("action") or "").upper()
        if allow is not None and act not in allow:
            kept.append(order)
            continue
        cancelled_n += 1
        events.append(
            {
                "kind": "skip",
                "message": (
                    f"{sym}{' fut' if kind == 'futures' else ''} "
                    f"pending {order.get('entry_style')} {act} отменён ({reason_s})"
                ),
            }
        )
        if append_cancel_row is not None:
            place_ts = int(order.get("ts") or order.get("signal_ts") or 0)
            append_cancel_row(
                {
                    "ts": place_ts,
                    "exit_ts": place_ts,
                    "symbol": sym,
                    "interval": order.get("interval"),
                    "market": kind,
                    "action": act,
                    "entry": float(order.get("signal_px") or 0.0),
                    "exit": float(order.get("signal_px") or 0.0),
                    "ret": 0.0,
                    "edge": 0.0,
                    "correct": False,
                    "horizon": order.get("horizon"),
                    "features": order.get("features") or {},
                    "feature_vec": order.get("feature_vec") or [],
                    "policy": order.get("source") or "live",
                    "live": True,
                    "exit_reason": f"cancel_{reason_s}",
                    "entry_style": order.get("entry_style"),
                    "pending_cancelled": True,
                    "mfe_pct": 0.0,
                    "mae_pct": 0.0,
                    "entry_timing_score": -1.0,
                }
            )
    if cancelled_n:
        save_pending_orders(project_root, kept)
    return {"cancelled": cancelled_n, "events": events, "orders_left": len(kept)}


def process_pending_orders(
    project_root: str | Path,
    *,
    symbol: str,
    market: str,
    candles_exec: Sequence[dict[str, Any]],
    append_cancel_row: Any = None,
) -> dict[str, Any]:
    """Advance pendings for symbol/market on exec candles.

    On fill, remaining pendings for the same symbol/market are cancelled
    (``sibling_fill``) — bracket / multi-leg safety.

    ``append_cancel_row(row)`` optional callback to log cancelled attempts for learning.
    Returns {events, filled_positions, cancelled, pending_left}.
    """
    sym = (symbol or "").strip().upper()
    kind = normalize_market(market)
    orders = load_pending_orders(project_root)
    events: list[dict[str, Any]] = []
    filled: list[dict[str, Any]] = []
    cancelled_n = 0
    others: list[dict[str, Any]] = []
    still: list[dict[str, Any]] = []
    changed = False

    for order in orders:
        if str(order.get("symbol") or "").upper() != sym or normalize_market(order.get("market")) != kind:
            others.append(order)
            continue
        if str(order.get("status") or "pending") != "pending":
            continue
        place_ts = int(order.get("ts") or order.get("signal_ts") or 0)
        idx = find_entry_index(candles_exec, place_ts)
        if idx < 0 or not candles_exec:
            still.append(order)
            continue
        last_seen = int(order.get("last_seen_ts") or place_ts)
        start = None
        for i in range(idx, len(candles_exec)):
            if int(candles_exec[i].get("open_time") or 0) > last_seen:
                start = i
                break
        if start is None:
            still.append(order)
            continue

        done = False
        for i in range(start, len(candles_exec)):
            bar = candles_exec[i]
            bars_since = i - idx
            result = simulate_pending_on_bar(order, bar, bars_since_place=bars_since)
            order["last_seen_ts"] = int(bar.get("open_time") or 0)
            changed = True
            st = result["status"]
            if st == "filled":
                pos = result.get("position")
                if pos:
                    filled.append(pos)
                events.append(
                    {
                        "kind": "paper",
                        "message": (
                            f"{sym}{' fut' if kind == 'futures' else ''} "
                            f"вход {order.get('entry_style')}→{result.get('reason')} "
                            f"{order.get('action')} @ {float(result['entry']):.4f} "
                            f"(pending {order.get('id')})"
                        ),
                    }
                )
                done = True
                break
            if st == "cancelled":
                cancelled_n += 1
                reason = str(result.get("reason") or "cancel")
                events.append(
                    {
                        "kind": "skip",
                        "message": (
                            f"{sym}{' fut' if kind == 'futures' else ''} "
                            f"pending {order.get('entry_style')} {order.get('action')} "
                            f"отменён ({reason})"
                        ),
                    }
                )
                if append_cancel_row is not None:
                    append_cancel_row(
                        {
                            "ts": place_ts,
                            "exit_ts": int(bar.get("open_time") or 0),
                            "symbol": sym,
                            "interval": order.get("interval"),
                            "market": kind,
                            "action": order.get("action"),
                            "entry": float(order.get("signal_px") or 0.0),
                            "exit": float(order.get("signal_px") or 0.0),
                            "ret": 0.0,
                            "edge": 0.0,
                            "correct": False,
                            "horizon": order.get("horizon"),
                            "features": order.get("features") or {},
                            "feature_vec": order.get("feature_vec") or [],
                            "policy": order.get("source") or "live",
                            "live": True,
                            "exit_reason": f"cancel_{reason}",
                            "entry_style": order.get("entry_style"),
                            "pending_cancelled": True,
                            "mfe_pct": 0.0,
                            "mae_pct": 0.0,
                            "entry_timing_score": -1.0,
                        }
                    )
                done = True
                break
        if not done:
            still.append(order)

    # Bracket safety: one fill cancels other legs / sibling pendings on this pair.
    if filled and still:
        for order in list(still):
            cancelled_n += 1
            events.append(
                {
                    "kind": "skip",
                    "message": (
                        f"{sym}{' fut' if kind == 'futures' else ''} "
                        f"pending {order.get('entry_style')} {order.get('action')} "
                        f"отменён (sibling_fill)"
                    ),
                }
            )
            if append_cancel_row is not None:
                place_ts = int(order.get("ts") or order.get("signal_ts") or 0)
                append_cancel_row(
                    {
                        "ts": place_ts,
                        "exit_ts": place_ts,
                        "symbol": sym,
                        "interval": order.get("interval"),
                        "market": kind,
                        "action": order.get("action"),
                        "entry": float(order.get("signal_px") or 0.0),
                        "exit": float(order.get("signal_px") or 0.0),
                        "ret": 0.0,
                        "edge": 0.0,
                        "correct": False,
                        "horizon": order.get("horizon"),
                        "features": order.get("features") or {},
                        "feature_vec": order.get("feature_vec") or [],
                        "policy": order.get("source") or "live",
                        "live": True,
                        "exit_reason": "cancel_sibling_fill",
                        "entry_style": order.get("entry_style"),
                        "pending_cancelled": True,
                        "mfe_pct": 0.0,
                        "mae_pct": 0.0,
                        "entry_timing_score": -1.0,
                    }
                )
        still = []
        changed = True

    final = others + still
    if changed or filled or cancelled_n:
        save_pending_orders(project_root, final)

    return {
        "events": events,
        "filled_positions": filled,
        "cancelled": cancelled_n,
        "pending_left": len(still),
    }
