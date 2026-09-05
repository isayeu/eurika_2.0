"""Thesis-driven overnight paper book (isolated from MLP exam).

Separate portfolio, pending, opens, trades, and verbose journal under
``.eurika/ml/assistant_*``. No live Binance orders — 1m simulation only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.exec_tf import find_entry_index, main_horizon_to_exec, simulate_exec_exit
from eurika.ml.features import features_dict
from eurika.ml.llm_shadow_orders import (
    DEFAULT_AGENT_SL_PCT as DEFAULT_ASSISTANT_SL_PCT,
    DEFAULT_AGENT_TP_PCT as DEFAULT_ASSISTANT_TP_PCT,
    DEFAULT_AGENT_TRAIL_PCT as DEFAULT_ASSISTANT_TRAIL_PCT,
    MIN_AGENT_TP_SL_RATIO as MIN_ASSISTANT_TP_SL_RATIO,
    enforce_tp_sl_ratio,
)
from eurika.ml.market_store import load_candles, ml_root, normalize_market, sync_klines
from eurika.ml.paper_orders import (
    ENTRY_STYLES,
    build_pending_order,
    simulate_pending_on_bar,
)
from eurika.ml.paper_portfolio import DEFAULT_START_EQUITY_USDT, propose_size
from eurika.ml.paper_trader import fee_for_market, label_trade
from eurika.ml.universe import load_ticker_lists

ASSISTANT_SOURCE = "assistant_night"
DEFAULT_INTERVAL = "15m"
DEFAULT_HORIZON_MAIN = 96  # 96×15m ≈ 24h exec window on 1m
DEFAULT_PENDING_HORIZON_EXEC = 720  # 12h on 1m before pending expires
SYNC_1M_LIMIT = 720  # match pending horizon so fills are not marked stale overnight
MAX_THESES = 6
MAX_OPENS = 3
SCAN_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT")
# After SL — block same (symbol, market, side) so LLM cannot «restore» the same long.
# 120×1m ≈ 2h ≈ ~8 portfolio cycles; stops ARB-style revenge loops.
DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M = 120
# Same limit/stop level: at most N places inside the rolling window.
MAX_SAME_LIMIT_PLACES = 2
SAME_LIMIT_WINDOW_MS = 4 * 60 * 60 * 1000  # 4h
_MS_PER_1M_BAR = 60_000
# Agent book levels (not MLP exam): DEFAULT_ASSISTANT_* from llm_shadow_orders (~3:1).
DEFAULT_STRUCTURE_ARM_MFE_PCT = 0.012  # was 0.004 — no skim on noise MFE
DEFAULT_STRUCTURE_GIVEBACK_FRAC = 0.45
_ACTION_ALIASES = {
    "open": "open",
    "place": "place",
    "add": "add",
    "close": "close",
    "cancel": "cancel",
    "hold": "hold",
    "update": "update",
    "reprice": "update",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ts_iso(ms: int | None = None) -> str:
    t = int(ms or _now_ms()) / 1000.0
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def assistant_portfolio_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_portfolio.json"


def assistant_open_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_open.json"


def assistant_pending_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_pending.json"


def assistant_theses_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_theses.json"


def assistant_journal_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_journal.jsonl"


def assistant_trades_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_trades.jsonl"


def assistant_memory_path(root: str | Path) -> Path:
    return ml_root(root) / "assistant_memory.json"


def assistant_reentry_cooldown_path(root: str | Path) -> Path:
    """Separate from MLP exam ``reentry_cooldown.json``."""
    return ml_root(root) / "assistant_reentry_cooldown.json"


def _cooldown_key(symbol: str, market: str, side: str) -> str:
    return f"{str(symbol).upper()}|{normalize_market(market)}|{str(side).upper()}"


def _limit_key(symbol: str, market: str, side: str, level_px: float) -> str:
    return f"{_cooldown_key(symbol, market, side)}|{round(float(level_px), 6)}"


def _entry_level_px(row: Mapping[str, Any]) -> float | None:
    for key in ("limit_px", "stop_px"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            px = float(raw)
        except (TypeError, ValueError):
            continue
        if px > 0:
            return px
    return None


def enforce_assistant_tp_sl(
    tp_pct: float,
    sl_pct: float,
    *,
    min_ratio: float = MIN_ASSISTANT_TP_SL_RATIO,
) -> tuple[float, float]:
    """Ensure TP/SL risk:reward is at least ``min_ratio`` (bump TP if needed)."""
    return enforce_tp_sl_ratio(tp_pct, sl_pct, min_ratio=min_ratio)


def load_assistant_reentry_state(root: str | Path) -> dict[str, Any]:
    data = _read_json(assistant_reentry_cooldown_path(root), {})
    if not isinstance(data, dict):
        return {"entries": {}, "recent_limits": {}}
    raw_entries = data.get("entries")
    raw_recent = data.get("recent_limits")
    entries: dict[str, Any] = raw_entries if isinstance(raw_entries, dict) else {}
    recent: dict[str, Any] = raw_recent if isinstance(raw_recent, dict) else {}
    return {"entries": dict(entries), "recent_limits": dict(recent)}


def save_assistant_reentry_state(root: str | Path, state: Mapping[str, Any]) -> Path:
    path = assistant_reentry_cooldown_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "entries": dict(state.get("entries") or {}),
        "recent_limits": dict(state.get("recent_limits") or {}),
    }
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_assistant_reentry_cooldowns(
    root: str | Path, *, now_ts_ms: int | None = None
) -> dict[str, dict[str, Any]]:
    state = load_assistant_reentry_state(root)
    now = int(now_ts_ms) if now_ts_ms is not None else None
    out: dict[str, dict[str, Any]] = {}
    for key, row in state["entries"].items():
        if not isinstance(row, dict):
            continue
        until = int(row.get("until_ts") or 0)
        if now is not None and until <= now:
            continue
        out[str(key)] = row
    return out


def register_assistant_reentry_cooldown(
    root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    exit_ts_ms: int,
    bars_1m: int = DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M,
    exit_reason: str = "sl",
) -> dict[str, Any]:
    """Arm same-side reentry block after SL (holistic / assistant book)."""
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        return {}
    bars = max(1, int(bars_1m))
    until = int(exit_ts_ms) + bars * _MS_PER_1M_BAR
    state = load_assistant_reentry_state(root)
    entries = {
        k: v
        for k, v in state["entries"].items()
        if isinstance(v, dict) and int(v.get("until_ts") or 0) > int(exit_ts_ms)
    }
    row = {
        "symbol": str(symbol).upper(),
        "market": normalize_market(market),
        "side": side_u,
        "until_ts": until,
        "exit_ts": int(exit_ts_ms),
        "bars_1m": bars,
        "exit_reason": str(exit_reason or "sl"),
    }
    entries[_cooldown_key(symbol, market, side_u)] = row
    state["entries"] = entries
    save_assistant_reentry_state(root, state)
    return row


def assistant_reentry_cooldown_active(
    root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    now_ts_ms: int,
) -> dict[str, Any] | None:
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        return None
    row = load_assistant_reentry_cooldowns(root, now_ts_ms=int(now_ts_ms)).get(
        _cooldown_key(symbol, market, side_u)
    )
    if not row:
        return None
    if int(row.get("until_ts") or 0) <= int(now_ts_ms):
        return None
    return row


def note_assistant_limit_place(
    root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    level_px: float,
    now_ts_ms: int | None = None,
) -> dict[str, Any]:
    """Record a place/open at ``level_px`` for the same-limit cap."""
    now = int(now_ts_ms if now_ts_ms is not None else _now_ms())
    state = load_assistant_reentry_state(root)
    recent = dict(state.get("recent_limits") or {})
    # drop expired fingerprints
    kept: dict[str, Any] = {}
    for key, row in recent.items():
        if not isinstance(row, dict):
            continue
        last = int(row.get("last_ts") or row.get("first_ts") or 0)
        if now - last <= SAME_LIMIT_WINDOW_MS:
            kept[str(key)] = row
    key = _limit_key(symbol, market, side, level_px)
    prev = kept.get(key) if isinstance(kept.get(key), dict) else None
    if prev and now - int(prev.get("first_ts") or 0) <= SAME_LIMIT_WINDOW_MS:
        row = {
            "symbol": str(symbol).upper(),
            "market": normalize_market(market),
            "side": str(side).upper(),
            "limit_px": float(level_px),
            "count": int(prev.get("count") or 0) + 1,
            "first_ts": int(prev.get("first_ts") or now),
            "last_ts": now,
        }
    else:
        row = {
            "symbol": str(symbol).upper(),
            "market": normalize_market(market),
            "side": str(side).upper(),
            "limit_px": float(level_px),
            "count": 1,
            "first_ts": now,
            "last_ts": now,
        }
    kept[key] = row
    state["recent_limits"] = kept
    # keep live cooldowns too
    state["entries"] = load_assistant_reentry_cooldowns(root, now_ts_ms=now)
    save_assistant_reentry_state(root, state)
    return row


def same_limit_place_count(
    root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    level_px: float,
    now_ts_ms: int | None = None,
) -> int:
    now = int(now_ts_ms if now_ts_ms is not None else _now_ms())
    state = load_assistant_reentry_state(root)
    row = state["recent_limits"].get(_limit_key(symbol, market, side, level_px))
    if not isinstance(row, dict):
        return 0
    first = int(row.get("first_ts") or 0)
    if now - first > SAME_LIMIT_WINDOW_MS:
        return 0
    return int(row.get("count") or 0)


def assistant_entry_block_reason(
    root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    level_px: float | None = None,
    now_ts_ms: int | None = None,
) -> str | None:
    """Return human reason if place/open must be refused, else None."""
    now = int(now_ts_ms if now_ts_ms is not None else _now_ms())
    cd = assistant_reentry_cooldown_active(
        root, symbol=symbol, market=market, side=side, now_ts_ms=now
    )
    if cd:
        left_m = max(0, (int(cd.get("until_ts") or 0) - now) // 60_000)
        why = str(cd.get("exit_reason") or "sl")
        return f"cooldown после {why} ещё ~{left_m}м"
    if level_px is not None and float(level_px) > 0:
        n = same_limit_place_count(
            root,
            symbol=symbol,
            market=market,
            side=side,
            level_px=float(level_px),
            now_ts_ms=now,
        )
        if n >= MAX_SAME_LIMIT_PLACES:
            return (
                f"тот же уровень {float(level_px):.6g} уже place×{n} "
                f"за {SAME_LIMIT_WINDOW_MS // 3_600_000}ч (лимит {MAX_SAME_LIMIT_PLACES})"
            )
    return None


def format_assistant_cooldowns_for_prompt(root: str | Path, *, now_ts_ms: int | None = None) -> str:
    now = int(now_ts_ms if now_ts_ms is not None else _now_ms())
    lines = ["REENTRY GUARDS (скелет; place/open игнорируются если сработало)"]
    cds = load_assistant_reentry_cooldowns(root, now_ts_ms=now)
    if not cds:
        lines.append("  cooldown: none")
    else:
        for row in cds.values():
            left_m = max(0, (int(row.get("until_ts") or 0) - now) // 60_000)
            lines.append(
                f"  cooldown {row.get('symbol')} {row.get('side')} "
                f"after {row.get('exit_reason')} ~{left_m}м left"
            )
    state = load_assistant_reentry_state(root)
    caps: list[str] = []
    for row in state.get("recent_limits", {}).values():
        if not isinstance(row, dict):
            continue
        first = int(row.get("first_ts") or 0)
        if now - first > SAME_LIMIT_WINDOW_MS:
            continue
        n = int(row.get("count") or 0)
        if n <= 0:
            continue
        caps.append(
            f"  limit-cap {row.get('symbol')} {row.get('side')} "
            f"@{float(row.get('limit_px') or 0):.6g} place×{n}/{MAX_SAME_LIMIT_PLACES}"
        )
    if caps:
        lines.extend(caps)
    else:
        lines.append("  same-limit caps: none")
    return "\n".join(lines)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_portfolio() -> dict[str, Any]:
    eq = float(DEFAULT_START_EQUITY_USDT)
    now = _now_ms()
    return {
        "version": 1,
        "start_equity_usdt": eq,
        "equity_usdt": eq,
        "margin_used_usdt": 0.0,
        "realized_pnl_usdt": 0.0,
        "risk_frac": 0.01,
        "max_margin_frac": 0.20,
        "max_opens": MAX_OPENS,
        "note": "assistant night thesis book; not MLP exam",
        "created_ms": now,
        "updated_ms": now,
    }


def load_portfolio(root: str | Path) -> dict[str, Any]:
    data = _read_json(assistant_portfolio_path(root), None)
    if not isinstance(data, dict):
        return default_portfolio()
    out = default_portfolio()
    out.update({k: data[k] for k in data if k in out or k in ("version", "note", "created_ms")})
    return out


def save_portfolio(root: str | Path, port: Mapping[str, Any]) -> None:
    blob = dict(port)
    blob["updated_ms"] = _now_ms()
    _write_json(assistant_portfolio_path(root), blob)


def ensure_portfolio(root: str | Path) -> dict[str, Any]:
    path = assistant_portfolio_path(root)
    if not path.is_file():
        port = default_portfolio()
        save_portfolio(root, port)
        return port
    return load_portfolio(root)


def load_opens(root: str | Path) -> list[dict[str, Any]]:
    data = _read_json(assistant_open_path(root), {"positions": []})
    rows = data.get("positions") if isinstance(data, dict) else data
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save_opens(root: str | Path, positions: Sequence[dict[str, Any]]) -> None:
    _write_json(assistant_open_path(root), {"positions": list(positions)})


def load_pending(root: str | Path) -> list[dict[str, Any]]:
    data = _read_json(assistant_pending_path(root), {"orders": []})
    rows = data.get("orders") if isinstance(data, dict) else data
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save_pending(root: str | Path, orders: Sequence[dict[str, Any]]) -> None:
    _write_json(assistant_pending_path(root), {"orders": list(orders)})


def load_theses(root: str | Path) -> list[dict[str, Any]]:
    data = _read_json(assistant_theses_path(root), {"theses": []})
    rows = data.get("theses") if isinstance(data, dict) else data
    return [dict(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save_theses(root: str | Path, theses: Sequence[dict[str, Any]]) -> None:
    _write_json(assistant_theses_path(root), {"theses": list(theses)})


def append_journal(root: str | Path, *, kind: str, text: str, extra: Mapping[str, Any] | None = None) -> None:
    row: dict[str, Any] = {"ts": _now_ms(), "ts_iso": _ts_iso(), "kind": kind, "text": text}
    if extra:
        row.update(dict(extra))
    path = assistant_journal_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(text)
    sys.stdout.flush()


def append_trade(root: str | Path, row: Mapping[str, Any]) -> None:
    path = assistant_trades_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def load_memory(root: str | Path) -> dict[str, Any]:
    data = _read_json(assistant_memory_path(root), {})
    return data if isinstance(data, dict) else {}


def save_memory(root: str | Path, memory: Mapping[str, Any]) -> None:
    blob = dict(memory)
    blob["updated_ms"] = _now_ms()
    _write_json(assistant_memory_path(root), blob)


def load_journal_tail(root: str | Path, *, limit: int = 5, kind: str | None = None) -> list[dict[str, Any]]:
    path = assistant_journal_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if kind and str(row.get("kind") or "") != kind:
            continue
        rows.append(row)
    return rows[-max(1, limit) :]


def sync_assistant_symbols(
    root: str | Path,
    symbols: Sequence[str],
    *,
    limit_1m: int = SYNC_1M_LIMIT,
    limit_other: int = 200,
) -> list[str]:
    """Best-effort kline sync for assistant book symbols."""
    logs: list[str] = []
    for sym in sorted({str(s).upper() for s in symbols if s}):
        for iv, limit in (("1m", limit_1m), ("15m", limit_other), ("1h", limit_other)):
            try:
                sync_klines(root, symbol=sym, interval=iv, market="futures", limit=limit)
            except Exception as exc:
                logs.append(f"sync {sym} {iv}: {type(exc).__name__}")
    return logs


def format_assistant_book_for_prompt(root: str | Path, *, limit: int = 12) -> str:
    port = load_portfolio(root)
    opens = load_opens(root)
    pending = load_pending(root)
    eq = float(port.get("equity_usdt") or 0.0)
    start = float(port.get("start_equity_usdt") or eq)
    lines = [
        "ASSISTANT PAPER BOOK (futures sim only; not MLP exam)",
        f"  equity={eq:.2f} USDT start={start:.2f} Δ={eq-start:+.2f}",
        f"  margin_used={float(port.get('margin_used_usdt') or 0.0):.2f} "
        f"max_opens={int(port.get('max_opens') or MAX_OPENS)}",
    ]
    lines.append("OPENS")
    if not opens:
        lines.append("  none")
    else:
        for pos in opens[:limit]:
            lines.append(
                "  "
                + f"{pos.get('symbol')} {pos.get('action')} entry={float(pos.get('entry') or 0):.4f} "
                + f"tp={float(pos.get('tp_pct') or 0):.4f} sl={float(pos.get('sl_pct') or 0):.4f} "
                + f"trail={float(pos.get('trail_pct') or 0):.4f} mfe={float(pos.get('mfe_pct') or 0):+.4f} "
                + f"thesis={pos.get('thesis_id') or '-'}"
            )
    lines.append("PENDING")
    if not pending:
        lines.append("  none")
    else:
        for order in pending[:limit]:
            lines.append(
                "  "
                + f"{order.get('symbol')} {order.get('action')} style={order.get('entry_style')} "
                + f"limit={order.get('limit_px')} stop={order.get('stop_px')} "
                + f"inv={order.get('invalidate_px')} thesis={order.get('thesis_id') or '-'}"
            )
    lines.append(format_assistant_cooldowns_for_prompt(root))
    return "\n".join(lines)


def _margin_used(opens: Sequence[dict[str, Any]], pending: Sequence[dict[str, Any]]) -> float:
    total = 0.0
    for p in opens:
        total += float(p.get("margin_usdt") or 0.0)
    for o in pending:
        total += float(o.get("margin_usdt") or 0.0)
    return total


def _recent_range(candles: Sequence[dict[str, Any]], n: int = 20) -> tuple[float, float]:
    chunk = list(candles)[-max(3, n) :]
    highs = [float(b["high"]) for b in chunk if isinstance(b.get("high"), (int, float))]
    lows = [float(b["low"]) for b in chunk if isinstance(b.get("low"), (int, float))]
    if not highs or not lows:
        return 0.0, 0.0
    return min(lows), max(highs)


def propose_thesis(
    symbol: str,
    *,
    candles_15m: Sequence[dict[str, Any]],
    candles_1h: Sequence[dict[str, Any]],
    now_ms: int | None = None,
) -> dict[str, Any] | None:
    """Build one futures thesis from structure (no LLM)."""
    if len(candles_15m) < 25:
        return None
    close = float(candles_15m[-1]["close"])
    f15 = features_dict(candles_15m) or {}
    f1h = features_dict(candles_1h) or {}
    support, resist = _recent_range(candles_15m, 20)
    if support <= 0 or resist <= 0 or close <= 0:
        return None
    sma1h = float(f1h.get("sma_ratio") or 0.0)
    bb = float(f15.get("bb_pos") or 0.0)
    ret4 = float(f15.get("ret_4") or 0.0)
    vol_z = float(f15.get("vol_z") or 0.0)
    now = int(now_ms or _now_ms())
    tid = f"{symbol.lower()}-{uuid.uuid4().hex[:6]}"

    if sma1h > 0.008 and close >= support * 1.001:
        limit_px = round(support * 1.0008, 8)
        invalidate_px = round(support * 0.996, 8)
        stop_px = None
        style = "limit"
        trigger = "trend_pullback_long"
        narrative = (
            f"{symbol} fut: 1h выше SMA (sma_ratio={sma1h:+.3f}), откат к поддержке "
            f"~{support:.4g}. Лимит {limit_px:.4g}, инвалидация {invalidate_px:.4g}. "
            f"TP {DEFAULT_ASSISTANT_TP_PCT*100:.1f}% / SL {DEFAULT_ASSISTANT_SL_PCT*100:.1f}% "
            f"(R≥{MIN_ASSISTANT_TP_SL_RATIO:g}), trail после MFE, structure-exit только после "
            f"MFE≥{DEFAULT_STRUCTURE_ARM_MFE_PCT*100:.1f}%."
        )
    elif bb < -0.35 and close <= resist:
        limit_px = round(close * 0.999, 8)
        invalidate_px = round(support * 0.995, 8)
        stop_px = None
        style = "limit"
        trigger = "range_fade_long"
        narrative = (
            f"{symbol} fut: перепроданность bb_pos={bb:+.3f}, лимит у текущей "
            f"{limit_px:.4g} с узким SL. Ждём отскок к mid-range."
        )
    elif ret4 > 0.003 and close >= resist * 0.997 and vol_z > -0.5:
        stop_px = round(resist * 1.0003, 8)
        limit_px = None
        invalidate_px = round(support * 0.994, 8)
        style = "stop"
        trigger = "breakout_stop_long"
        narrative = (
            f"{symbol} fut: импульс ret_4={ret4:+.3%}, stop-entry над сопротивлением "
            f"{stop_px:.4g}. TP {DEFAULT_ASSISTANT_TP_PCT*100:.1f}% / "
            f"SL {DEFAULT_ASSISTANT_SL_PCT*100:.1f}%, trail, structure после "
            f"MFE≥{DEFAULT_STRUCTURE_ARM_MFE_PCT*100:.1f}%."
        )
    elif sma1h > -0.015 and abs(bb) < 0.85:
        # Fallback: мягкий откат к поддержке / под ценой — ночной watch без MLP-шума
        limit_px = round(min(close * 0.997, support * 1.002), 8)
        invalidate_px = round(support * 0.992, 8)
        stop_px = None
        style = "limit"
        trigger = "passive_pullback_long"
        narrative = (
            f"{symbol} fut: нейтральный/слабый режим (sma1h={sma1h:+.3f}, bb={bb:+.2f}). "
            f"Лимит {limit_px:.4g} (−0.3% от {close:.4g}), "
            f"TP {DEFAULT_ASSISTANT_TP_PCT*100:.1f}% / SL {DEFAULT_ASSISTANT_SL_PCT*100:.1f}%, "
            f"structure после MFE≥{DEFAULT_STRUCTURE_ARM_MFE_PCT*100:.1f}%."
        )
    else:
        return None

    return {
        "id": tid,
        "symbol": symbol.upper(),
        "market": "futures",
        "status": "watching",
        "side": "BUY",
        "trigger": trigger,
        "narrative": narrative,
        "entry_style": style,
        "limit_px": limit_px,
        "stop_px": stop_px,
        "invalidate_px": invalidate_px,
        "tp_pct": DEFAULT_ASSISTANT_TP_PCT,
        "sl_pct": DEFAULT_ASSISTANT_SL_PCT,
        "trail_pct": DEFAULT_ASSISTANT_TRAIL_PCT,
        "structure_arm_mfe_pct": DEFAULT_STRUCTURE_ARM_MFE_PCT,
        "structure_giveback_frac": DEFAULT_STRUCTURE_GIVEBACK_FRAC,
        "created_ms": now,
        "updated_ms": now,
    }


def seed_theses(root: str | Path, *, symbols: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Scan futures tickers and create up to MAX_THESES plans."""
    root = Path(root).resolve()
    ensure_portfolio(root)
    existing = [t for t in load_theses(root) if t.get("status") in ("watching", "pending", "open")]
    if existing:
        return load_theses(root)
    lists = load_ticker_lists(root)
    fut = lists.get("futures") or []
    want = list(symbols or SCAN_SYMBOLS)
    for sym in fut:
        if sym not in want and len(want) < MAX_THESES:
            want.append(sym)
    theses: list[dict[str, Any]] = []
    for sym in want:
        if len(theses) >= MAX_THESES:
            break
        try:
            sync_klines(root, symbol=sym, interval="15m", market="futures", limit=120)
            sync_klines(root, symbol=sym, interval="1h", market="futures", limit=80)
            sync_klines(root, symbol=sym, interval="1m", market="futures", limit=200)
        except Exception:
            continue
        c15 = load_candles(root, sym, "15m", market="futures")
        c1h = load_candles(root, sym, "1h", market="futures")
        th = propose_thesis(sym, candles_15m=c15, candles_1h=c1h)
        if th:
            theses.append(th)
    save_theses(root, theses)
    lines = [f"=== SEED {_ts_iso()} — {len(theses)} thesis ==="]
    for t in theses:
        lines.append(f"\n[{t['symbol']}] {t['trigger']}\n{t['narrative']}")
        lines.append(
            f"  style={t['entry_style']} limit={t.get('limit_px')} stop={t.get('stop_px')} "
            f"inv={t.get('invalidate_px')} TP={float(t['tp_pct'])*100:.1f}% SL={float(t['sl_pct'])*100:.1f}%"
        )
    append_journal(root, kind="seed", text="\n".join(lines), extra={"theses_n": len(theses)})
    return theses


def _thesis_to_pending(
    root: str | Path,
    thesis: Mapping[str, Any],
    portfolio: Mapping[str, Any],
) -> dict[str, Any] | None:
    sym = str(thesis.get("symbol") or "").upper()
    market = normalize_market(thesis.get("market"))
    side = str(thesis.get("side") or "BUY").upper()
    style = str(thesis.get("entry_style") or "limit").lower()
    if style not in ENTRY_STYLES:
        style = "limit"
    candles = load_candles(root, sym, DEFAULT_INTERVAL, market=market)
    candles_exec = load_candles(root, sym, "1m", market=market)
    if not candles and not candles_exec:
        return None
    bar = candles_exec[-1] if candles_exec else candles[-1]
    signal_px = float(bar.get("close") or 0.0)
    signal_ts = int(bar.get("open_time") or _now_ms())
    if signal_px <= 0:
        return None
    size = propose_size(portfolio, market=market, action=side, soft_entry=True)
    if not size.get("ok"):
        return None
    h_exec = max(1, main_horizon_to_exec(DEFAULT_HORIZON_MAIN, DEFAULT_INTERVAL, "1m"))
    tp_pct, sl_pct = enforce_assistant_tp_sl(
        float(thesis.get("tp_pct") or DEFAULT_ASSISTANT_TP_PCT),
        float(thesis.get("sl_pct") or DEFAULT_ASSISTANT_SL_PCT),
    )
    order = build_pending_order(
        symbol=sym,
        market=market,
        action=side,
        signal_px=signal_px,
        signal_ts=signal_ts,
        interval=DEFAULT_INTERVAL,
        entry_style=style,
        horizon=DEFAULT_HORIZON_MAIN,
        horizon_exec=h_exec,
        exec_interval="1m",
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        trail_pct=float(thesis.get("trail_pct") or DEFAULT_ASSISTANT_TRAIL_PCT),
        invalidate_pct=0.005,
        source=ASSISTANT_SOURCE,
    )
    order["pending_horizon_exec"] = DEFAULT_PENDING_HORIZON_EXEC
    for key in ("limit_px", "stop_px", "invalidate_px"):
        val = thesis.get(key)
        if isinstance(val, (int, float)) and float(val) > 0:
            order[key] = float(val)
    order["thesis_id"] = str(thesis.get("id") or "")
    order["margin_usdt"] = float(size.get("margin_usdt") or 0.0)
    order["notional_usdt"] = float(size.get("notional_usdt") or size.get("margin_usdt") or 0.0)
    order["leverage"] = min(2.0, float(size.get("leverage") or 1.0))
    order["assistant"] = True
    return order


def _process_pending_group(
    root: str | Path,
    symbol: str,
    market: str,
    group: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return (still_pending, filled_positions, log_lines)."""
    sym = symbol.upper()
    kind = normalize_market(market)
    candles_exec = load_candles(root, sym, "1m", market=kind)
    still: list[dict[str, Any]] = []
    filled: list[dict[str, Any]] = []
    logs: list[str] = []
    filled_here = False
    for order in group:
        if filled_here:
            logs.append(f"cancel sibling pending {order.get('id')} ({sym})")
            try:
                from eurika.ml.holistic_portfolio import release_trade_margin

                release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
            except Exception:
                pass
            continue
        place_ts = int(order.get("ts") or order.get("signal_ts") or 0)
        idx = find_entry_index(candles_exec, place_ts)
        if idx < 0 or not candles_exec:
            if candles_exec and place_ts < int(candles_exec[0].get("open_time") or 0):
                logs.append(f"pending stale {order.get('id')} {sym}")
                try:
                    from eurika.ml.holistic_portfolio import release_trade_margin

                    release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
                except Exception:
                    pass
                continue
            still.append(order)
            continue
        last_seen = int(order.get("last_seen_ts") or place_ts)
        start = next(
            (i for i in range(idx, len(candles_exec)) if int(candles_exec[i].get("open_time") or 0) > last_seen),
            None,
        )
        if start is None:
            still.append(order)
            continue
        done = False
        for i in range(start, len(candles_exec)):
            bar = candles_exec[i]
            result = simulate_pending_on_bar(order, bar, bars_since_place=i - idx)
            order["last_seen_ts"] = int(bar.get("open_time") or 0)
            st = result.get("status")
            if st == "filled":
                pos = dict(result.get("position") or {})
                pos["thesis_id"] = order.get("thesis_id")
                pos["margin_usdt"] = order.get("margin_usdt")
                pos["notional_usdt"] = order.get("notional_usdt")
                pos["leverage"] = order.get("leverage")
                pos["assistant"] = True
                pos["mfe_pct"] = 0.0
                pos["source"] = ASSISTANT_SOURCE
                filled.append(pos)
                logs.append(
                    f"FILL {sym} {order.get('entry_style')} {order.get('action')} "
                    f"@ {float(result.get('entry') or 0):.6g} thesis={order.get('thesis_id')}"
                )
                done = True
                filled_here = True
                break
            if st == "cancelled":
                logs.append(f"CANCEL pending {order.get('id')} {sym} reason={result.get('reason')}")
                try:
                    from eurika.ml.holistic_portfolio import release_trade_margin

                    release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
                except Exception:
                    pass
                done = True
                break
        if not done:
            still.append(order)
    return still, filled, logs


def _structure_exit(
    pos: Mapping[str, Any],
    candles_15m: Sequence[dict[str, Any]],
    candles_1m: Sequence[dict[str, Any]],
    thesis: Mapping[str, Any] | None,
) -> tuple[bool, str, float]:
    """Early profit take on giveback / bearish 15m close."""
    entry = float(pos.get("entry") or 0.0)
    if entry <= 0 or not candles_1m:
        return False, "", 0.0
    act = str(pos.get("action") or "BUY").upper()
    last = float(candles_1m[-1].get("close") or 0.0)
    if last <= 0:
        return False, "", 0.0
    if act == "BUY":
        unreal = (last / entry) - 1.0
    else:
        unreal = (entry / last) - 1.0
    mfe = float(pos.get("mfe_pct") or unreal)
    if unreal > mfe:
        mfe = unreal
    arm = float((thesis or pos).get("structure_arm_mfe_pct") or DEFAULT_STRUCTURE_ARM_MFE_PCT)
    give_frac = float((thesis or pos).get("structure_giveback_frac") or DEFAULT_STRUCTURE_GIVEBACK_FRAC)
    if mfe < arm:
        return False, "", 0.0
    if unreal > mfe * (1.0 - give_frac):
        return False, "", 0.0
    if len(candles_15m) >= 2:
        prev_c = float(candles_15m[-2].get("close") or 0.0)
        cur_c = float(candles_15m[-1].get("close") or 0.0)
        if act == "BUY" and cur_c >= prev_c:
            return False, "", 0.0
        if act == "SELL" and cur_c <= prev_c:
            return False, "", 0.0
    if unreal <= 0:
        return False, "", 0.0
    return True, "structure_exit", last


def _close_position(
    root: str | Path,
    pos: Mapping[str, Any],
    *,
    exit_px: float,
    exit_ts: int,
    exit_reason: str,
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    market = normalize_market(pos.get("market"))
    act = str(pos.get("action") or "BUY").upper()
    fee = fee_for_market(market)
    lab = label_trade(float(pos.get("entry") or 0), float(exit_px), act, fee=fee)
    margin = float(pos.get("margin_usdt") or 0.0)
    notional = float(pos.get("notional_usdt") or margin * float(pos.get("leverage") or 1.0))
    pnl = float(lab.get("edge") or 0.0) * notional if notional > 0 else 0.0
    portfolio["realized_pnl_usdt"] = float(portfolio.get("realized_pnl_usdt") or 0.0) + pnl
    portfolio["equity_usdt"] = float(portfolio.get("equity_usdt") or 0.0) + pnl
    row = {
        "ts": exit_ts,
        "symbol": pos.get("symbol"),
        "market": market,
        "action": act,
        "entry": pos.get("entry"),
        "exit": exit_px,
        "exit_reason": exit_reason,
        "edge": lab.get("edge"),
        "correct": lab.get("correct"),
        "pnl_usdt": pnl,
        "thesis_id": pos.get("thesis_id"),
        "source": ASSISTANT_SOURCE,
        "assistant": True,
    }
    append_trade(root, row)
    if str(exit_reason or "").lower() == "sl":
        register_assistant_reentry_cooldown(
            root,
            symbol=str(pos.get("symbol") or ""),
            market=market,
            side=act,
            exit_ts_ms=int(exit_ts),
            bars_1m=DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M,
            exit_reason="sl",
        )
    try:
        from eurika.ml.holistic_portfolio import release_trade_margin

        release_trade_margin(root, margin, pnl)
    except Exception:
        pass
    return row


def _order_side(row: Mapping[str, Any]) -> str:
    side = str(row.get("side") or "").strip().upper()
    return side if side in {"BUY", "SELL"} else ""


def _entry_style(row: Mapping[str, Any]) -> str:
    style = str(row.get("entry_style") or row.get("style") or "market").strip().lower()
    return style if style in ENTRY_STYLES else "market"


def _mk_action_row(action_row: Mapping[str, Any]) -> dict[str, Any] | None:
    act = _ACTION_ALIASES.get(str(action_row.get("action") or action_row.get("op") or "").strip().lower())
    symbol = str(action_row.get("symbol") or "").strip().upper()
    if not act or not symbol:
        return None
    row = dict(action_row)
    row["action"] = act
    row["symbol"] = symbol
    row["market"] = normalize_market(action_row.get("market") or "futures")
    return row


def _build_assistant_open(
    root: str | Path,
    portfolio: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any] | None:
    from eurika.ml.llm_shadow_orders import normalize_level_frac

    symbol = str(row.get("symbol") or "").upper()
    market = normalize_market(row.get("market"))
    side = _order_side(row)
    if not side:
        return None
    candles_exec = load_candles(root, symbol, "1m", market=market)
    candles = load_candles(root, symbol, DEFAULT_INTERVAL, market=market)
    if not candles and not candles_exec:
        return None
    try:
        entry_bar = candles_exec[-1] if candles_exec else candles[-1]
        entry = float(entry_bar.get("close") or 0.0)
        entry_ts = int(entry_bar.get("open_time") or row.get("ts") or 0)
    except (TypeError, ValueError):
        return None
    if entry <= 0 or entry_ts <= 0:
        return None
    size = propose_size(portfolio, market=market, action=side, soft_entry=False)
    if not size.get("ok"):
        return None
    trail = normalize_level_frac(row.get("trail_pct"), default=0.0) or 0.0
    h_exec = max(1, main_horizon_to_exec(DEFAULT_HORIZON_MAIN, DEFAULT_INTERVAL, "1m"))
    tid = str(row.get("thesis_id") or f"{symbol.lower()}-agent-{uuid.uuid4().hex[:6]}")
    tp_pct, sl_pct = enforce_assistant_tp_sl(
        float(normalize_level_frac(row.get("tp_pct"), default=DEFAULT_ASSISTANT_TP_PCT) or DEFAULT_ASSISTANT_TP_PCT),
        float(normalize_level_frac(row.get("sl_pct"), default=DEFAULT_ASSISTANT_SL_PCT) or DEFAULT_ASSISTANT_SL_PCT),
    )
    return {
        "symbol": symbol,
        "market": market,
        "action": side,
        "entry": entry,
        "entry_ts": entry_ts,
        "interval": DEFAULT_INTERVAL,
        "exec_interval": "1m",
        "horizon": DEFAULT_HORIZON_MAIN,
        "horizon_exec": h_exec,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "trail_pct": trail if trail > 0 else None,
        "trail_extreme": entry if trail > 0 else None,
        "margin_usdt": float(size.get("margin_usdt") or 0.0),
        "notional_usdt": float(size.get("notional_usdt") or size.get("margin_usdt") or 0.0),
        "leverage": min(2.0, float(row.get("leverage") or size.get("leverage") or 1.0)),
        "thesis_id": tid,
        "mfe_pct": 0.0,
        "structure_arm_mfe_pct": float(
            row.get("structure_arm_mfe_pct") or DEFAULT_STRUCTURE_ARM_MFE_PCT
        ),
        "structure_giveback_frac": float(
            row.get("structure_giveback_frac") or DEFAULT_STRUCTURE_GIVEBACK_FRAC
        ),
        "assistant": True,
        "source": ASSISTANT_SOURCE,
        "agent_note": str(row.get("note") or row.get("narrative") or "")[:500],
    }


def _build_assistant_pending(
    root: str | Path,
    portfolio: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any] | None:
    from eurika.ml.llm_shadow_orders import normalize_level_frac

    symbol = str(row.get("symbol") or "").upper()
    market = normalize_market(row.get("market"))
    side = _order_side(row)
    style = _entry_style(row)
    if not side or style == "market":
        return None
    candles_exec = load_candles(root, symbol, "1m", market=market)
    candles = load_candles(root, symbol, DEFAULT_INTERVAL, market=market)
    if not candles and not candles_exec:
        return None
    try:
        signal_bar = candles_exec[-1] if candles_exec else candles[-1]
        signal_px = float(row.get("signal_px") or signal_bar.get("close") or 0.0)
        signal_ts = int(row.get("signal_ts") or row.get("ts") or signal_bar.get("open_time") or _now_ms())
    except (TypeError, ValueError):
        return None
    if signal_px <= 0:
        return None
    size = propose_size(portfolio, market=market, action=side, soft_entry=True)
    if not size.get("ok"):
        return None
    h_exec = max(1, main_horizon_to_exec(DEFAULT_HORIZON_MAIN, DEFAULT_INTERVAL, "1m"))
    tp_pct, sl_pct = enforce_assistant_tp_sl(
        float(
            normalize_level_frac(row.get("tp_pct"), default=DEFAULT_ASSISTANT_TP_PCT)
            or DEFAULT_ASSISTANT_TP_PCT
        ),
        float(
            normalize_level_frac(row.get("sl_pct"), default=DEFAULT_ASSISTANT_SL_PCT)
            or DEFAULT_ASSISTANT_SL_PCT
        ),
    )
    order = build_pending_order(
        symbol=symbol,
        market=market,
        action=side,
        signal_px=signal_px,
        signal_ts=signal_ts,
        interval=DEFAULT_INTERVAL,
        entry_style=style,
        horizon=DEFAULT_HORIZON_MAIN,
        horizon_exec=h_exec,
        exec_interval="1m",
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        trail_pct=float(
            normalize_level_frac(row.get("trail_pct"), default=DEFAULT_ASSISTANT_TRAIL_PCT)
            or DEFAULT_ASSISTANT_TRAIL_PCT
        ),
        invalidate_pct=float(normalize_level_frac(row.get("invalidate_pct"), default=0.005) or 0.005),
        source=ASSISTANT_SOURCE,
    )
    order["pending_horizon_exec"] = int(row.get("pending_horizon_exec") or DEFAULT_PENDING_HORIZON_EXEC)
    for key in ("limit_px", "stop_px", "invalidate_px"):
        if isinstance(row.get(key), (int, float)) and float(row[key]) > 0:
            order[key] = float(row[key])
    # BUY limit: invalidate must be below limit (dump cancel). SELL: above limit.
    try:
        lim = float(order.get("limit_px") or 0.0)
        inv = order.get("invalidate_px")
        inv_f = float(inv) if inv is not None else None
        if style == "limit" and lim > 0 and inv_f is not None and inv_f > 0:
            if side == "BUY" and inv_f >= lim:
                order["invalidate_px"] = round(lim * 0.995, 8)
                order["invalidate_fixed"] = "buy_inv_above_limit"
            elif side == "SELL" and inv_f <= lim:
                order["invalidate_px"] = round(lim * 1.005, 8)
                order["invalidate_fixed"] = "sell_inv_below_limit"
    except (TypeError, ValueError):
        pass
    order["thesis_id"] = str(row.get("thesis_id") or f"{symbol.lower()}-agent-{uuid.uuid4().hex[:6]}")
    order["margin_usdt"] = float(size.get("margin_usdt") or 0.0)
    order["notional_usdt"] = float(size.get("notional_usdt") or size.get("margin_usdt") or 0.0)
    order["leverage"] = min(2.0, float(row.get("leverage") or size.get("leverage") or 1.0))
    order["assistant"] = True
    order["agent_note"] = str(row.get("note") or row.get("narrative") or "")[:500]
    return order


def apply_assistant_actions(
    root: str | Path,
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from eurika.ml.llm_shadow_orders import normalize_level_frac, update_shadow_pending_order
    from eurika.ml.holistic_portfolio import (
        reconcile_holistic,
        release_trade_margin,
        reserve_trade_margin,
        trade_portfolio_overlay,
    )

    opens = load_opens(root)
    pending = load_pending(root)
    portfolio = ensure_portfolio(root)
    size_portfolio = trade_portfolio_overlay(root, portfolio)
    applied = {
        "open": 0,
        "place": 0,
        "add": 0,
        "close": 0,
        "update": 0,
        "cancel": 0,
        "hold": 0,
        "ignored": 0,
        "blocked": 0,
    }
    block_notes: list[str] = []
    closed_rows: list[dict[str, Any]] = []
    keep = list(opens)
    keep_pending = list(pending)
    max_opens = int(portfolio.get("max_opens") or MAX_OPENS)
    now_ms = _now_ms()

    def _match_opens(symbol: str, market: str) -> list[dict[str, Any]]:
        return [
            p
            for p in keep
            if str(p.get("symbol") or "").upper() == symbol and normalize_market(p.get("market")) == market
        ]

    def _match_pending(symbol: str, market: str) -> list[dict[str, Any]]:
        return [
            p
            for p in keep_pending
            if str(p.get("symbol") or "").upper() == symbol and normalize_market(p.get("market")) == market
        ]

    def _block_entry(symbol: str, market: str, side: str, level_px: float | None) -> bool:
        reason = assistant_entry_block_reason(
            root,
            symbol=symbol,
            market=market,
            side=side,
            level_px=level_px,
            now_ts_ms=now_ms,
        )
        if not reason:
            return False
        applied["blocked"] += 1
        block_notes.append(f"{symbol} {side}: {reason}")
        return True

    for raw in actions:
        row = _mk_action_row(raw)
        if row is None:
            applied["ignored"] += 1
            continue
        act = str(row["action"])
        symbol = str(row["symbol"])
        market = str(row.get("market") or "futures")
        open_matches = _match_opens(symbol, market)
        pend_matches = _match_pending(symbol, market)

        if act == "hold":
            applied["hold"] += 1
            continue

        if act in {"open", "place", "add"}:
            side = _order_side(row)
            if not side:
                applied["ignored"] += 1
                continue
            row = {**row, "side": side}
            style = _entry_style(row)
            level_px = _entry_level_px(row)
            if act != "add" and _block_entry(symbol, market, side, level_px):
                continue
            if act == "add" or style == "market":
                if act != "add":
                    for order in pend_matches:
                        release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
                    keep_pending = [p for p in keep_pending if p not in pend_matches]
                    if open_matches:
                        applied["ignored"] += 1
                        continue
                if act != "add" and len(keep) + len(keep_pending) >= max_opens:
                    applied["ignored"] += 1
                    continue
                pos = _build_assistant_open(root, size_portfolio, row)
                if pos is None:
                    applied["ignored"] += 1
                    continue
                margin = float(pos.get("margin_usdt") or 0.0)
                if margin > 0 and not reserve_trade_margin(root, margin):
                    applied["ignored"] += 1
                    continue
                keep.append(pos)
                if act != "add" and level_px is not None:
                    note_assistant_limit_place(
                        root,
                        symbol=symbol,
                        market=market,
                        side=side,
                        level_px=level_px,
                        now_ts_ms=now_ms,
                    )
                size_portfolio = trade_portfolio_overlay(root, portfolio)
                applied["add" if act == "add" else "open"] += 1
                continue
            for order in pend_matches:
                release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
            keep_pending = [p for p in keep_pending if p not in pend_matches]
            if open_matches:
                applied["ignored"] += 1
                continue
            if len(keep) + len(keep_pending) >= max_opens:
                applied["ignored"] += 1
                continue
            pending_order = _build_assistant_pending(root, size_portfolio, row)
            if pending_order is None:
                applied["ignored"] += 1
                continue
            margin = float(pending_order.get("margin_usdt") or 0.0)
            if margin > 0 and not reserve_trade_margin(root, margin):
                applied["ignored"] += 1
                continue
            keep_pending.append(pending_order)
            placed_level = _entry_level_px(pending_order) or level_px
            if placed_level is not None:
                note_assistant_limit_place(
                    root,
                    symbol=symbol,
                    market=market,
                    side=side,
                    level_px=float(placed_level),
                    now_ts_ms=now_ms,
                )
            size_portfolio = trade_portfolio_overlay(root, portfolio)
            applied["place"] += 1
            continue

        if act == "update":
            touched = 0
            for pos in open_matches:
                for key in ("tp_pct", "sl_pct", "trail_pct"):
                    frac = normalize_level_frac(row.get(key))
                    if frac is not None:
                        pos[key] = frac
                if "tp_pct" in pos or "sl_pct" in pos:
                    tp_u, sl_u = enforce_assistant_tp_sl(
                        float(pos.get("tp_pct") or DEFAULT_ASSISTANT_TP_PCT),
                        float(pos.get("sl_pct") or DEFAULT_ASSISTANT_SL_PCT),
                    )
                    pos["tp_pct"] = tp_u
                    pos["sl_pct"] = sl_u
                if pos.get("trail_pct"):
                    pos["trail_extreme"] = float(pos.get("trail_extreme") or pos.get("entry") or 0.0)
                touched += 1
            for order in pend_matches:
                update_shadow_pending_order(order, row)
                tp_u, sl_u = enforce_assistant_tp_sl(
                    float(order.get("tp_pct") or DEFAULT_ASSISTANT_TP_PCT),
                    float(order.get("sl_pct") or DEFAULT_ASSISTANT_SL_PCT),
                )
                order["tp_pct"] = tp_u
                order["sl_pct"] = sl_u
                touched += 1
            if touched:
                applied["update"] += touched
            else:
                applied["ignored"] += 1
            continue

        if act == "cancel":
            if not pend_matches:
                applied["ignored"] += 1
                continue
            for order in pend_matches:
                release_trade_margin(root, float(order.get("margin_usdt") or 0.0), 0.0)
            keep_pending = [p for p in keep_pending if p not in pend_matches]
            applied["cancel"] += len(pend_matches)
            size_portfolio = trade_portfolio_overlay(root, portfolio)
            continue

        if act == "close":
            if not open_matches:
                applied["ignored"] += 1
                continue
            latest_close = None
            candles_exec = load_candles(root, symbol, "1m", market=market)
            if candles_exec:
                last = candles_exec[-1]
                latest_close = (float(last.get("close") or 0.0), int(last.get("open_time") or 0))
            new_keep: list[dict[str, Any]] = []
            for pos in keep:
                if pos not in open_matches:
                    new_keep.append(pos)
                    continue
                if latest_close is None:
                    new_keep.append(pos)
                    continue
                exit_px, exit_ts = latest_close
                trade = _close_position(
                    root,
                    pos,
                    exit_px=exit_px,
                    exit_ts=exit_ts,
                    exit_reason="agent_close",
                    portfolio=portfolio,
                )
                closed_rows.append(trade)
                applied["close"] += 1
            keep = new_keep
            continue

        applied["ignored"] += 1

    portfolio["margin_used_usdt"] = _margin_used(keep, keep_pending)
    save_portfolio(root, portfolio)
    save_opens(root, keep)
    save_pending(root, keep_pending)
    reconcile_holistic(root)
    return {"applied": applied, "closed_rows": closed_rows, "block_notes": block_notes}


def run_book_tick(
    root: str | Path,
    *,
    now_ms: int | None = None,
    auto_place: bool = False,
    symbols: Sequence[str] | None = None,
    limit_1m: int = SYNC_1M_LIMIT,
    journal_kind: str = "cycle",
    write_journal: bool = True,
) -> dict[str, Any]:
    """Sync candles, process pending fills, resolve opens. Optional rule-based place."""
    root = Path(root).resolve()
    now = int(now_ms or _now_ms())
    portfolio = ensure_portfolio(root)
    theses = load_theses(root)
    opens = load_opens(root)
    pending = load_pending(root)
    logs: list[str] = [f"=== BOOK TICK {_ts_iso(now)} ==="]

    sym_set = {str(s).upper() for s in (symbols or SCAN_SYMBOLS)}
    sym_set.update(str(t.get("symbol")).upper() for t in theses)
    sym_set.update(str(p.get("symbol")).upper() for p in opens)
    sym_set.update(str(p.get("symbol")).upper() for p in pending)
    logs.extend(sync_assistant_symbols(root, sorted(sym_set), limit_1m=limit_1m))

    if auto_place:
        if not theses:
            theses = seed_theses(root)
        open_n = len(opens)
        pending_ids = {o.get("thesis_id") for o in pending}
        for th in theses:
            if th.get("status") != "watching":
                continue
            if th.get("id") in pending_ids:
                continue
            if open_n + len(pending) >= int(portfolio.get("max_opens") or MAX_OPENS):
                logs.append(f"skip place {th.get('id')}: max opens/pending")
                continue
            side = str(th.get("side") or "BUY").upper()
            level = None
            for key in ("limit_px", "stop_px"):
                raw = th.get(key)
                try:
                    if raw is not None and float(raw) > 0:
                        level = float(raw)
                        break
                except (TypeError, ValueError):
                    pass
            block = assistant_entry_block_reason(
                root,
                symbol=str(th.get("symbol") or ""),
                market=normalize_market(th.get("market")),
                side=side,
                level_px=level,
                now_ts_ms=now,
            )
            if block:
                logs.append(f"skip place {th.get('id')}: {block}")
                continue
            order = _thesis_to_pending(root, th, portfolio)
            if order:
                pending.append(order)
                th["status"] = "pending"
                th["updated_ms"] = now
                placed_level = _entry_level_px(order) or level
                if placed_level is not None:
                    note_assistant_limit_place(
                        root,
                        symbol=str(order.get("symbol") or th.get("symbol") or ""),
                        market=normalize_market(order.get("market") or th.get("market")),
                        side=str(order.get("action") or side),
                        level_px=float(placed_level),
                        now_ts_ms=now,
                    )
                logs.append(f"PLACE pending thesis={th.get('id')} {th.get('symbol')} {th.get('entry_style')}")

    pending_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for o in pending:
        group_key = (str(o.get("symbol")).upper(), normalize_market(o.get("market")))
        pending_groups.setdefault(group_key, []).append(o)
    new_pending: list[dict[str, Any]] = []
    for (sym, kind), group in pending_groups.items():
        still, filled, plogs = _process_pending_group(root, sym, kind, group)
        new_pending.extend(still)
        logs.extend(plogs)
        for pos in filled:
            opens.append(pos)
            for th in theses:
                if th.get("id") == pos.get("thesis_id"):
                    th["status"] = "open"
                    th["updated_ms"] = now
    pending = new_pending

    keep: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    thesis_by_id = {str(t.get("id")): t for t in theses}
    h_exec = max(1, main_horizon_to_exec(DEFAULT_HORIZON_MAIN, DEFAULT_INTERVAL, "1m"))
    for pos in opens:
        sym = str(pos.get("symbol") or "").upper()
        market = normalize_market(pos.get("market"))
        c1m = load_candles(root, sym, "1m", market=market)
        c15 = load_candles(root, sym, "15m", market=market)
        entry = float(pos.get("entry") or 0.0)
        if entry > 0 and c1m:
            idx = find_entry_index(c1m, int(pos.get("entry_ts") or pos.get("ts") or 0))
            if idx >= 0:
                path = c1m[idx:]
                if str(pos.get("action")).upper() == "BUY":
                    mfe = max((float(b["high"]) / entry - 1.0) for b in path if b.get("high"))
                else:
                    lows = [float(b["low"]) for b in path if b.get("low")]
                    mfe = max((entry / x - 1.0) for x in lows if x > 0) if lows else 0.0
                pos["mfe_pct"] = max(float(pos.get("mfe_pct") or 0.0), mfe)
        thesis = thesis_by_id.get(str(pos.get("thesis_id") or ""))
        hit, reason, px = _structure_exit(pos, c15, c1m, thesis)
        if hit:
            row = _close_position(
                root,
                pos,
                exit_px=px,
                exit_ts=int(c1m[-1].get("open_time") or now),
                exit_reason=reason,
                portfolio=portfolio,
            )
            closed.append(row)
            if thesis:
                thesis["status"] = "closed"
                thesis["updated_ms"] = now
            logs.append(
                f"CLOSE {sym} structure_exit @ {px:.6g} edge={float(row.get('edge') or 0):+.4%} "
                f"pnl={float(row.get('pnl_usdt') or 0):+.3f}$ thesis={pos.get('thesis_id')}"
            )
            continue
        sim = simulate_exec_exit(
            c1m,
            entry_ts=int(pos.get("entry_ts") or pos.get("ts") or 0),
            entry=entry,
            action=str(pos.get("action") or ""),
            horizon_exec=h_exec,
            tp_pct=float(pos.get("tp_pct") or 0.0),
            sl_pct=float(pos.get("sl_pct") or 0.0),
            trail_pct=float(pos.get("trail_pct") or 0.0),
            trail_extreme=float(pos["trail_extreme"]) if pos.get("trail_extreme") else None,
        )
        if sim and sim.get("trail_extreme") is not None:
            pos["trail_extreme"] = sim["trail_extreme"]
        if sim and sim.get("ready"):
            row = _close_position(
                root,
                pos,
                exit_px=float(sim.get("exit") or 0.0),
                exit_ts=int(sim.get("exit_ts") or now),
                exit_reason=str(sim.get("reason") or "exit"),
                portfolio=portfolio,
            )
            closed.append(row)
            if thesis:
                thesis["status"] = "closed"
                thesis["updated_ms"] = now
            logs.append(
                f"CLOSE {sym} {sim.get('reason')} @ {float(sim.get('exit') or 0):.6g} "
                f"pnl={float(row.get('pnl_usdt') or 0):+.3f}$"
            )
        else:
            keep.append(pos)
    opens = keep

    portfolio["margin_used_usdt"] = _margin_used(opens, pending)
    save_portfolio(root, portfolio)
    save_opens(root, opens)
    save_pending(root, pending)
    save_theses(root, theses)

    eq = float(portfolio.get("equity_usdt") or 0.0)
    start = float(portfolio.get("start_equity_usdt") or eq)
    logs.append(
        f"\nBOOK equity={eq:.2f} Δ={eq-start:+.2f}$ margin={portfolio['margin_used_usdt']:.2f} "
        f"opens={len(opens)} pending={len(pending)} closed_cycle={len(closed)}"
    )
    if opens:
        logs.append("OPENS:")
        for p in opens:
            logs.append(
                f"  {p.get('symbol')} {p.get('action')} entry={p.get('entry')} "
                f"mfe={float(p.get('mfe_pct') or 0):+.3%} thesis={p.get('thesis_id')}"
            )
    if pending:
        logs.append("PENDING:")
        for p in pending:
            logs.append(
                f"  {p.get('symbol')} {p.get('entry_style')} limit={p.get('limit_px')} "
                f"stop={p.get('stop_px')} thesis={p.get('thesis_id')}"
            )

    text = "\n".join(logs)
    if write_journal:
        append_journal(
            root,
            kind=journal_kind,
            text=text,
            extra={
                "equity_usdt": eq,
                "opens": len(opens),
                "pending": len(pending),
                "closed": len(closed),
            },
        )
    return {
        "equity_usdt": eq,
        "opens": len(opens),
        "pending": len(pending),
        "closed": len(closed),
        "logs": logs,
    }


def run_cycle(root: str | Path, *, now_ms: int | None = None) -> dict[str, Any]:
    """One mechanical assistant cycle (rule-based thesis placement)."""
    return run_book_tick(root, now_ms=now_ms, auto_place=True, journal_kind="cycle")


def format_morning_report(root: str | Path) -> str:
    root = Path(root).resolve()
    port = load_portfolio(root)
    eq = float(port.get("equity_usdt") or 0.0)
    start = float(port.get("start_equity_usdt") or eq)
    lines = [
        f"# Assistant night paper — {_ts_iso()}",
        f"equity {eq:.2f} USDT (start {start:.2f}, Δ {eq-start:+.2f})",
        f"opens {len(load_opens(root))} pending {len(load_pending(root))}",
        "",
        "## Theses",
    ]
    for th in load_theses(root):
        lines.append(
            f"- {th.get('symbol')} [{th.get('status')}] {th.get('trigger')}: "
            f"{(th.get('narrative') or '')[:120]}…"
        )
    lines.append("\n## Journal tail (last 8 cycles)")
    journal = assistant_journal_path(root)
    if journal.is_file():
        rows = journal.read_text(encoding="utf-8").strip().splitlines()
        for line in rows[-8:]:
            try:
                row = json.loads(line)
                lines.append(f"\n### {row.get('ts_iso')} ({row.get('kind')})\n{row.get('text')}")
            except json.JSONDecodeError:
                continue
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assistant thesis night paper")
    parser.add_argument("--root", default=".", help="Project root")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="Scan market and create theses")
    sub.add_parser("once", help="Run one cycle")
    p_loop = sub.add_parser("loop", help="Run cycles until interrupted")
    p_loop.add_argument("--interval", type=int, default=900, help="Seconds between cycles")
    sub.add_parser("agent-once", help="One holistic LLM portfolio cycle")
    p_agent_loop = sub.add_parser("agent-loop", help="Holistic LLM cycles until interrupted")
    p_agent_loop.add_argument("--interval", type=int, default=900, help="Seconds between cycles")
    sub.add_parser("portfolio-once", help="Alias for agent-once")
    p_port_loop = sub.add_parser("portfolio-loop", help="Alias for agent-loop")
    p_port_loop.add_argument("--interval", type=int, default=900, help="Seconds between cycles")
    sub.add_parser("report", help="Morning summary")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "seed":
        seed_theses(root)
    elif args.cmd == "once":
        run_cycle(root)
    elif args.cmd == "loop":
        append_journal(root, kind="start", text=f"=== LOOP START {_ts_iso()} interval={args.interval}s ===")
        while True:
            try:
                run_cycle(root)
            except Exception as exc:
                append_journal(
                    root,
                    kind="error",
                    text=f"CYCLE ERROR {type(exc).__name__}: {exc}",
                )
            time.sleep(max(60, int(args.interval)))
    elif args.cmd in {"agent-once", "agent-loop", "portfolio-once", "portfolio-loop"}:
        from eurika.ml.portfolio_agent import run_portfolio_cycle

        loop_cmds = {"agent-loop", "portfolio-loop"}
        interval = int(getattr(args, "interval", 900))
        if args.cmd in loop_cmds:
            append_journal(
                root,
                kind="start",
                text=f"=== PORTFOLIO LOOP START {_ts_iso()} interval={interval}s ===",
            )
        while True:
            try:
                run_portfolio_cycle(root)
            except Exception as exc:
                append_journal(
                    root,
                    kind="error",
                    text=f"PORTFOLIO CYCLE ERROR {type(exc).__name__}: {exc}",
                )
            if args.cmd not in loop_cmds:
                break
            time.sleep(max(60, interval))
    elif args.cmd == "report":
        print(format_morning_report(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
