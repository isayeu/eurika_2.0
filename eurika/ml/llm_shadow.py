"""LLM shadow portfolio: separate bankroll for hourly teacher advice.

Shadow LLM places market entries or cancelable pending (limit/stop/OCO), manages
them on each 15m critique, and resolves fills with the same 1m TP/SL/trail/horizon
skeleton as paper — without touching ``paper_portfolio.json`` / ``paper_trades.jsonl``.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.exec_tf import main_horizon_to_exec, simulate_exec_exit
from eurika.ml.live_paper import stale_force_close_reason
from eurika.ml.llm_shadow_orders import (
    DEFAULT_AGENT_SL_PCT,
    DEFAULT_AGENT_TP_PCT,
    build_shadow_pending_order,
    enforce_tp_sl_ratio,
    format_shadow_pending_for_prompt,
    load_shadow_pending,
    margin_used_with_pending,
    normalize_level_frac,
    process_llm_shadow_pendings,
    save_shadow_pending,
    update_shadow_pending_order,
)
from eurika.ml.market_store import load_candles, ml_root, normalize_market
from eurika.ml.paper_orders import ENTRY_STYLES
from eurika.ml.paper_portfolio import (
    DEFAULT_START_EQUITY_USDT,
    propose_size,
)
from eurika.ml.paper_trader import fee_for_market, label_trade

DEFAULT_SHADOW_START_EQUITY_USDT = DEFAULT_START_EQUITY_USDT
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


def llm_shadow_portfolio_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_shadow_portfolio.json"


def llm_shadow_open_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_shadow_open.json"


def llm_shadow_trades_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_shadow_trades.jsonl"


def default_shadow_portfolio(
    *,
    start_equity: float = DEFAULT_SHADOW_START_EQUITY_USDT,
) -> dict[str, Any]:
    eq = max(1.0, float(start_equity))
    now = int(time.time() * 1000)
    return {
        "version": 1,
        "start_equity_usdt": eq,
        "equity_usdt": eq,
        "margin_used_usdt": 0.0,
        "realized_pnl_usdt": 0.0,
        "risk_frac": 0.01,
        "max_margin_frac": 0.30,
        "updated_ms": now,
        "created_ms": now,
        "note": "llm shadow bankroll; independent of paper_portfolio",
    }


def load_shadow_portfolio(project_root: str | Path) -> dict[str, Any]:
    path = llm_shadow_portfolio_path(project_root)
    if not path.is_file():
        return default_shadow_portfolio()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_shadow_portfolio()
    if not isinstance(data, dict):
        return default_shadow_portfolio()
    out = default_shadow_portfolio()
    out.update({k: data[k] for k in data if k in out or k in ("version", "note", "created_ms")})
    try:
        out["equity_usdt"] = float(data.get("equity_usdt") or out["equity_usdt"])
        out["start_equity_usdt"] = float(data.get("start_equity_usdt") or out["start_equity_usdt"])
        out["margin_used_usdt"] = max(0.0, float(data.get("margin_used_usdt") or 0.0))
        out["realized_pnl_usdt"] = float(data.get("realized_pnl_usdt") or 0.0)
        out["risk_frac"] = float(data.get("risk_frac") or out["risk_frac"])
        out["max_margin_frac"] = float(data.get("max_margin_frac") or out["max_margin_frac"])
    except (TypeError, ValueError):
        return default_shadow_portfolio()
    return out


def save_shadow_portfolio(project_root: str | Path, portfolio: Mapping[str, Any]) -> Path:
    path = llm_shadow_portfolio_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(portfolio)
    blob["updated_ms"] = int(time.time() * 1000)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ensure_shadow_portfolio(project_root: str | Path) -> dict[str, Any]:
    path = llm_shadow_portfolio_path(project_root)
    if path.is_file():
        return load_shadow_portfolio(project_root)
    port = default_shadow_portfolio()
    save_shadow_portfolio(project_root, port)
    return port


def load_shadow_opens(project_root: str | Path) -> list[dict[str, Any]]:
    path = llm_shadow_open_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("positions") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def save_shadow_opens(project_root: str | Path, positions: list[dict[str, Any]]) -> Path:
    path = llm_shadow_open_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"positions": positions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    port = ensure_shadow_portfolio(project_root)
    port["margin_used_usdt"] = margin_used_with_pending(positions, load_shadow_pending(project_root))
    save_shadow_portfolio(project_root, port)
    return path


def _sync_shadow_margin(project_root: str | Path, opens: Sequence[Mapping[str, Any]] | None = None) -> float:
    positions = list(opens) if opens is not None else load_shadow_opens(project_root)
    used = margin_used_with_pending(positions, load_shadow_pending(project_root))
    port = ensure_shadow_portfolio(project_root)
    port["margin_used_usdt"] = used
    save_shadow_portfolio(project_root, port)
    return used


def append_shadow_trades(project_root: str | Path, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    path = llm_shadow_trades_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return len(rows)


def load_shadow_trades(project_root: str | Path) -> list[dict[str, Any]]:
    path = llm_shadow_trades_path(project_root)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        return []
    return out


def shadow_portfolio_status(project_root: str | Path) -> dict[str, Any]:
    port = load_shadow_portfolio(project_root)
    equity = float(port.get("equity_usdt") or DEFAULT_SHADOW_START_EQUITY_USDT)
    start = float(port.get("start_equity_usdt") or DEFAULT_SHADOW_START_EQUITY_USDT)
    used = margin_used_with_pending(load_shadow_opens(project_root), load_shadow_pending(project_root))
    mf = float(port.get("max_margin_frac") or 0.30)
    return {
        "equity_usdt": equity,
        "start_equity_usdt": start,
        "realized_pnl_usdt": float(port.get("realized_pnl_usdt") or 0.0),
        "session_pnl_usdt": equity - start,
        "margin_used_usdt": used,
        "margin_free_usdt": max(0.0, equity * mf - used),
        "max_margin_usdt": equity * mf,
        "risk_frac": float(port.get("risk_frac") or 0.01),
        "max_margin_frac": mf,
        "pending_n": len(load_shadow_pending(project_root)),
        "path": str(llm_shadow_portfolio_path(project_root)),
    }


def _symbol_market_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("symbol") or "").upper(), normalize_market(row.get("market")))


def _open_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        *_symbol_market_key(row),
        int(row.get("llm_row_ts") or row.get("ts") or 0),
    )


def _teacher_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        *_symbol_market_key(row),
        int(row.get("ts") or 0),
    )


def _teacher_market_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("enter") or "").lower() != "yes":
            continue
        side = str(row.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            continue
        out.append(dict(row))
    return out


def _try_obj(blob: str) -> dict[str, Any] | None:
    text = (blob or "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    depth = 0
    end = -1
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        data = json.loads(text[: end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_shadow_actions(text: str) -> list[dict[str, Any]]:
    raw = text or ""
    blobs: list[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fence:
        blobs.append(fence.group(1))
    idx = raw.rfind('"shadow_actions"')
    if idx >= 0:
        start = raw.rfind("{", 0, idx + 1)
        if start >= 0:
            blobs.append(raw[start:])
    blobs.append(raw)
    for blob in blobs:
        data = _try_obj(blob)
        if not data:
            continue
        rows = data.get("shadow_actions")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def format_shadow_opens_for_prompt(project_root: str | Path, *, limit: int = 12) -> str:
    opens = load_shadow_opens(project_root)
    lines = ["LLM SHADOW OPENS"]
    if not opens:
        lines.append("  none")
    else:
        for pos in opens[:limit]:
            lines.append(
                "  "
                + f"{pos.get('symbol')} {pos.get('market')} {pos.get('action')} "
                + f"entry={float(pos.get('entry') or 0.0):.4f} "
                + f"tp={float(pos.get('tp_pct') or 0.0):.4f} "
                + f"sl={float(pos.get('sl_pct') or 0.0):.4f} "
                + f"trail={float(pos.get('trail_pct') or 0.0):.4f} "
                + f"style={pos.get('entry_style') or 'market'} "
                + f"llm_row_ts={int(pos.get('llm_row_ts') or 0)}"
            )
    return "\n".join(lines) + "\n\n" + format_shadow_pending_for_prompt(project_root, limit=limit)


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
    row["market"] = normalize_market(action_row.get("market"))
    return row


def _build_shadow_open(
    project_root: str | Path,
    portfolio: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "").upper()
    market = normalize_market(row.get("market"))
    side = _order_side(row) or str(row.get("side") or "").upper()
    if side not in {"BUY", "SELL"}:
        return None
    interval = str(row.get("interval") or "").strip() or "15m"
    candles = load_candles(project_root, symbol, interval, market=market)
    if not candles:
        return None
    exec_interval = "1m"
    candles_exec = load_candles(project_root, symbol, exec_interval, market=market)
    # Stamp the entry on the execution TF: resolution walks 1m bars after
    # entry_ts, so a main-TF bar open would replay minutes that had already
    # closed before the advice was given.
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
    tp_pct, sl_pct = enforce_tp_sl_ratio(
        float(normalize_level_frac(row.get("tp_pct"), default=DEFAULT_AGENT_TP_PCT) or DEFAULT_AGENT_TP_PCT),
        float(normalize_level_frac(row.get("sl_pct"), default=DEFAULT_AGENT_SL_PCT) or DEFAULT_AGENT_SL_PCT),
    )
    return {
        "kind": "llm_shadow",
        "symbol": symbol,
        "market": market,
        "action": side,
        "entry": entry,
        "entry_ts": entry_ts,
        "interval": interval,
        "exec_interval": "1m",
        "horizon": int(row.get("horizon") or 4),
        "horizon_exec": max(1, main_horizon_to_exec(int(row.get("horizon") or 4), interval, "1m")),
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "trail_pct": trail if trail > 0 else None,
        "trail_extreme": entry if trail > 0 else None,
        "margin_usdt": float(size.get("margin_usdt") or 0.0),
        "notional_usdt": float(size.get("notional_usdt") or size.get("margin_usdt") or 0.0),
        "leverage": float(row.get("leverage") or size.get("leverage") or 1.0),
        "llm_row_ts": int(row.get("llm_row_ts") or row.get("ts") or entry_ts),
        "teacher_source": str(row.get("source") or "cursor"),
        "when": str(row.get("when") or ""),
        "entry_style": "market",
        "source": "llm_shadow",
    }


def open_from_teacher_rows(
    project_root: str | Path,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Open shadow market entries from fresh teacher BUY/SELL rows.

    Conditional setups belong in ``shadow_actions`` (limit/stop/oco). Teacher
    ``enter:yes`` stays immediate market-only and skips symbols that already
    have an open or a pending.
    """
    opens = load_shadow_opens(project_root)
    existing = {_open_key(p) for p in opens}
    held = {_symbol_market_key(p) for p in opens}
    pending_keys = {_symbol_market_key(p) for p in load_shadow_pending(project_root)}
    portfolio = ensure_shadow_portfolio(project_root)
    portfolio["margin_used_usdt"] = margin_used_with_pending(opens, load_shadow_pending(project_root))
    added: list[dict[str, Any]] = []
    rejected = 0
    for row in _teacher_market_rows(rows):
        key = _teacher_key(row)
        sym_key = _symbol_market_key(row)
        if key in existing or sym_key in held or sym_key in pending_keys:
            continue
        pos = _build_shadow_open(project_root, portfolio, row)
        if pos is None:
            rejected += 1
            continue
        opens.append(pos)
        existing.add(key)
        held.add(sym_key)
        portfolio["margin_used_usdt"] = margin_used_with_pending(opens, load_shadow_pending(project_root))
        added.append(pos)
    if added:
        save_shadow_opens(project_root, opens)
    return {"opened": len(added), "rejected": rejected, "positions": added}


def _shadow_trade_row(pos: Mapping[str, Any], *, exit_px: float, exit_ts: int, exit_reason: str) -> dict[str, Any]:
    action = str(pos.get("action") or "").upper()
    entry = float(pos.get("entry") or 0.0)
    market = str(pos.get("market") or "spot").lower()
    fee = fee_for_market(market)
    lab = label_trade(entry, exit_px, action, fee=fee)
    return {
        "kind": "llm_shadow_trade",
        "shadow_llm": True,
        "live": False,
        "source": "llm_shadow",
        "teacher_source": str(pos.get("teacher_source") or "cursor"),
        "symbol": str(pos.get("symbol") or ""),
        "market": market,
        "action": action,
        "ts": int(pos.get("entry_ts") or 0),
        "llm_row_ts": int(pos.get("llm_row_ts") or 0),
        "entry": entry,
        "entry_ts": int(pos.get("entry_ts") or 0),
        "exit_px": exit_px,
        "exit_ts": exit_ts,
        "exit_reason": exit_reason,
        "tp_pct": pos.get("tp_pct"),
        "sl_pct": pos.get("sl_pct"),
        "trail_pct": pos.get("trail_pct"),
        "margin_usdt": float(pos.get("margin_usdt") or 0.0),
        "notional_usdt": float(pos.get("notional_usdt") or 0.0),
        "leverage": float(pos.get("leverage") or 1.0),
        "edge": float(lab.get("edge") or 0.0),
        "correct": bool(lab.get("correct")),
        "pnl_usdt": None,
    }


def _apply_shadow_close(
    project_root: str | Path,
    *,
    margin_usdt: float,
    edge: float,
    notional_usdt: float,
    opens: Sequence[Mapping[str, Any]],
    pending: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    port = ensure_shadow_portfolio(project_root)
    notion = max(0.0, float(notional_usdt))
    marg = max(0.0, float(margin_usdt))
    pnl = float(edge) * notion
    if pnl < 0 and marg > 0:
        pnl = max(pnl, -marg)
    pend = list(pending) if pending is not None else load_shadow_pending(project_root)
    port["equity_usdt"] = max(1.0, float(port.get("equity_usdt") or DEFAULT_SHADOW_START_EQUITY_USDT) + pnl)
    port["realized_pnl_usdt"] = float(port.get("realized_pnl_usdt") or 0.0) + pnl
    port["margin_used_usdt"] = margin_used_with_pending(opens, pend)
    save_shadow_portfolio(project_root, port)
    return {**port, "pnl_usdt": pnl}


def ingest_pending_fills(project_root: str | Path, *, now_ms: int | None = None) -> dict[str, Any]:
    """Fill/cancel LLM shadow pendings on 1m, then append filled positions to opens."""
    result = process_llm_shadow_pendings(project_root, now_ms=now_ms)
    positions = list(result.get("positions") or [])
    if not positions:
        _sync_shadow_margin(project_root)
        return result
    opens = load_shadow_opens(project_root)
    held = {_symbol_market_key(p) for p in opens}
    added = 0
    for pos in positions:
        key = _symbol_market_key(pos)
        if key in held:
            continue
        opens.append(pos)
        held.add(key)
        added += 1
    save_shadow_opens(project_root, opens)
    return {**result, "opened_from_fill": added}


def apply_shadow_actions(
    project_root: str | Path,
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    opens = load_shadow_opens(project_root)
    pending = load_shadow_pending(project_root)
    portfolio = ensure_shadow_portfolio(project_root)
    portfolio["margin_used_usdt"] = margin_used_with_pending(opens, pending)
    applied = {
        "open": 0,
        "place": 0,
        "add": 0,
        "close": 0,
        "update": 0,
        "cancel": 0,
        "hold": 0,
        "ignored": 0,
    }
    closed_rows: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = list(opens)
    keep_pending: list[dict[str, Any]] = list(pending)

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

    for raw in actions:
        row = _mk_action_row(raw)
        if row is None:
            applied["ignored"] += 1
            continue
        act = str(row["action"])
        symbol = str(row["symbol"])
        market = str(row.get("market") or "spot")
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
            if act == "add" or style == "market":
                if act != "add":
                    keep_pending = [p for p in keep_pending if p not in pend_matches]
                    if open_matches:
                        applied["ignored"] += 1
                        continue
                portfolio["margin_used_usdt"] = margin_used_with_pending(keep, keep_pending)
                pos = _build_shadow_open(project_root, portfolio, row)
                if pos is None:
                    applied["ignored"] += 1
                    continue
                keep.append(pos)
                portfolio["margin_used_usdt"] = margin_used_with_pending(keep, keep_pending)
                applied["add" if act == "add" else "open"] += 1
                continue
            # Cancelable entry: replace any existing pending for this symbol.
            keep_pending = [p for p in keep_pending if p not in pend_matches]
            if open_matches:
                applied["ignored"] += 1
                continue
            portfolio["margin_used_usdt"] = margin_used_with_pending(keep, keep_pending)
            order = build_shadow_pending_order(project_root, portfolio, row)
            if order is None:
                applied["ignored"] += 1
                continue
            keep_pending.append(order)
            portfolio["margin_used_usdt"] = margin_used_with_pending(keep, keep_pending)
            applied["place"] += 1
            continue

        if act == "update":
            touched = 0
            for pos in open_matches:
                for key in ("tp_pct", "sl_pct", "trail_pct"):
                    frac = normalize_level_frac(row.get(key))
                    if frac is not None:
                        pos[key] = frac
                tp_u, sl_u = enforce_tp_sl_ratio(
                    float(pos.get("tp_pct") or DEFAULT_AGENT_TP_PCT),
                    float(pos.get("sl_pct") or DEFAULT_AGENT_SL_PCT),
                )
                pos["tp_pct"] = tp_u
                pos["sl_pct"] = sl_u
                if pos.get("trail_pct"):
                    pos["trail_extreme"] = float(pos.get("trail_extreme") or pos.get("entry") or 0.0)
                touched += 1
            for order in pend_matches:
                update_shadow_pending_order(order, row)
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
            keep_pending = [p for p in keep_pending if p not in pend_matches]
            applied["cancel"] += len(pend_matches)
            portfolio["margin_used_usdt"] = margin_used_with_pending(keep, keep_pending)
            continue

        if act == "close":
            if not open_matches:
                applied["ignored"] += 1
                continue
            latest_close = None
            candles_exec = load_candles(project_root, symbol, "1m", market=market)
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
                trade = _shadow_trade_row(pos, exit_px=exit_px, exit_ts=exit_ts, exit_reason="llm_close")
                port = _apply_shadow_close(
                    project_root,
                    margin_usdt=float(pos.get("margin_usdt") or 0.0),
                    edge=float(trade.get("edge") or 0.0),
                    notional_usdt=float(pos.get("notional_usdt") or 0.0),
                    opens=new_keep,
                    pending=keep_pending,
                )
                # pending still reserved separately after save below
                trade["pnl_usdt"] = float(port.get("pnl_usdt") or 0.0)
                closed_rows.append(trade)
                applied["close"] += 1
            keep = new_keep
            continue

        applied["ignored"] += 1

    save_shadow_pending(project_root, keep_pending)
    save_shadow_opens(project_root, keep)
    if closed_rows:
        append_shadow_trades(project_root, closed_rows)
    return {"applied": applied, "closed_rows": closed_rows}


def resolve_llm_shadow(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Resolve open shadow positions with exec TF TP/SL/trail/horizon."""
    now = int(now_ms or time.time() * 1000)
    opens = load_shadow_opens(project_root)
    if not opens:
        return {"closed": 0, "waiting": 0, "rows": []}
    keep: list[dict[str, Any]] = []
    closed_rows: list[dict[str, Any]] = []
    for pos in opens:
        symbol = str(pos.get("symbol") or "").upper()
        market = str(pos.get("market") or "spot").lower()
        exec_iv = str(pos.get("exec_interval") or "1m")
        candles_exec = load_candles(project_root, symbol, exec_iv, market=market)
        if not candles_exec:
            keep.append(pos)
            continue
        sim = simulate_exec_exit(
            candles_exec,
            entry_ts=int(pos.get("entry_ts") or 0),
            entry=float(pos.get("entry") or 0.0),
            action=str(pos.get("action") or ""),
            horizon_exec=int(pos.get("horizon_exec") or 4),
            tp_pct=float(pos.get("tp_pct") or 0.0),
            sl_pct=float(pos.get("sl_pct") or 0.0),
            trail_pct=float(pos.get("trail_pct") or 0.0),
            trail_extreme=float(pos["trail_extreme"]) if pos.get("trail_extreme") else None,
        )
        if sim and sim.get("trail_extreme") is not None:
            pos["trail_extreme"] = sim["trail_extreme"]
        if sim is None or not sim.get("ready"):
            # Entry scrolled out of the retained 1m window: without this the
            # position would never resolve and would hold shadow margin forever.
            stale_why = stale_force_close_reason(
                {**pos, "ts": int(pos.get("entry_ts") or 0)},
                now_ts_ms=now,
                interval=str(pos.get("interval") or "15m"),
                horizon=int(pos.get("horizon") or 4),
                candles_exec=candles_exec,
            )
            if stale_why is None:
                keep.append(pos)
                continue
            exit_px = float(candles_exec[-1].get("close") or 0.0)
            exit_ts = int(candles_exec[-1].get("open_time") or 0)
            exit_reason = stale_why
        else:
            exit_px = float(sim.get("exit") or 0.0)
            exit_ts = int(sim.get("exit_ts") or 0)
            exit_reason = str(sim.get("reason") or "horizon")
        row = _shadow_trade_row(
            pos,
            exit_px=exit_px,
            exit_ts=exit_ts,
            exit_reason=exit_reason,
        )
        port = _apply_shadow_close(
            project_root,
            margin_usdt=float(pos.get("margin_usdt") or 0.0),
            edge=float(row.get("edge") or 0.0),
            notional_usdt=float(pos.get("notional_usdt") or 0.0),
            opens=keep,
        )
        row["pnl_usdt"] = float(port.get("pnl_usdt") or 0.0)
        closed_rows.append(row)
    if closed_rows:
        append_shadow_trades(project_root, closed_rows)
    else:
        used = margin_used_with_pending(keep, load_shadow_pending(project_root))
        if used != margin_used_with_pending(opens, load_shadow_pending(project_root)):
            port = ensure_shadow_portfolio(project_root)
            port["margin_used_usdt"] = used
            save_shadow_portfolio(project_root, port)
    save_shadow_opens(project_root, keep)
    return {"closed": len(closed_rows), "waiting": len(keep), "rows": closed_rows}

