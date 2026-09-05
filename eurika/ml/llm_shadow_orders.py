"""LLM shadow pending book: limit / stop / OCO, isolated from MLP paper.

Uses ``paper_orders.simulate_pending_on_bar`` for 1m fill/cancel logic, but stores
orders in ``llm_shadow_pending.json`` so live/explore pending never mix.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.exec_tf import find_entry_index, main_horizon_to_exec
from eurika.ml.market_store import load_candles, ml_root, normalize_market
from eurika.ml.paper_orders import (
    DEFAULT_INVALIDATE_PCT,
    DEFAULT_LIMIT_OFFSET_PCT,
    DEFAULT_STOP_OFFSET_PCT,
    ENTRY_STYLES,
    build_pending_order,
    simulate_pending_on_bar,
)
from eurika.ml.paper_portfolio import propose_size, recompute_margin_used


def normalize_level_frac(raw: object, *, default: float | None = None) -> float | None:
    """TP/SL/trail as a fraction of price.

    Accepts protocol shares (``0.01`` = 1%) and common LLM mistakes
    (``1`` / ``1.0`` meaning 1 percent). Values ``> 0.2`` are treated as
    percent points and divided by 100, then clamped to ``[0, 0.2]``.
    """
    if isinstance(raw, bool) or raw is None or raw == "":
        return default
    if not isinstance(raw, (int, float, str)):
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    if val > 0.2:
        val = val / 100.0
    return max(0.0, min(0.2, val))


# Agent / LLM-shadow book defaults (not MLP exam). Soft floor bumps TP if R:R is worse.
DEFAULT_AGENT_TP_PCT = 0.024
DEFAULT_AGENT_SL_PCT = 0.008
DEFAULT_AGENT_TRAIL_PCT = 0.008
MIN_AGENT_TP_SL_RATIO = 1.5


def enforce_tp_sl_ratio(
    tp_pct: float,
    sl_pct: float,
    *,
    min_ratio: float = MIN_AGENT_TP_SL_RATIO,
) -> tuple[float, float]:
    """Ensure TP/SL ≥ ``min_ratio`` by raising TP when needed."""
    tp = max(0.0, float(tp_pct or 0.0))
    sl = max(0.0, float(sl_pct or 0.0))
    if sl <= 0:
        return tp, sl
    need = sl * max(1.0, float(min_ratio))
    if tp < need:
        tp = need
    return tp, sl


def llm_shadow_pending_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_shadow_pending.json"


def load_shadow_pending(project_root: str | Path) -> list[dict[str, Any]]:
    path = llm_shadow_pending_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("orders") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and str(r.get("status") or "pending") == "pending"]


def save_shadow_pending(project_root: str | Path, orders: list[dict[str, Any]]) -> Path:
    path = llm_shadow_pending_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = [r for r in orders if isinstance(r, dict) and str(r.get("status") or "pending") == "pending"]
    path.write_text(json.dumps({"orders": pending}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _entry_style(row: Mapping[str, Any]) -> str:
    style = str(row.get("entry_style") or row.get("style") or "market").strip().lower()
    return style if style in ENTRY_STYLES else "market"


def format_shadow_pending_for_prompt(project_root: str | Path, *, limit: int = 12) -> str:
    orders = load_shadow_pending(project_root)
    if not orders:
        return "LLM SHADOW PENDING\n  none"
    lines = ["LLM SHADOW PENDING"]
    for order in orders[:limit]:
        style = str(order.get("entry_style") or "market")
        lim = order.get("limit_px")
        stop = order.get("stop_px")
        inv = order.get("invalidate_px")
        lines.append(
            "  "
            + f"{order.get('symbol')} {order.get('market')} {order.get('action')} "
            + f"style={style} "
            + (f"limit={float(lim):.4f} " if isinstance(lim, (int, float)) else "")
            + (f"stop={float(stop):.4f} " if isinstance(stop, (int, float)) else "")
            + (f"inv={float(inv):.4f} " if isinstance(inv, (int, float)) else "")
            + f"tp={float(order.get('tp_pct') or 0.0):.4f} "
            + f"sl={float(order.get('sl_pct') or 0.0):.4f} "
            + f"id={order.get('id')}"
        )
    return "\n".join(lines)


def pending_symbols(project_root: str | Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for order in load_shadow_pending(project_root):
        sym = str(order.get("symbol") or "").upper()
        if sym:
            out.add((sym, normalize_market(order.get("market"))))
    return out


def margin_used_with_pending(
    opens: Sequence[Mapping[str, Any]],
    pending: Sequence[Mapping[str, Any]] | None = None,
) -> float:
    return recompute_margin_used(list(opens) + list(pending or []))


def filled_pending_to_shadow_open(order: Mapping[str, Any], *, entry: float, entry_ts: int) -> dict[str, Any]:
    trail = float(order.get("trail_pct") or 0.0)
    return {
        "kind": "llm_shadow",
        "symbol": str(order.get("symbol") or "").upper(),
        "market": normalize_market(order.get("market")),
        "action": str(order.get("action") or "").upper(),
        "entry": float(entry),
        "entry_ts": int(entry_ts),
        "interval": str(order.get("interval") or "15m"),
        "exec_interval": str(order.get("exec_interval") or "1m"),
        "horizon": int(order.get("horizon") or 4),
        "horizon_exec": int(order.get("horizon_exec") or 4),
        "tp_pct": float(order.get("tp_pct") or DEFAULT_AGENT_TP_PCT),
        "sl_pct": float(order.get("sl_pct") or DEFAULT_AGENT_SL_PCT),
        "trail_pct": trail if trail > 0 else None,
        "trail_extreme": float(entry) if trail > 0 else None,
        "margin_usdt": float(order.get("margin_usdt") or 0.0),
        "notional_usdt": float(order.get("notional_usdt") or order.get("margin_usdt") or 0.0),
        "leverage": float(order.get("leverage") or 1.0),
        "llm_row_ts": int(order.get("llm_row_ts") or order.get("signal_ts") or entry_ts),
        "teacher_source": str(order.get("teacher_source") or "cursor"),
        "when": str(order.get("when") or ""),
        "entry_style": str(order.get("entry_style") or "market"),
        "fill_leg": order.get("fill_leg"),
        "pending_id": order.get("id"),
        "source": "llm_shadow",
    }


def build_shadow_pending_order(
    project_root: str | Path,
    portfolio: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    now_ms: int | None = None,
) -> dict[str, Any] | None:
    """Build a cancelable LLM pending (limit/stop/oco) from a shadow_action row."""
    symbol = str(row.get("symbol") or "").upper()
    side = str(row.get("side") or row.get("action_side") or "").upper()
    if side not in {"BUY", "SELL"}:
        # ``action`` is place/open; side lives in ``side``.
        side = str(row.get("order_side") or "").upper()
    if not symbol or side not in {"BUY", "SELL"}:
        return None
    market = normalize_market(row.get("market"))
    style = _entry_style(row)
    if style == "market":
        return None
    interval = str(row.get("interval") or "").strip() or "15m"
    candles = load_candles(project_root, symbol, interval, market=market)
    candles_exec = load_candles(project_root, symbol, "1m", market=market)
    if not candles and not candles_exec:
        return None
    try:
        signal_bar = candles_exec[-1] if candles_exec else candles[-1]
        signal_px = float(row.get("signal_px") or signal_bar.get("close") or 0.0)
        signal_ts = int(
            row.get("signal_ts")
            or row.get("ts")
            or signal_bar.get("open_time")
            or (now_ms or time.time() * 1000)
        )
    except (TypeError, ValueError):
        return None
    if signal_px <= 0 or signal_ts <= 0:
        return None
    size = propose_size(portfolio, market=market, action=side, soft_entry=True)
    if not size.get("ok"):
        return None
    horizon = int(row.get("horizon") or 4)
    horizon_exec = max(1, main_horizon_to_exec(horizon, interval, "1m"))
    lim_off = float(row.get("limit_offset_pct") or DEFAULT_LIMIT_OFFSET_PCT)
    stop_off = float(row.get("stop_offset_pct") or DEFAULT_STOP_OFFSET_PCT)
    inv_pct = float(row.get("invalidate_pct") or DEFAULT_INVALIDATE_PCT)
    tp_pct, sl_pct = enforce_tp_sl_ratio(
        float(normalize_level_frac(row.get("tp_pct"), default=DEFAULT_AGENT_TP_PCT) or DEFAULT_AGENT_TP_PCT),
        float(normalize_level_frac(row.get("sl_pct"), default=DEFAULT_AGENT_SL_PCT) or DEFAULT_AGENT_SL_PCT),
    )
    order = build_pending_order(
        symbol=symbol,
        market=market,
        action=side,
        signal_px=signal_px,
        signal_ts=signal_ts,
        interval=interval,
        entry_style=style,
        horizon=horizon,
        horizon_exec=horizon_exec,
        exec_interval="1m",
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        trail_pct=float(
            normalize_level_frac(row.get("trail_pct"), default=DEFAULT_AGENT_TRAIL_PCT)
            or DEFAULT_AGENT_TRAIL_PCT
        ),
        invalidate_pct=float(
            normalize_level_frac(row.get("invalidate_pct"), default=inv_pct) or inv_pct
        ),
        limit_offset_pct=lim_off,
        stop_offset_pct=stop_off,
        source="llm_shadow",
        shadow=False,
    )
    # Absolute prices from the LLM override offset-derived levels.
    for key in ("limit_px", "stop_px", "invalidate_px"):
        if isinstance(row.get(key), (int, float)) and float(row[key]) > 0:
            order[key] = float(row[key])
    if isinstance(row.get("pending_horizon_exec"), (int, float)):
        order["pending_horizon_exec"] = max(1, int(row["pending_horizon_exec"]))
    order["margin_usdt"] = float(size.get("margin_usdt") or 0.0)
    order["notional_usdt"] = float(size.get("notional_usdt") or size.get("margin_usdt") or 0.0)
    order["leverage"] = float(row.get("leverage") or size.get("leverage") or 1.0)
    order["llm_shadow"] = True
    order["llm_row_ts"] = int(row.get("llm_row_ts") or row.get("ts") or signal_ts)
    order["teacher_source"] = str(row.get("source") or "cursor")
    order["when"] = str(row.get("when") or "")
    return order


def update_shadow_pending_order(order: dict[str, Any], row: Mapping[str, Any]) -> None:
    for key in ("tp_pct", "sl_pct", "trail_pct", "invalidate_pct"):
        frac = normalize_level_frac(row.get(key))
        if frac is not None:
            order[key] = frac
    tp_u, sl_u = enforce_tp_sl_ratio(
        float(order.get("tp_pct") or DEFAULT_AGENT_TP_PCT),
        float(order.get("sl_pct") or DEFAULT_AGENT_SL_PCT),
    )
    order["tp_pct"] = tp_u
    order["sl_pct"] = sl_u
    for key in ("limit_px", "stop_px", "invalidate_px"):
        if isinstance(row.get(key), (int, float)) and float(row[key]) > 0:
            order[key] = float(row[key])
    if isinstance(row.get("pending_horizon_exec"), (int, float)):
        order["pending_horizon_exec"] = max(1, int(row["pending_horizon_exec"]))
    style = str(row.get("entry_style") or row.get("style") or "").strip().lower()
    if style in ENTRY_STYLES and style != "market":
        order["entry_style"] = style


def process_llm_shadow_pendings(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Advance all LLM shadow pendings on 1m candles; return fills for open book."""
    _ = now_ms
    orders = load_shadow_pending(project_root)
    if not orders:
        return {"filled": 0, "cancelled": 0, "pending_left": 0, "positions": [], "events": []}

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for order in orders:
        key = (str(order.get("symbol") or "").upper(), normalize_market(order.get("market")))
        by_key.setdefault(key, []).append(order)

    still: list[dict[str, Any]] = []
    filled_positions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    cancelled_n = 0

    for (sym, kind), group in by_key.items():
        candles_exec = load_candles(project_root, sym, "1m", market=kind)
        filled_here = False
        for order in group:
            if filled_here:
                cancelled_n += 1
                events.append(
                    {
                        "kind": "skip",
                        "message": (
                            f"{sym}{' fut' if kind == 'futures' else ''} "
                            f"LLM pending {order.get('entry_style')} {order.get('action')} "
                            "отменён (sibling_fill)"
                        ),
                    }
                )
                continue
            place_ts = int(order.get("ts") or order.get("signal_ts") or 0)
            if not candles_exec:
                still.append(order)
                continue
            idx = find_entry_index(candles_exec, place_ts)
            if idx < 0:
                if place_ts < int(candles_exec[0].get("open_time") or 0):
                    cancelled_n += 1
                    events.append(
                        {
                            "kind": "skip",
                            "message": (
                                f"{sym}{' fut' if kind == 'futures' else ''} "
                                f"LLM pending {order.get('entry_style')} {order.get('action')} "
                                "отменён (stale)"
                            ),
                        }
                    )
                    continue
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
                result = simulate_pending_on_bar(order, bar, bars_since_place=i - idx)
                order["last_seen_ts"] = int(bar.get("open_time") or 0)
                st = result["status"]
                if st == "filled":
                    entry = float(result["entry"] or 0.0)
                    entry_ts = int(result["entry_ts"] or 0)
                    order["fill_leg"] = result.get("reason")
                    pos = filled_pending_to_shadow_open(order, entry=entry, entry_ts=entry_ts)
                    filled_positions.append(pos)
                    filled_here = True
                    events.append(
                        {
                            "kind": "paper",
                            "message": (
                                f"{sym}{' fut' if kind == 'futures' else ''} "
                                f"LLM {order.get('entry_style')} {order.get('action')} "
                                f"fill @{entry:.4f}"
                            ),
                        }
                    )
                    done = True
                    break
                if st == "cancelled":
                    cancelled_n += 1
                    events.append(
                        {
                            "kind": "skip",
                            "message": (
                                f"{sym}{' fut' if kind == 'futures' else ''} "
                                f"LLM pending {order.get('entry_style')} {order.get('action')} "
                                f"отменён ({result.get('reason') or 'cancel'})"
                            ),
                        }
                    )
                    done = True
                    break
            if not done:
                still.append(order)

    save_shadow_pending(project_root, still)
    return {
        "filled": len(filled_positions),
        "cancelled": cancelled_n,
        "pending_left": len(still),
        "positions": filled_positions,
        "events": events,
    }
