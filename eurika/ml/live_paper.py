"""Live paper tick: small kline tail → infer → open/resolve → learn.

No live Binance orders. Designed for Chat Market panel (event stream).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from eurika.ml.entry_cost import (
    calibrate_cost_gate,
    cost_gate_ok,
    expansion_score,
    load_cost_gate,
)
from eurika.ml.features import DEFAULT_WINDOW, feature_vector, features_dict, impulse_horizon
from eurika.ml.exec_tf import (
    DEFAULT_EXEC_INTERVAL,
    DEFAULT_SL_PCT,
    DEFAULT_TP_PCT,
    exit_feature_vector,
    interval_ms,
    main_horizon_to_exec,
    path_excursions,
    retro_exit_samples,
    should_model_exit,
    simulate_exec_exit,
)
from eurika.ml.market_model import (
    append_exit_samples,
    append_style_samples,
    entry_setup_ok,
    model_status,
    predict_action,
    predict_entry_style,
    predict_exit,
    predict_levels,
    soften_entry_action,
    train_entry_style_policy,
    train_market_exit_policy,
    train_market_levels_policy,
    train_market_policy,
)
from eurika.ml.paper_orders import (
    DEFAULT_TRAIL_PCT,
    build_pending_order,
    cancel_pending_orders_for_symbol,
    load_pending_orders,
    process_pending_orders,
    retro_best_entry_style,
    save_pending_orders,
)
from eurika.ml.paper_portfolio import (
    adjust_soft_futures_levels,
    apply_close,
    ensure_portfolio,
    propose_size,
    recompute_margin_used,
    save_portfolio,
    utc_hour_from_ms,
)
from eurika.ml.market_store import (
    DEFAULT_INTERVAL,
    DEFAULT_MARKET,
    DEFAULT_SYMBOL,
    MarketKind,
    load_candles,
    ml_root,
    normalize_market,
    parse_markets,
    save_candles,
    sync_klines,
)
from eurika.ml.paper_trader import (
    DEFAULT_THR,
    commission_breakdown,
    fee_for_market,
    resolve_funding_edge,
    label_trade,
    paper_trades_path,
)

# Keep only a short local window — live learning, not bulk history.
DEFAULT_SYNC_LIMIT = 100
DEFAULT_MAX_KEEP = 120
DEFAULT_EXEC_SYNC_LIMIT = 180
DEFAULT_EXEC_MAX_KEEP = 360  # > 4h×1m horizon so entry@bar0 can still reach horizon exit
DEFAULT_EXPLORE_RATE = 0.5
DEFAULT_LIVE_HORIZON = 2
# After this many live labels, explore auto-stops (0 = unlimited).
DEFAULT_EXPLORE_LIVE_CAP = 80
# Gate-rejected entries kept in flight; a stuck one must never grow the book.
MAX_SHADOW_OPEN = 200
# Planned hold × this → force close (entry scrolled out of 1m window otherwise
# remapped to bar 0 and waited forever).
MAX_HOLD_MULT = 3


def planned_hold_ms(
    pos: Mapping[str, Any],
    *,
    interval: str,
    horizon: int,
) -> int:
    """How long the position was meant to live, in ms (exec horizon preferred)."""
    pos_exec = str(pos.get("exec_interval") or "").strip()
    h_exec = pos.get("horizon_exec")
    if pos_exec and h_exec is not None:
        try:
            return max(1, int(h_exec)) * interval_ms(pos_exec)
        except (TypeError, ValueError):
            pass
    h = max(1, int(pos.get("horizon") or horizon or 1))
    return h * interval_ms(str(pos.get("interval") or interval))


def stale_force_close_reason(
    pos: Mapping[str, Any],
    *,
    now_ts_ms: int,
    interval: str,
    horizon: int,
    candles_exec: Sequence[dict[str, Any]] | None = None,
    hold_mult: int = MAX_HOLD_MULT,
) -> str | None:
    """Return ``stale`` / ``max_age`` when the open must be force-closed, else None."""
    entry_ts = int(pos.get("ts") or 0)
    if entry_ts <= 0 or now_ts_ms <= 0:
        return None
    age = int(now_ts_ms) - entry_ts
    planned = planned_hold_ms(pos, interval=interval, horizon=horizon)
    if age >= max(1, int(hold_mult)) * planned:
        return "max_age"
    if candles_exec:
        first_ts = int(candles_exec[0].get("open_time") or 0)
        # Entry left the retained exec window and the planned hold is already over.
        if first_ts > 0 and entry_ts < first_ts and age >= planned:
            return "stale"
    return None


def _fetch_futures_funding(
    symbol: str,
    *,
    entry_ts_ms: int,
    exit_ts_ms: int,
) -> dict[str, Any]:
    """Public Binance funding for paper close (history + premium fallback)."""
    out: dict[str, Any] = {
        "settlements": [],
        "last_funding_rate": None,
        "fetch_ok": False,
        "error": None,
    }
    try:
        from eurika.integrations.binance_readonly import (
            futures_funding_rate_history,
            futures_premium_index,
        )

        hist = futures_funding_rate_history(
            symbol,
            start_time=int(entry_ts_ms),
            end_time=int(exit_ts_ms),
            limit=100,
        )
        if hist.get("ok"):
            out["settlements"] = list(hist.get("rows") or [])
            out["fetch_ok"] = True
        else:
            out["error"] = hist.get("error")
        prem = futures_premium_index(symbol)
        if prem.get("ok") and prem.get("last_funding_rate") is not None:
            out["last_funding_rate"] = float(prem["last_funding_rate"])
            out["fetch_ok"] = True
        elif not out["fetch_ok"]:
            out["error"] = prem.get("error") or out.get("error")
    except Exception as exc:
        out["error"] = str(exc)
    return out


def count_live_labels(project_root: str | Path) -> int:
    """Labels that count toward the explore budget.

    Live closes always count. Explore shadows count too: exploration buys
    information without touching equity, but it still needs a cap so the
    shadow book does not drown the journal in noise forever.
    """
    path = paper_trades_path(project_root)
    if not path.is_file():
        return 0
    n = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if row.get("live"):
                n += 1
                continue
            if row.get("shadow") and "explore" in str(row.get("policy") or row.get("source") or ""):
                n += 1
    except OSError:
        return 0
    return n


def explore_baseline_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "explore_baseline.json"


def load_explore_baseline(project_root: str | Path) -> int:
    path = explore_baseline_path(project_root)
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(data, dict):
        return max(0, int(data.get("baseline") or 0))
    return 0


def save_explore_baseline(project_root: str | Path, baseline: int) -> Path:
    path = explore_baseline_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"baseline": max(0, int(baseline)), "total_live_at_reset": count_live_labels(project_root)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def reset_explore_counter(project_root: str | Path) -> dict[str, Any]:
    """Zero the explore session counter without deleting paper trades.

    Sets baseline = current total live labels so cap counts only new labels after reset.
    """
    total = count_live_labels(project_root)
    save_explore_baseline(project_root, total)
    return {
        "ok": True,
        "baseline": total,
        "session_live": 0,
        "total_live": total,
    }


def count_explore_session_labels(project_root: str | Path) -> int:
    """Live labels counted toward explore cap (after optional reset baseline)."""
    total = count_live_labels(project_root)
    baseline = load_explore_baseline(project_root)
    return max(0, total - baseline)


def resolve_explore_enabled(
    project_root: str | Path,
    *,
    explore: bool,
    explore_live_cap: int | None = DEFAULT_EXPLORE_LIVE_CAP,
) -> dict[str, Any]:
    """Whether explore should run given live-label cap.

    ``explore_live_cap`` <= 0 means unlimited.
    Cap uses session live (= total − explore baseline), not raw history size.
    """
    total = count_live_labels(project_root)
    session = count_explore_session_labels(project_root)
    if not explore:
        return {
            "enabled": False,
            "reason": "off",
            "live": session,
            "total_live": total,
            "cap": explore_live_cap,
        }
    cap = DEFAULT_EXPLORE_LIVE_CAP if explore_live_cap is None else int(explore_live_cap)
    if cap <= 0:
        return {
            "enabled": True,
            "reason": "unlimited",
            "live": session,
            "total_live": total,
            "cap": 0,
        }
    if session >= cap:
        return {
            "enabled": False,
            "reason": "cap",
            "live": session,
            "total_live": total,
            "cap": cap,
        }
    return {
        "enabled": True,
        "reason": "below_cap",
        "live": session,
        "total_live": total,
        "cap": cap,
    }


def open_paper_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "open_paper.json"


# After model-exit, block same (symbol, market, side) reentry for N×1m bars.
# Stops close→immediate reopen churn that double-pays fees and cuts leftover MFE.
DEFAULT_REENTRY_COOLDOWN_BARS_1M = 20
# After SL — longer same-side block to stop soft re-entry churn (overnight SL carousel).
DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M = 40
_MS_PER_1M_BAR = 60_000


def reentry_cooldown_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "reentry_cooldown.json"


def _cooldown_key(symbol: str, market: str, side: str) -> str:
    return f"{str(symbol).upper()}|{normalize_market(market)}|{str(side).upper()}"


def load_reentry_cooldowns(project_root: str | Path, *, now_ts_ms: int | None = None) -> dict[str, dict[str, Any]]:
    path = reentry_cooldown_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    now = int(now_ts_ms) if now_ts_ms is not None else None
    out: dict[str, dict[str, Any]] = {}
    for key, row in raw.items():
        if not isinstance(row, dict):
            continue
        until = int(row.get("until_ts") or 0)
        if now is not None and until <= now:
            continue
        out[str(key)] = row
    return out


def save_reentry_cooldowns(project_root: str | Path, entries: dict[str, dict[str, Any]]) -> Path:
    path = reentry_cooldown_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def register_reentry_cooldown(
    project_root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    exit_ts_ms: int,
    bars_1m: int = DEFAULT_REENTRY_COOLDOWN_BARS_1M,
    exit_reason: str = "model",
) -> dict[str, Any]:
    """Arm same-side reentry block after a model (or explicit) exit."""
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        return {}
    bars = max(1, int(bars_1m))
    until = int(exit_ts_ms) + bars * _MS_PER_1M_BAR
    entries = load_reentry_cooldowns(project_root, now_ts_ms=int(exit_ts_ms))
    row = {
        "symbol": str(symbol).upper(),
        "market": normalize_market(market),
        "side": side_u,
        "until_ts": until,
        "exit_ts": int(exit_ts_ms),
        "bars_1m": bars,
        "exit_reason": str(exit_reason or "model"),
    }
    entries[_cooldown_key(symbol, market, side_u)] = row
    save_reentry_cooldowns(project_root, entries)
    return row


def reentry_cooldown_active(
    project_root: str | Path,
    *,
    symbol: str,
    market: str,
    side: str,
    now_ts_ms: int,
) -> dict[str, Any] | None:
    """Return active cooldown row for (symbol, market, side), else None."""
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        return None
    entries = load_reentry_cooldowns(project_root, now_ts_ms=int(now_ts_ms))
    row = entries.get(_cooldown_key(symbol, market, side_u))
    if not row:
        return None
    until = int(row.get("until_ts") or 0)
    if until <= int(now_ts_ms):
        return None
    return row


def load_open_positions(project_root: str | Path) -> list[dict[str, Any]]:
    path = open_paper_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        rows: list[Any] = data
    elif isinstance(data, dict):
        raw = data.get("positions")
        rows = raw if isinstance(raw, list) else []
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


def save_open_positions(project_root: str | Path, positions: list[dict[str, Any]]) -> Path:
    path = open_paper_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"positions": positions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep paper bankroll margin in sync with opens.
    try:
        port = ensure_portfolio(project_root)
        port["margin_used_usdt"] = recompute_margin_used(positions)
        save_portfolio(project_root, port)
    except Exception:
        pass
    return path


def shadow_open_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "shadow_open.json"


def load_shadow_positions(project_root: str | Path) -> list[dict[str, Any]]:
    """Open shadow probes (cost-gate rejects and explore) — labels only, no money."""
    path = shadow_open_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("positions") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [dict(r, shadow=True) for r in rows if isinstance(r, dict)]


def save_shadow_positions(project_root: str | Path, positions: list[dict[str, Any]]) -> Path:
    """Shadow book never touches equity or margin — it only feeds learning."""
    path = shadow_open_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = positions[-MAX_SHADOW_OPEN:] if len(positions) > MAX_SHADOW_OPEN else positions
    path.write_text(
        json.dumps({"positions": trimmed}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _attach_size_fields(target: dict[str, Any], size: Mapping[str, Any]) -> None:
    target["margin_usdt"] = float(size.get("margin_usdt") or 0.0)
    target["notional_usdt"] = float(size.get("notional_usdt") or 0.0)
    target["leverage"] = float(size.get("leverage") or 1.0)
    tag = str(size.get("size_tag") or "").strip()
    if tag:
        target["size_tag"] = tag
    if size.get("soft_entry"):
        try:
            target["soft_margin_scale"] = float(size.get("soft_margin_scale") or 1.0)
        except (TypeError, ValueError):
            target["soft_margin_scale"] = 1.0


def _portfolio_for_sizing(project_root: str | Path) -> dict[str, Any]:
    """Equity snapshot with open + pending margin counted toward the risk budget."""
    port = dict(ensure_portfolio(project_root))
    used = float(port.get("margin_used_usdt") or 0.0)
    for o in load_pending_orders(project_root):
        if str(o.get("status") or "pending") != "pending":
            continue
        if o.get("shadow"):
            continue  # shadow pendings never reserve live margin
        try:
            used += max(0.0, float(o.get("margin_usdt") or 0.0))
        except (TypeError, ValueError):
            continue
    port["margin_used_usdt"] = used
    return port

def drop_orphan_opens(
    project_root: str | Path,
    *,
    keep_keys: set[tuple[str, str]] | None = None,
    spot_symbols: Sequence[str] | None = None,
    futures_symbols: Sequence[str] | None = None,
    markets: Sequence[str] | str | None = None,
) -> dict[str, Any]:
    """Remove open paper positions that are outside the active Spot/Futures lists.

    Does not write trade labels — hard drop. Use when leftover opens confuse the log.
    """
    if keep_keys is None:
        if isinstance(markets, str):
            kinds = parse_markets(markets)
        elif markets is None:
            kinds = ("spot", "futures")
        else:
            kinds = tuple(normalize_market(m) for m in markets) or ("spot", "futures")
        keys: set[tuple[str, str]] = set()
        if "spot" in kinds:
            for s in spot_symbols or ():
                u = str(s or "").strip().upper()
                if u:
                    keys.add((u, "spot"))
        if "futures" in kinds:
            for s in futures_symbols or ():
                u = str(s or "").strip().upper()
                if u:
                    keys.add((u, "futures"))
        keep_keys = keys

    opens = load_open_positions(project_root)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for p in opens:
        u = str(p.get("symbol") or "").strip().upper()
        mk = _pos_market(p)
        if u and (u, mk) in keep_keys:
            kept.append(p)
        else:
            dropped.append({"symbol": u, "market": mk, "action": p.get("action"), "entry": p.get("entry")})
    save_open_positions(project_root, kept)
    return {
        "ok": True,
        "kept": len(kept),
        "dropped": len(dropped),
        "dropped_positions": dropped,
        "path": str(open_paper_path(project_root)),
    }

def trim_candles(
    project_root: str | Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    max_keep: int = DEFAULT_MAX_KEEP,
    market: str | None = DEFAULT_MARKET,
) -> int:
    """Drop old candles; keep last max_keep. Returns remaining count."""
    kind = normalize_market(market)
    candles = load_candles(project_root, symbol, interval, market=kind)
    keep = max(8, int(max_keep))
    if len(candles) <= keep:
        return len(candles)
    trimmed = candles[-keep:]
    save_candles(project_root, trimmed, symbol=symbol, interval=interval, market=kind)
    return len(trimmed)


def _pos_market(pos: dict[str, Any]) -> MarketKind:
    """Open-position market tag; legacy rows without tag are spot."""
    return normalize_market(str(pos.get("market") or DEFAULT_MARKET))


def _sym_label(symbol: str, market: str) -> str:
    kind = normalize_market(market)
    if kind == "futures":
        return f"{symbol} fut"
    return symbol


def _append_learn_events(events: list[dict[str, Any]], root: Path, *, epochs: int) -> None:
    trained = train_market_policy(root, epochs=int(epochs))
    if trained.get("ok"):
        events.append(
            {
                "kind": "learn",
                "message": (
                    f"дообучение входа: примеров={trained.get('samples')}, "
                    f"точность={trained.get('train_accuracy')}, "
                    f"устройство={trained.get('device')}"
                ),
            }
        )
    else:
        events.append(
            {
                "kind": "learn",
                "message": f"дообучение входа пропущено: {trained.get('error')}",
            }
        )
    trained_x = train_market_exit_policy(root, epochs=int(epochs))
    if trained_x.get("ok"):
        events.append(
            {
                "kind": "learn",
                "message": (
                    f"дообучение выхода: примеров={trained_x.get('samples')}, "
                    f"точность={trained_x.get('train_accuracy')}, "
                    f"устройство={trained_x.get('device')}"
                ),
            }
        )
    else:
        events.append(
            {
                "kind": "learn",
                "message": f"дообучение выхода пропущено: {trained_x.get('error')}",
            }
        )
    trained_l = train_market_levels_policy(root, epochs=int(epochs))
    if trained_l.get("ok"):
        events.append(
            {
                "kind": "learn",
                "message": (
                    f"дообучение уровней TP/SL/trail: примеров={trained_l.get('samples')}, "
                    f"mae={trained_l.get('train_mae')}, "
                    f"устройство={trained_l.get('device')}"
                ),
            }
        )
    else:
        events.append(
            {
                "kind": "learn",
                "message": f"дообучение уровней пропущено: {trained_l.get('error')}",
            }
        )
    trained_s = train_entry_style_policy(root, epochs=int(epochs))
    if trained_s.get("ok"):
        events.append(
            {
                "kind": "learn",
                "message": (
                    f"дообучение стиля входа: примеров={trained_s.get('samples')}, "
                    f"точность={trained_s.get('train_accuracy')}, "
                    f"устройство={trained_s.get('device')}"
                ),
            }
        )
    else:
        events.append(
            {
                "kind": "learn",
                "message": f"дообучение стиля входа пропущено: {trained_s.get('error')}",
            }
        )
    gate = calibrate_cost_gate(root)
    if gate.get("calibrated"):
        events.append(
            {
                "kind": "learn",
                "message": (
                    f"стоимостные ворота: расширение ≥ {float(gate['expansion_min']):+.2f}, "
                    f"ожидаемый эдж={100 * float(gate['expected_edge']):.3f}% "
                    f"(×{float(gate['cost_mult']):.2f} комиссии, примеров={gate.get('samples')})"
                ),
            }
        )
    else:
        events.append(
            {
                "kind": "learn",
                "message": (
                    "стоимостные ворота: калибровка не нашла порога, окупающего комиссию — "
                    f"держим запасной ≥ {float(gate['expansion_min']):+.2f} "
                    f"(просмотрено сделок: {gate.get('scanned')})"
                ),
            }
        )


def _append_paper_row(project_root: str | Path, row: dict[str, Any]) -> None:
    path = paper_trades_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _candle_index_by_open_time(candles: list[dict[str, Any]], open_time: int) -> int:
    for i, c in enumerate(candles):
        if int(c["open_time"]) == int(open_time):
            return i
    return -1


_KIND_RU = {
    "sync": "синхронизация",
    "analysis": "анализ",
    "paper": "сделка",
    "hold": "ожидание",
    "wait": "горизонт",
    "outcome": "итог",
    "learn": "обучение",
    "explore": "исследование",
    "skip": "пропуск",
    "error": "ошибка",
    "info": "инфо",
}

_SOURCE_RU = {
    "model": "модель",
    "momentum": "импульс",
    "live": "live",
    "custom": "своя",
}

_ACTION_RU = {
    "BUY": "ПОКУПКА",
    "SELL": "ПРОДАЖА",
    "HOLD": "ДЕРЖАТЬ",
}


def action_ru(action: str) -> str:
    return _ACTION_RU.get((action or "").upper(), action or "?")


def source_ru(source: str) -> str:
    key = (source or "").lower()
    if key.startswith("explore/"):
        base = key.split("/", 1)[1]
        return f"исследование/{_SOURCE_RU.get(base, base)}"
    if key.endswith("/soft"):
        base = key[: -len("/soft")]
        return f"{_SOURCE_RU.get(base, base)}/мягкий"
    return _SOURCE_RU.get(key, source or "?")


def _action_ru(action: str) -> str:
    return action_ru(action)


def _source_ru(source: str) -> str:
    return source_ru(source)


def format_market_event(event: dict[str, Any]) -> str:
    """Human line for Market log (Russian, no HTML)."""
    kind = str(event.get("kind") or "info")
    label = _KIND_RU.get(kind, kind)
    msg = str(event.get("message") or "")
    return f"{label}: {msg}"


def pick_explore_action(
    pred: dict[str, Any],
    features: Sequence[float],
    *,
    rng: Optional[Any] = None,
) -> str:
    """Choose BUY or SELL for exploration (never HOLD)."""
    _rng = rng if rng is not None else random
    probs = pred.get("probs") if isinstance(pred.get("probs"), dict) else None
    if probs:
        buy_p = float(probs.get("BUY") or 0.0)
        sell_p = float(probs.get("SELL") or 0.0)
        total = buy_p + sell_p
        if total > 1e-9:
            return "BUY" if _rng.random() < (buy_p / total) else "SELL"
    from eurika.ml.paper_trader import momentum_policy

    mom = momentum_policy(features)
    if mom in ("BUY", "SELL"):
        return mom
    ret1 = float(features[0]) if features else 0.0
    return "BUY" if ret1 >= 0 else "SELL"


def run_live_tick(
    project_root: str | Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    window: int = DEFAULT_WINDOW,
    horizon: int = DEFAULT_LIVE_HORIZON,
    fee: float | None = None,
    thr: float = DEFAULT_THR,
    sync_limit: int = DEFAULT_SYNC_LIMIT,
    max_keep: int = DEFAULT_MAX_KEEP,
    micro_train: bool = True,
    train_epochs: int = 15,
    explore: bool = True,
    explore_rate: float = DEFAULT_EXPLORE_RATE,
    explore_when_idle: bool = True,
    explore_live_cap: int | None = DEFAULT_EXPLORE_LIVE_CAP,
    allow_open: bool = True,
    market: str | None = DEFAULT_MARKET,
    exec_interval: str | None = None,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    trail_pct: float = DEFAULT_TRAIL_PCT,
    rng: Optional[Any] = None,
    fetch: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """One live paper cycle. Returns {ok, events, opens, resolved, suggestion, error?}."""
    events: list[dict[str, Any]] = []
    root = Path(project_root).resolve()
    sym = (symbol or DEFAULT_SYMBOL).strip().upper()
    iv = (interval or DEFAULT_INTERVAL).strip()
    kind = normalize_market(market)
    label = _sym_label(sym, kind)
    fee_override = float(fee) if fee is not None else None
    gate_fee = fee_override if fee_override is not None else fee_for_market(kind)
    w = max(8, int(window))
    h = max(1, int(horizon))
    if exec_interval is None:
        exec_interval = DEFAULT_EXEC_INTERVAL
    exec_iv = (exec_interval or "").strip()
    use_exec = bool(exec_iv)
    tp = max(0.0, float(tp_pct))
    sl = max(0.0, float(sl_pct))
    trail = max(0.0, float(trail_pct))

    explore_gate = resolve_explore_enabled(root, explore=explore, explore_live_cap=explore_live_cap)
    explore_eff = bool(explore_gate.get("enabled"))
    if (
        allow_open
        and explore
        and not explore_eff
        and explore_gate.get("reason") == "cap"
    ):
        events.append(
            {
                "kind": "info",
                "message": (
                    f"исследование выкл: live-меток {explore_gate.get('live')} "
                    f"≥ порога {explore_gate.get('cap')} — доверяем модели"
                ),
            }
        )
    sync = sync_klines(root, symbol=sym, interval=iv, limit=int(sync_limit), market=kind, fetch=fetch)
    if not sync.get("ok"):
        err = sync.get("error") or "сбой синхронизации"
        events.append({"kind": "error", "message": f"синхронизация не удалась ({label}): {err}"})
        return {
            "ok": False,
            "events": events,
            "opens": 0,
            "resolved": 0,
            "suggestion": None,
            "market": kind,
            "error": err,
        }

    keep = max(int(max_keep), w + h + 8)
    kept = trim_candles(root, symbol=sym, interval=iv, max_keep=keep, market=kind)
    added = int(sync.get("added") or 0)
    if added > 0:
        events.append(
            {
                "kind": "sync",
                "message": f"{label} {iv}: добавлено={added}, храним={kept}, горизонт={h}",
            }
        )

    candles_exec: list[dict[str, Any]] = []
    added_exec = 0
    if use_exec:
        h_exec_guess = main_horizon_to_exec(h, iv, exec_iv)
        sync_e = sync_klines(
            root,
            symbol=sym,
            interval=exec_iv,
            limit=max(int(DEFAULT_EXEC_SYNC_LIMIT), h_exec_guess + 40),
            market=kind,
            fetch=fetch,
        )
        if sync_e.get("ok"):
            keep_e = max(int(DEFAULT_EXEC_MAX_KEEP), h_exec_guess + 60)
            kept_e = trim_candles(root, symbol=sym, interval=exec_iv, max_keep=keep_e, market=kind)
            candles_exec = load_candles(root, sym, exec_iv, market=kind)
            added_exec = int(sync_e.get("added") or 0)
            if added_exec > 0:
                events.append(
                    {
                        "kind": "sync",
                        "message": (
                            f"{label} {exec_iv} (исполнение): добавлено={added_exec}, храним={kept_e}, "
                            f"потолок UI TP={tp:.2%} SL={sl:.2%} trail={trail:.2%}"
                        ),
                    }
                )
        else:
            events.append(
                {
                    "kind": "info",
                    "message": (
                        f"{label}: {exec_iv} недоступен ({sync_e.get('error')}) — "
                        f"выход по close {iv}"
                    ),
                }
            )
            use_exec = False

    candles = load_candles(root, sym, iv, market=kind)
    if len(candles) < w:
        msg = f"нужно ≥ {w} свечей для признаков ({label}), есть {len(candles)}"
        events.append({"kind": "error", "message": msg})
        return {
            "ok": False,
            "events": events,
            "opens": 0,
            "resolved": 0,
            "suggestion": None,
            "market": kind,
            "error": msg,
        }

    opens = load_open_positions(root)
    # Shadow book loads before pending fills so OCO/limit fills can land here.
    shadows = load_shadow_positions(root)

    # Fill / cancel pending entries on 1m before resolving opens.
    if use_exec and candles_exec:
        pend = process_pending_orders(
            root,
            symbol=sym,
            market=kind,
            candles_exec=candles_exec,
            append_cancel_row=lambda row: _append_paper_row(root, row),
        )
        events.extend(pend.get("events") or [])
        live_filled = False
        shadow_filled = False
        for pos in pend.get("filled_positions") or []:
            if pos.get("shadow"):
                shadows.append(pos)
                shadow_filled = True
            else:
                opens.append(pos)
                live_filled = True
        if live_filled:
            save_open_positions(root, opens)
        if shadow_filled:
            save_shadow_positions(root, shadows)
    # Shadow entries ride the same resolution machinery, so their outcome is
    # measured exactly like a real one — only money and cooldowns are skipped.
    still_open: list[dict[str, Any]] = []
    still_shadow: list[dict[str, Any]] = []
    resolved = 0
    shadow_resolved = 0
    waiting = 0
    for pos in opens + shadows:
        is_shadow = bool(pos.get("shadow"))
        keep_open = still_shadow if is_shadow else still_open
        if str(pos.get("symbol") or "").upper() != sym or _pos_market(pos) != kind:
            keep_open.append(pos)
            continue
        entry_ts = int(pos.get("ts") or 0)
        pos_h = max(1, int(pos.get("horizon") or h))
        entry = float(pos.get("entry") or 0.0)
        action = str(pos.get("action") or "").upper()
        pos_exec = str(pos.get("exec_interval") or "").strip()
        # Model exits cross the spread, so use the entry fill + taker exit cost
        # when deciding whether unrealized edge is worth banking.
        pos_fee_taker = (
            fee_override
            if fee_override is not None
            else float(
                commission_breakdown(
                    kind,
                    entry_style=pos.get("entry_style"),
                    fill_leg=pos.get("fill_leg"),
                    exit_reason="model",
                )["fee"]
            )
        )
        # Legacy opens (до dual-TF): подключить 1m TP/SL/trail на текущем тике.
        if use_exec and candles_exec and not pos_exec:
            pos["exec_interval"] = exec_iv
            pos_exec = exec_iv
            if pos.get("tp_pct") is None:
                pos["tp_pct"] = tp
            if pos.get("sl_pct") is None:
                pos["sl_pct"] = sl
            if pos.get("trail_pct") is None and trail > 0:
                pos["trail_pct"] = trail
            if pos.get("horizon_exec") is None:
                pos["horizon_exec"] = main_horizon_to_exec(pos_h, iv, exec_iv)
            if pos.get("trail_pct") and not pos.get("trail_extreme") and entry > 0:
                pos["trail_extreme"] = entry
            if not pos.get("entry_style"):
                pos["entry_style"] = "market"
            pos["levels_source"] = pos.get("levels_source") or "legacy_migrate"
        pos_use_exec = bool(pos_exec) and bool(candles_exec)

        exit_px: float | None = None
        exit_ts: int | None = None
        exit_reason = "horizon"
        bars_held_1m = 0

        now_ts_ms = (
            int(candles_exec[-1]["open_time"])
            if (pos_use_exec and candles_exec)
            else int(candles[-1]["open_time"])
        )
        stale_why = stale_force_close_reason(
            pos,
            now_ts_ms=now_ts_ms,
            interval=iv,
            horizon=h,
            candles_exec=candles_exec if pos_use_exec else None,
        )
        if stale_why:
            # Entry scrolled out of the 1m window or lived past N×horizon — free
            # margin and write a label instead of waiting forever.
            if pos_use_exec and candles_exec:
                exit_px = float(candles_exec[-1]["close"])
                exit_ts = int(candles_exec[-1]["open_time"])
            else:
                exit_px = float(candles[-1]["close"])
                exit_ts = int(candles[-1]["open_time"])
            exit_reason = stale_why
            if entry <= 0:
                entry = float(pos.get("entry") or exit_px)
            bars_held_1m = max(0, int((int(exit_ts) - int(entry_ts)) // 60_000))
        elif pos_use_exec:
            h_exec = max(
                1,
                int(pos.get("horizon_exec") or main_horizon_to_exec(pos_h, iv, pos_exec)),
            )
            pos_tp = float(pos.get("tp_pct") or 0.0)
            pos_sl = float(pos.get("sl_pct") or 0.0)
            entry_px = entry if entry > 0 else float(candles_exec[-1]["close"])
            sim = simulate_exec_exit(
                candles_exec,
                entry_ts=entry_ts,
                entry=entry_px,
                action=action,
                horizon_exec=h_exec,
                tp_pct=pos_tp,
                sl_pct=pos_sl,
                trail_pct=float(pos.get("trail_pct") or 0.0),
                trail_extreme=float(pos["trail_extreme"])
                if pos.get("trail_extreme")
                else None,
            )
            if sim is None or not sim.get("ready"):
                # Soft early exit: model CLOSE if unrealized edge ≥ half TP (safety still TP/SL).
                closed_by_model = False
                if sim and sim.get("trail_extreme") is not None:
                    pos["trail_extreme"] = sim["trail_extreme"]
                evec = exit_feature_vector(
                    candles_exec,
                    entry_ts=entry_ts,
                    entry=entry_px,
                    action=action,
                    horizon_exec=h_exec,
                    tp_pct=pos_tp,
                    sl_pct=pos_sl,
                    fee=pos_fee_taker,
                )
                if evec is not None:
                    unreal = float(evec[1])
                    pred_x = predict_exit(root, evec)
                    mfe_now = 0.0
                    if sim and sim.get("trail_extreme") is not None and entry_px > 0:
                        ex = float(sim["trail_extreme"])
                        if action == "BUY":
                            mfe_now = (ex - entry_px) / entry_px
                        else:
                            mfe_now = (entry_px - ex) / entry_px if ex > 0 else 0.0
                    if should_model_exit(pred_x, unreal, pos_tp, mfe_pct=mfe_now):
                        exit_px = float(candles_exec[-1]["close"])
                        exit_ts = int(candles_exec[-1]["open_time"])
                        exit_reason = "model"
                        entry = entry_px
                        closed_by_model = True
                        if sim and sim.get("bars_held") is not None:
                            bars_held_1m = int(sim["bars_held"])
                        elif entry_ts and exit_ts:
                            bars_held_1m = max(0, int((int(exit_ts) - int(entry_ts)) // 60_000))
                if not closed_by_model:
                    keep_open.append(pos)
                    if is_shadow:
                        continue
                    waiting += 1
                    if (added > 0 or added_exec > 0) and sim:
                        events.append(
                            {
                                "kind": "wait",
                                "message": (
                                    f"{label} {_action_ru(action)} @ {pos.get('entry')} — "
                                    f"ждём {pos_exec}: ещё ~{sim.get('left')} бар "
                                    f"(TP/SL/trail или горизонт {h_exec}×{pos_exec}, "
                                    f"прогресс ≈{sim.get('bars_held')}/{h_exec})"
                                ),
                            }
                        )
                    elif added > 0 or added_exec > 0:
                        events.append(
                            {
                                "kind": "wait",
                                "message": (
                                    f"{label} {_action_ru(action)} @ {pos.get('entry')} — "
                                    f"ждём исполнение на {pos_exec}"
                                ),
                            }
                        )
                    continue
            else:
                exit_px = float(sim["exit"])
                exit_ts = int(sim["exit_ts"])
                exit_reason = str(sim.get("reason") or "horizon")
                entry = entry_px
                bars_held_1m = int(sim.get("bars_held") or 0)
                if sim.get("trail_extreme") is not None:
                    pos["trail_extreme"] = sim["trail_extreme"]
        else:
            idx = _candle_index_by_open_time(candles, entry_ts)
            if idx < 0 or idx + pos_h >= len(candles):
                keep_open.append(pos)
                if is_shadow:
                    continue
                waiting += 1
                if added > 0:
                    age = len(candles) - 1 - idx if idx >= 0 else "?"
                    left: Any = "?" if idx < 0 else max(0, pos_h - (len(candles) - 1 - idx))
                    events.append(
                        {
                            "kind": "wait",
                            "message": (
                                f"{label} {_action_ru(str(pos.get('action')))} @ {pos.get('entry')} — "
                                f"ждём ещё ~{left} свеч. (горизонт {pos_h}, прогресс ≈{age}/{pos_h})"
                            ),
                        }
                    )
                continue
            exit_px = float(candles[idx + pos_h]["close"])
            exit_ts = int(candles[idx + pos_h]["open_time"])
            bars_held_1m = max(1, int(pos_h) * (15 if iv == "15m" else 60 if iv == "1h" else 1))
            if entry <= 0:
                entry = float(pos.get("entry") or candles[idx]["close"])

        if entry <= 0 or exit_px is None or exit_ts is None:
            keep_open.append(pos)
            continue

        fund_info: dict[str, Any] = {
            "funding": 0.0,
            "source": "none",
            "n_settlements": 0,
            "last_funding_rate": None,
        }
        if kind == "futures":
            raw_f = _fetch_futures_funding(sym, entry_ts_ms=int(entry_ts), exit_ts_ms=int(exit_ts))
            fund_info = resolve_funding_edge(
                action,
                entry_ts_ms=int(entry_ts),
                exit_ts_ms=int(exit_ts),
                bars_held_1m=bars_held_1m,
                settlements=raw_f.get("settlements"),
                last_funding_rate=raw_f.get("last_funding_rate"),
            )
        fund = float(fund_info.get("funding") or 0.0)
        commission = commission_breakdown(
            kind,
            entry_style=pos.get("entry_style"),
            fill_leg=pos.get("fill_leg"),
            exit_reason=exit_reason,
        )
        trade_fee = fee_override if fee_override is not None else float(commission["fee"])
        lab = label_trade(entry, exit_px, action, fee=trade_fee, thr=thr, funding=fund)
        path_candles = candles_exec if pos_use_exec else candles
        exc = path_excursions(
            path_candles,
            entry_ts=entry_ts,
            entry=entry,
            action=action,
            exit_ts=exit_ts,
        )
        margin_usdt = float(pos.get("margin_usdt") or 0.0)
        notional_usdt = float(pos.get("notional_usdt") or 0.0)
        leverage = float(pos.get("leverage") or 1.0)
        pnl_usdt = 0.0
        if not is_shadow and (notional_usdt > 0 or margin_usdt > 0):
            closed_port = apply_close(
                root,
                margin_usdt=margin_usdt,
                edge=float(lab["edge"]),
                notional_usdt=notional_usdt,
            )
            pnl_usdt = float(closed_port.get("pnl_usdt") or 0.0)
        row = {
            "ts": entry_ts,
            "exit_ts": exit_ts,
            "symbol": sym,
            "interval": iv,
            "market": kind,
            "action": action,
            "entry": entry,
            "exit": exit_px,
            "ret": lab["ret"],
            "edge": lab["edge"],
            "correct": lab["correct"],
            "horizon": pos_h,
            "fee": trade_fee,
            "fee_source": "override" if fee_override is not None else "maker_taker",
            "entry_fee": None if fee_override is not None else commission["entry_fee"],
            "exit_fee": None if fee_override is not None else commission["exit_fee"],
            "entry_liquidity": commission["entry_liquidity"],
            "exit_liquidity": commission["exit_liquidity"],
            "funding": fund if abs(fund) > 1e-15 else None,
            "funding_source": fund_info.get("source") if kind == "futures" else None,
            "funding_rate": fund_info.get("last_funding_rate") if kind == "futures" else None,
            "funding_n": fund_info.get("n_settlements") if kind == "futures" else None,
            "features": pos.get("features") or {},
            "feature_vec": pos.get("feature_vec") or [],
            "policy": pos.get("source") or "live",
            "live": not is_shadow,
            "shadow": True if is_shadow else None,
            "gate_expansion": pos.get("gate_expansion") if is_shadow else None,
            "exit_reason": exit_reason,
            "exec_interval": pos_exec or None,
            "tp_pct": pos.get("tp_pct"),
            "sl_pct": pos.get("sl_pct"),
            "trail_pct": pos.get("trail_pct"),
            "entry_style": pos.get("entry_style") or "market",
            "fill_leg": pos.get("fill_leg"),
            "mfe_pct": exc.get("mfe_pct"),
            "mae_pct": exc.get("mae_pct"),
            "entry_timing_score": exc.get("entry_timing_score"),
            "margin_usdt": margin_usdt or None,
            "notional_usdt": notional_usdt or None,
            "leverage": leverage if notional_usdt > 0 else None,
            "pnl_usdt": pnl_usdt if (not is_shadow and (notional_usdt > 0 or margin_usdt > 0)) else None,
        }
        _append_paper_row(root, row)
        if pos_use_exec and candles_exec:
            samples = retro_exit_samples(
                candles_exec,
                entry_ts=entry_ts,
                entry=entry,
                action=action,
                exit_ts=int(exit_ts),
                horizon_exec=max(
                    1,
                    int(pos.get("horizon_exec") or main_horizon_to_exec(pos_h, iv, pos_exec)),
                ),
                tp_pct=float(pos.get("tp_pct") or 0.0),
                sl_pct=float(pos.get("sl_pct") or 0.0),
                # Every retro candidate is a possible model CLOSE, so train on
                # the same taker-exit cost used by online exit inference. The
                # final realized trade may have exited by maker TP instead.
                fee=pos_fee_taker,
                meta={"symbol": sym, "market": kind, "interval": iv},
            )
            append_exit_samples(root, samples)
            # Hindsight teacher for entry style (best fill among market/limit/stop/oco).
            sig_px = None
            raw_sig = pos.get("signal_px")
            if raw_sig is not None:
                try:
                    sig_px = float(raw_sig)
                except (TypeError, ValueError):
                    sig_px = None
            if sig_px is None or sig_px <= 0:
                sig_px = float(entry)
            signal_ts_style = int(pos.get("signal_ts") or entry_ts)
            h_pend = max(
                1,
                int(
                    pos.get("pending_horizon_exec")
                    or max(1, int(pos.get("horizon_exec") or 60) // 2)
                ),
            )
            teacher = retro_best_entry_style(
                action=action,
                signal_px=sig_px,
                candles_exec=candles_exec,
                signal_ts=signal_ts_style,
                pending_horizon_exec=h_pend,
            )
            if teacher.get("style"):
                append_style_samples(
                    root,
                    [
                        {
                            "kind": "style_sample",
                            "style_label": teacher["style"],
                            "style_score": teacher.get("score"),
                            "style_reason": teacher.get("reason"),
                            "feature_vec": pos.get("feature_vec") or [],
                            "features": pos.get("features") or {},
                            "symbol": sym,
                            "market": kind,
                            "action": action,
                            "signal_px": sig_px,
                            "entry": entry,
                            "used_style": pos.get("entry_style") or "market",
                        }
                    ],
                )
        if is_shadow:
            # Label recorded, exit/style samples collected — no money, no cooldown,
            # and no journal line, or the feed would drown in trades we never took.
            shadow_resolved += 1
            continue
        resolved += 1
        outcome = "удача" if lab["correct"] else "неудача"
        pnl = "прибыль" if lab["edge"] > 0 else "убыток"
        reason_ru = {
            "tp": "TP",
            "sl": "SL",
            "trail": "трейлинг",
            "horizon": "горизонт",
            "time_stop": "time-stop",
            "model": "модель",
            "max_age": "max-age (N×горизонт)",
            "stale": "stale (вход выпал из окна)",
        }.get(exit_reason, exit_reason)
        events.append(
            {
                "kind": "outcome",
                "message": (
                    f"{label} {_action_ru(action)} → {outcome} ({pnl}): "
                    f"edge={lab['edge']:+.4%}, ret={lab['ret']:+.4%}, "
                    f"вход={entry:.4f}, выход={exit_px:.4f}, причина={reason_ru}, "
                    f"MFE={float(exc.get('mfe_pct') or 0):+.3%}"
                    + (
                        f", fee={trade_fee:.4%}"
                        f"[{commission['entry_liquidity']}+{commission['exit_liquidity']}]"
                        + (
                            f", fund={fund:+.4%}[{fund_info.get('source')}]"
                            if kind == "futures"
                            else ""
                        )
                    )
                    + (f", PnL={pnl_usdt:+.2f} USDT" if (notional_usdt > 0 or margin_usdt > 0) else "")
                ),
                "correct": lab["correct"],
                "edge": lab["edge"],
                "pnl_usdt": pnl_usdt if (notional_usdt > 0 or margin_usdt > 0) else None,
                "fee": trade_fee,
                "fee_source": "override" if fee_override is not None else "maker_taker",
                "entry_fee": None if fee_override is not None else commission["entry_fee"],
                "exit_fee": None if fee_override is not None else commission["exit_fee"],
                "entry_liquidity": commission["entry_liquidity"],
                "exit_liquidity": commission["exit_liquidity"],
                "entry_style": pos.get("entry_style") or "market",
                "fill_leg": pos.get("fill_leg"),
                "reason": exit_reason,
                "exit_reason": exit_reason,
                "bar_ts": int(exit_ts) if exit_ts is not None else None,
                "symbol": sym,
                "market": kind,
                "action": action,
            }
        )
        if exit_reason == "model":
            cd = register_reentry_cooldown(
                root,
                symbol=sym,
                market=kind,
                side=action,
                exit_ts_ms=int(exit_ts),
                bars_1m=DEFAULT_REENTRY_COOLDOWN_BARS_1M,
                exit_reason="model",
            )
            left_m = max(1, int((int(cd.get("until_ts") or 0) - int(exit_ts)) // 60_000))
            events.append(
                {
                    "kind": "info",
                    "message": (
                        f"{label}: cooldown {_action_ru(action)} "
                        f"{DEFAULT_REENTRY_COOLDOWN_BARS_1M}×1m (~{left_m} мин) после выхода моделью"
                    ),
                }
            )
        elif exit_reason == "sl":
            cd = register_reentry_cooldown(
                root,
                symbol=sym,
                market=kind,
                side=action,
                exit_ts_ms=int(exit_ts),
                bars_1m=DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M,
                exit_reason="sl",
            )
            left_m = max(1, int((int(cd.get("until_ts") or 0) - int(exit_ts)) // 60_000))
            events.append(
                {
                    "kind": "info",
                    "message": (
                        f"{label}: cooldown {_action_ru(action)} "
                        f"{DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M}×1m (~{left_m} мин) после SL"
                    ),
                }
            )

    save_open_positions(root, still_open)
    if shadows or still_shadow:
        save_shadow_positions(root, still_shadow)

    vec = feature_vector(candles, window=w)
    feat = features_dict(candles, window=w) or {}
    if vec is None:
        events.append({"kind": "error", "message": f"не удалось посчитать признаки ({label})"})
        return {
            "ok": True,
            "events": events,
            "opens": len(still_open),
            "resolved": resolved,
            "suggestion": None,
            "market": kind,
            "error": None,
        }

    pred = soften_entry_action(predict_action(root, vec))
    action = str(pred.get("action") or "HOLD").upper()
    source = str(pred.get("source") or "momentum")
    suggestion: dict[str, Any] = {
        "action": action,
        "source": source,
        "entry": float(candles[-1]["close"]),
        "market": kind,
    }

    has_open = any(
        str(p.get("symbol") or "").upper() == sym and _pos_market(p) == kind for p in still_open
    )
    has_shadow = any(
        str(s.get("symbol") or "").upper() == sym and _pos_market(s) == kind for s in still_shadow
    )
    all_pending_here = [
        o
        for o in load_pending_orders(root)
        if str(o.get("symbol") or "").upper() == sym
        and _pos_market(o) == kind
        and str(o.get("status") or "pending") == "pending"
    ]
    # Live book must not see shadow pendings as blockers (and vice versa).
    pending_here = [o for o in all_pending_here if not o.get("shadow")]
    shadow_pending_here = [o for o in all_pending_here if o.get("shadow")]
    has_pending = bool(pending_here)
    has_shadow_pending = bool(shadow_pending_here)
    pend_sides = {str(o.get("action") or "").upper() for o in pending_here}
    shadow_pend_sides = {str(o.get("action") or "").upper() for o in shadow_pending_here}
    # Waiting on an open paper: no analysis/skip spam — wait/outcome already cover it.
    if has_open and waiting > 0 and resolved == 0:
        ms = model_status(root)
        return {
            "ok": True,
            "events": events,
            "opens": len(still_open),
            "resolved": resolved,
            "suggestion": suggestion,
            "model": ms,
            "symbol": sym,
            "interval": iv,
            "market": kind,
            "horizon": h,
            "error": None,
            "idle_wait": True,
        }

    if not allow_open:
        ms = model_status(root)
        if resolved == 0 and added == 0 and not events:
            pass
        elif not has_open and resolved == 0:
            events.append(
                {
                    "kind": "info",
                    "message": f"{label}: вне universe — только закрытие метки, новых сделок нет",
                }
            )
        return {
            "ok": True,
            "events": events,
            "opens": len(still_open),
            "resolved": resolved,
            "suggestion": suggestion,
            "model": ms,
            "symbol": sym,
            "interval": iv,
            "market": kind,
            "horizon": h,
            "error": None,
            "idle_wait": bool(has_open and resolved == 0 and added == 0),
        }

    rw = feat.get("ret_window", 0.0)
    probs = pred.get("probs") if isinstance(pred.get("probs"), dict) else None
    prob_s = ""
    if probs:
        prob_s = (
            f", P: держать={float(probs.get('HOLD', 0)):.2f} "
            f"покуп={float(probs.get('BUY', 0)):.2f} "
            f"прод={float(probs.get('SELL', 0)):.2f}"
        )
    burst = float(feat.get("atr_burst") or 0.0)
    brk = float(feat.get("range_break") or 0.0)
    rsi = float(feat.get("rsi_14") or 0.0)
    bb = float(feat.get("bb_pos") or 0.0)
    macd = float(feat.get("macd_hist") or 0.0)
    rsi_d = float(feat.get("rsi_delta") or 0.0)
    macd_d = float(feat.get("macd_hist_delta") or 0.0)
    bb_w = float(feat.get("bb_width") or 0.0)
    d_lo = float(feat.get("dist_to_low_40") or feat.get("dist_to_low_win") or 0.0)
    h_eff = impulse_horizon(h, feat)
    style_pred = predict_entry_style(root, feat if feat else vec, rng=rng)
    style_hint = str(style_pred.get("style") or "market")
    style_src = str(style_pred.get("source") or "heuristic")
    impulse_s = f", горизонт импульса={h_eff}" if h_eff > h else ""
    events.append(
        {
            "kind": "analysis",
            "message": (
                f"{label} окно={rw:+.3%}, волат={feat.get('volatility', 0):.4f}, "
                f"burst={burst:+.2f}, break={brk:+.4f}, "
                f"rsi={rsi:+.2f}(Δ{rsi_d:+.2f}), bb={bb:+.2f}, macd={macd:+.4f}(Δ{macd_d:+.4f}), "
                f"bb_w={bb_w:.4f}, dist_lo40={d_lo:.2f} → "
                f"совет: {_action_ru(action)} (источник: {_source_ru(source)}"
                f", вход≈{style_hint}/{style_src}){prob_s}{impulse_s}"
            ),
        }
    )

    last_ts = int(candles[-1]["open_time"])
    already_this_bar = any(
        int(p.get("signal_ts") or p.get("ts") or 0) == last_ts
        and str(p.get("symbol") or "").upper() == sym
        and _pos_market(p) == kind
        for p in still_open
    ) or any(
        int(o.get("signal_ts") or o.get("ts") or 0) == last_ts
        and str(o.get("symbol") or "").upper() == sym
        and _pos_market(o) == kind
        and not o.get("shadow")
        for o in load_pending_orders(root)
    )

    open_action = action
    open_source = source
    explored = False
    logged_hold = False
    # Side the cost gate refused; kept so it can still be shadowed for learning.
    shadow_action = ""
    # Same-side pending blocks; opposite-side can flip after setup/cooldown pass.
    flip_candidate = bool(
        open_action in ("BUY", "SELL")
        and pending_here
        and not has_open
        and pend_sides
        and open_action not in pend_sides
    )
    blocking_pending = has_pending and not flip_candidate
    # Same main-bar guard must not block opposite-side flip (pending keeps signal_ts
    # of the current 15m/1h bar for its whole life).
    same_bar_block = already_this_bar and not flip_candidate

    if (
        open_action == "HOLD"
        and not has_open
        and not has_pending
        and not has_shadow
        and not has_shadow_pending
        and not already_this_bar
        and explore_eff
    ):
        _rng = rng if rng is not None else random
        do_explore = bool(explore_when_idle) or (_rng.random() < float(explore_rate))
        if do_explore:
            # Explore buys labels, never sits the exam: paper equity must stay a
            # clean scoreboard of the cost-gated policy. The probe is a shadow.
            shadow_action = pick_explore_action(pred, vec, rng=_rng)
            open_source = f"explore/{source}"
            open_action = "HOLD"
            explored = True
            events.append(
                {
                    "kind": "explore",
                    "message": (
                        f"{label}: модель сказала ДЕРЖАТЬ — исследование (тень): "
                        f"пробуем {_action_ru(shadow_action)} (метка без риска для банка)"
                    ),
                }
            )
        else:
            events.append(
                {
                    "kind": "hold",
                    "message": (
                        f"{label}: ДЕРЖАТЬ — сделку не открываем "
                        f"(исследование не сработало, rate={float(explore_rate):.0%})"
                    ),
                }
            )
            logged_hold = True
    elif open_action == "HOLD" and not has_open and not has_pending and not explore_eff:
        if explore and explore_gate.get("reason") == "cap":
            logged_hold = True
        else:
            events.append(
                {
                    "kind": "hold",
                    "message": f"{label}: ДЕРЖАТЬ — сделку не открываем (исследование выключено)",
                }
            )
            logged_hold = True
    elif open_action == "HOLD" and has_shadow and not has_open:
        # Shadow already measuring this symbol — stay quiet, live path stays free.
        logged_hold = True

    if open_action in ("BUY", "SELL") and not has_open and not blocking_pending and not same_bar_block:
        cd_now = int(candles_exec[-1]["open_time"]) if (use_exec and candles_exec) else last_ts
        cd_hit = reentry_cooldown_active(
            root,
            symbol=sym,
            market=kind,
            side=open_action,
            now_ts_ms=cd_now,
        )
        if cd_hit:
            until = int(cd_hit.get("until_ts") or 0)
            left_m = max(1, (until - cd_now + 59_999) // 60_000)
            why = str(cd_hit.get("exit_reason") or "exit")
            why_ru = {"model": "model-exit", "sl": "SL"}.get(why, why)
            events.append(
                {
                    "kind": "hold",
                    "message": (
                        f"{label}: {_action_ru(open_action)} отклонён — cooldown после {why_ru} "
                        f"(ещё ~{left_m} мин)"
                    ),
                }
            )
            open_action = "HOLD"
            logged_hold = True
            flip_candidate = False
            same_bar_block = already_this_bar

    if (
        open_action in ("BUY", "SELL")
        and not has_open
        and not blocking_pending
        and not same_bar_block
        and not entry_setup_ok(open_action, feat if feat else vec)
    ):
        events.append(
            {
                "kind": "hold",
                "message": (
                    f"{label}: {_action_ru(open_action)} отклонён — слабый тайминг/сетап "
                    f"(источник: {_source_ru(open_source)})"
                ),
            }
        )
        open_action = "HOLD"
        logged_hold = True
        flip_candidate = False
        same_bar_block = already_this_bar

    # Explore deliberately pays for information as a shadow, so it never reaches
    # the cost gate — every live entry has to earn more than it costs.
    if (
        open_action in ("BUY", "SELL")
        and not explored
        and not has_open
        and not blocking_pending
        and not same_bar_block
    ):
        cost_ok, cost_why = cost_gate_ok(
            feat if feat else vec,
            fee=gate_fee,
            gate=load_cost_gate(root),
        )
        if not cost_ok:
            events.append(
                {
                    "kind": "hold",
                    "message": f"{label}: {_action_ru(open_action)} отклонён — {cost_why}",
                }
            )
            shadow_action = open_action
            open_action = "HOLD"
            logged_hold = True
            flip_candidate = False
            same_bar_block = already_this_bar

    # Opposite-side signal while pending: cancel old legs, then place new bracket.
    if (
        flip_candidate
        and open_action in ("BUY", "SELL")
        and pending_here
        and not has_open
    ):
        flip = cancel_pending_orders_for_symbol(
            root,
            symbol=sym,
            market=kind,
            reason="side_flip",
            append_cancel_row=lambda row: _append_paper_row(root, row),
            shadow_only=False,
        )
        events.extend(flip.get("events") or [])
        if int(flip.get("cancelled") or 0) > 0:
            events.append(
                {
                    "kind": "info",
                    "message": (
                        f"{label}: pending снят (side_flip) — ставим {_action_ru(open_action)}"
                    ),
                }
            )
        has_pending = False
        pending_here = []
        blocking_pending = False
        same_bar_block = False

    if (
        open_action in ("BUY", "SELL")
        and not has_open
        and not blocking_pending
        and not same_bar_block
    ):
        ensure_portfolio(root)
        is_soft = "soft" in str(open_source)
        utc_h = utc_hour_from_ms(last_ts)
        size = propose_size(
            _portfolio_for_sizing(root),
            market=kind,
            features=feat if feat else vec,
            action=open_action,
            probs=probs if isinstance(probs, dict) else None,
            project_root=root,
            soft_entry=is_soft,
            utc_hour=utc_h,
        )
        if not size.get("ok"):
            events.append(
                {
                    "kind": "hold",
                    "message": (
                        f"{label}: {_action_ru(open_action)} отклонён — нет бюджета риска "
                        f"(маржа занята {float(size.get('margin_used_usdt') or 0):.1f}/"
                        f"{float(size.get('max_margin_usdt') or 0):.1f} USDT, "
                        f"equity={float(size.get('equity_usdt') or 0):.1f})"
                    ),
                }
            )
            open_action = "HOLD"
            logged_hold = True

    if (
        open_action in ("BUY", "SELL")
        and not has_open
        and not blocking_pending
        and not same_bar_block
    ):
        entry_style_pred = predict_entry_style(root, feat if feat else vec, rng=rng)
        entry_style = str(entry_style_pred.get("style") or "market")
        style_learn_src = str(entry_style_pred.get("source") or "heuristic")
        levels = predict_levels(
            root,
            feat if feat else vec,
            fallback_tp=tp,
            fallback_sl=sl,
            fallback_trail=trail,
        )
        tp_use = float(levels["tp_pct"])
        sl_use = float(levels["sl_pct"])
        # Tighter trail → arms earlier, banks MFE instead of waiting horizon.
        trail_use = float(levels["trail_pct"]) * 0.75
        is_soft = "soft" in str(open_source)
        utc_h = utc_hour_from_ms(last_ts)
        sl_use, trail_use, soft_lvl_tag = adjust_soft_futures_levels(
            sl_use,
            trail_use,
            soft_entry=is_soft,
            market=kind,
            utc_hour=utc_h,
        )
        levels_src = str(levels.get("source") or "fallback")
        if soft_lvl_tag:
            levels_src = f"{levels_src}/{soft_lvl_tag}"
        size = propose_size(
            _portfolio_for_sizing(root),
            market=kind,
            features=feat if feat else vec,
            action=open_action,
            probs=probs if isinstance(probs, dict) else None,
            project_root=root,
            soft_entry=is_soft,
            utc_hour=utc_h,
        )
        if use_exec and candles_exec:
            signal_px = float(candles_exec[-1]["close"])
            signal_ts_exec = int(candles_exec[-1]["open_time"])
            exec_iv_pos = exec_iv
            h_exec = main_horizon_to_exec(h_eff, iv, exec_iv)
            # Soft entry is uncertain — prefer OCO bracket (limit+stop; other leg cancels).
            if "soft" in str(open_source) and entry_style in ("market", "limit"):
                entry_style = "oco"
                style_learn_src = f"{style_learn_src}/soft_bracket"
        else:
            signal_px = float(candles[-1]["close"])
            signal_ts_exec = last_ts
            exec_iv_pos = ""
            h_exec = h_eff
            entry_style = "market"

        if entry_style == "market" or not exec_iv_pos:
            entry = signal_px
            entry_ts = signal_ts_exec
            pos = {
                "ts": entry_ts,
                "signal_ts": last_ts,
                "signal_px": signal_px,
                "symbol": sym,
                "interval": iv,
                "market": kind,
                "action": open_action,
                "entry": entry,
                "horizon": h_eff,
                "horizon_exec": h_exec if exec_iv_pos else None,
                "exec_interval": exec_iv_pos or None,
                "tp_pct": tp_use if exec_iv_pos else None,
                "sl_pct": sl_use if exec_iv_pos else None,
                "trail_pct": trail_use if exec_iv_pos and trail_use > 0 else None,
                "trail_extreme": entry if exec_iv_pos and trail_use > 0 else None,
                "levels_source": levels_src if exec_iv_pos else None,
                "entry_style": "market",
                "style_source": style_learn_src,
                "features": feat,
                "feature_vec": vec,
                "source": open_source,
            }
            _attach_size_fields(pos, size)
            still_open.append(pos)
            save_open_positions(root, still_open)
            suggestion = {
                "action": open_action,
                "source": open_source,
                "entry": entry,
                "explored": explored,
                "market": kind,
                "horizon": h_eff,
                "exec_interval": exec_iv_pos or None,
                "entry_style": "market",
                "tp_pct": tp_use if exec_iv_pos else None,
                "sl_pct": sl_use if exec_iv_pos else None,
                "trail_pct": trail_use if exec_iv_pos else None,
                "levels_source": levels_src if exec_iv_pos else None,
                "margin_usdt": pos.get("margin_usdt"),
                "notional_usdt": pos.get("notional_usdt"),
                "leverage": pos.get("leverage"),
            }
            h_note = f", горизонт={h_eff}×{iv}" + (" (импульс)" if h_eff > h else "")
            if exec_iv_pos:
                h_note += (
                    f", market TP={tp_use:.2%} SL={sl_use:.2%} trail={trail_use:.2%} "
                    f"[{levels_src}] (макс {h_exec}×{exec_iv_pos})"
                )
            size_note = (
                f", stake={float(pos.get('notional_usdt') or 0):.1f} USDT "
                f"(маржа {float(pos.get('margin_usdt') or 0):.1f}×{float(pos.get('leverage') or 1):.1f})"
            )
            lev_tag = str(size.get("lev_tag") or "")
            if lev_tag == "confidence" and size.get("side_prob") is not None:
                size_note += f" [lev conf p={float(size['side_prob']):.2f}]"
            elif lev_tag.startswith("soft") and size.get("side_prob") is not None:
                size_note += f" [lev {lev_tag} p={float(size['side_prob']):.2f}]"
            elif lev_tag and lev_tag not in ("vol", "cap"):
                size_note += f" [{lev_tag}]"
            size_tag = str(size.get("size_tag") or "").strip()
            if size_tag:
                size_note += f" [{size_tag}]"
            if utc_h is not None:
                size_note += f" utc={utc_h:02d}"
            events.append(
                {
                    "kind": "paper",
                    "message": (
                        f"{label} бумажная {_action_ru(open_action)} @ {entry:.4f}{h_note}"
                        f"{size_note} (источник: {_source_ru(open_source)}) — без ордера"
                    ),
                    "reason": "open",
                    "bar_ts": int(entry_ts) if entry_ts else None,
                    "symbol": sym,
                    "market": kind,
                    "action": open_action,
                    "utc_hour": utc_h,
                }
            )
        else:
            order = build_pending_order(
                symbol=sym,
                market=kind,
                action=open_action,
                signal_px=signal_px,
                signal_ts=signal_ts_exec,
                interval=iv,
                entry_style=entry_style,
                horizon=h_eff,
                horizon_exec=h_exec,
                exec_interval=exec_iv_pos,
                tp_pct=tp_use,
                sl_pct=sl_use,
                trail_pct=trail_use,
                features=feat,
                feature_vec=vec,
                source=open_source,
            )
            order["signal_ts"] = last_ts
            order["main_signal_ts"] = last_ts
            order["levels_source"] = levels_src
            order["style_source"] = style_learn_src
            _attach_size_fields(order, size)
            pend_all = load_pending_orders(root)
            pend_all.append(order)
            save_pending_orders(root, pend_all)
            suggestion = {
                "action": open_action,
                "source": open_source,
                "entry": signal_px,
                "explored": explored,
                "market": kind,
                "horizon": h_eff,
                "exec_interval": exec_iv_pos,
                "entry_style": entry_style,
                "pending": True,
                "limit_px": order.get("limit_px"),
                "stop_px": order.get("stop_px"),
                "tp_pct": tp_use,
                "sl_pct": sl_use,
                "trail_pct": trail_use,
                "levels_source": levels_src,
                "margin_usdt": order.get("margin_usdt"),
                "notional_usdt": order.get("notional_usdt"),
                "leverage": order.get("leverage"),
            }
            bits = [f"стиль={entry_style}"]
            if order.get("limit_px"):
                bits.append(f"limit={float(order['limit_px']):.4f}")
            if order.get("stop_px"):
                bits.append(f"stop={float(order['stop_px']):.4f}")
            bits.append(
                f"TP={tp_use:.2%} SL={sl_use:.2%} trail={trail_use:.2%} [{levels_src}]"
            )
            bits.append(
                f"stake={float(order.get('notional_usdt') or 0):.1f} USDT "
                f"(маржа {float(order.get('margin_usdt') or 0):.1f}×{float(order.get('leverage') or 1):.1f})"
            )
            lev_tag = str(size.get("lev_tag") or "")
            if lev_tag == "confidence" and size.get("side_prob") is not None:
                bits.append(f"lev conf p={float(size['side_prob']):.2f}")
            elif lev_tag.startswith("soft") and size.get("side_prob") is not None:
                bits.append(f"lev {lev_tag} p={float(size['side_prob']):.2f}")
            elif lev_tag.startswith("sl_soft"):
                bits.append(lev_tag)
            elif lev_tag.startswith("soft"):
                bits.append(f"lev {lev_tag}")
            size_tag = str(size.get("size_tag") or "").strip()
            if size_tag:
                bits.append(size_tag)
            if utc_h is not None:
                bits.append(f"utc={utc_h:02d}")
            events.append(
                {
                    "kind": "paper",
                    "message": (
                        f"{label} pending {_action_ru(open_action)} @ signal={signal_px:.4f} "
                        f"({', '.join(bits)}; id={order.get('id')}) — ждём 1m, без ордера"
                    ),
                    "reason": "pending",
                    "bar_ts": int(signal_ts_exec) if signal_ts_exec else None,
                    "symbol": sym,
                    "market": kind,
                    "action": open_action,
                    "utc_hour": utc_h,
                }
            )
    elif has_open or has_pending:
        if has_pending and not has_open:
            events.append(
                {
                    "kind": "skip",
                    "message": f"уже есть pending по {label} — ждём fill/отмену",
                }
            )
        elif has_open:
            events.append(
                {"kind": "skip", "message": f"уже есть открытая позиция по {label} — ждём итог"}
            )
    elif open_action == "HOLD" and not logged_hold and not explored:
        events.append({"kind": "hold", "message": f"{label}: ДЕРЖАТЬ — бумажную сделку не открываем"})

    # A refused entry still has to teach us something: track it as a shadow so
    # the journal keeps learning about the regime the gate is filtering out.
    # Without this the next calibration only ever sees trades the gate allowed,
    # decides everything pays, and unlocks itself.
    # B12: shadow uses the same style/pending/OCO path as the live book.
    if shadow_action in ("BUY", "SELL"):
        if has_shadow or any(
            str(s.get("symbol") or "").upper() == sym and _pos_market(s) == kind
            for s in still_shadow
        ):
            shadow_action = ""
        elif has_shadow_pending and shadow_action in shadow_pend_sides:
            shadow_action = ""
        elif has_shadow_pending and shadow_pend_sides and shadow_action not in shadow_pend_sides:
            flip_s = cancel_pending_orders_for_symbol(
                root,
                symbol=sym,
                market=kind,
                reason="side_flip",
                append_cancel_row=lambda row: _append_paper_row(root, row),
                shadow_only=True,
            )
            events.extend(flip_s.get("events") or [])
            has_shadow_pending = False
            shadow_pending_here = []
            shadow_pend_sides = set()
    if shadow_action in ("BUY", "SELL"):
        s_levels = predict_levels(
            root,
            feat if feat else vec,
            fallback_tp=tp,
            fallback_sl=sl,
            fallback_trail=trail,
        )
        s_trail = float(s_levels["trail_pct"]) * 0.75
        s_tp = float(s_levels["tp_pct"])
        s_sl = float(s_levels["sl_pct"])
        s_levels_src = str(s_levels.get("source") or "fallback")
        s_gate_exp = expansion_score(feat if feat else vec)
        s_style_pred = predict_entry_style(root, feat if feat else vec, rng=rng)
        s_entry_style = str(s_style_pred.get("style") or "market")
        s_style_src = str(s_style_pred.get("source") or "heuristic")
        # Soft shadows (rare) get the same OCO bracket preference as live soft.
        if "soft" in str(open_source) and s_entry_style in ("market", "limit"):
            s_entry_style = "oco"
            s_style_src = f"{s_style_src}/soft_bracket"
        if use_exec and candles_exec:
            s_signal_px = float(candles_exec[-1]["close"])
            s_signal_ts = int(candles_exec[-1]["open_time"])
            s_exec_iv = exec_iv
            s_h_exec = main_horizon_to_exec(h_eff, iv, exec_iv)
        else:
            s_signal_px = float(candles[-1]["close"])
            s_signal_ts = last_ts
            s_exec_iv = ""
            s_h_exec = h_eff
            s_entry_style = "market"

        if s_entry_style == "market" or not s_exec_iv:
            still_shadow.append(
                {
                    "ts": s_signal_ts,
                    "signal_ts": last_ts,
                    "signal_px": s_signal_px,
                    "symbol": sym,
                    "interval": iv,
                    "market": kind,
                    "action": shadow_action,
                    "entry": s_signal_px,
                    "horizon": h_eff,
                    "horizon_exec": s_h_exec if s_exec_iv else None,
                    "exec_interval": s_exec_iv or None,
                    "tp_pct": s_tp if s_exec_iv else None,
                    "sl_pct": s_sl if s_exec_iv else None,
                    "trail_pct": s_trail if s_exec_iv and s_trail > 0 else None,
                    "trail_extreme": s_signal_px if s_exec_iv and s_trail > 0 else None,
                    "levels_source": s_levels_src,
                    "entry_style": "market",
                    "style_source": s_style_src,
                    "features": feat,
                    "feature_vec": vec,
                    "source": open_source,
                    "gate_expansion": s_gate_exp,
                    "shadow": True,
                }
            )
            save_shadow_positions(root, still_shadow)
        else:
            s_order = build_pending_order(
                symbol=sym,
                market=kind,
                action=shadow_action,
                signal_px=s_signal_px,
                signal_ts=s_signal_ts,
                interval=iv,
                entry_style=s_entry_style,
                horizon=h_eff,
                horizon_exec=s_h_exec,
                exec_interval=s_exec_iv,
                tp_pct=s_tp,
                sl_pct=s_sl,
                trail_pct=s_trail,
                features=feat,
                feature_vec=vec,
                source=open_source,
                shadow=True,
                gate_expansion=s_gate_exp,
            )
            s_order["signal_ts"] = last_ts
            s_order["main_signal_ts"] = last_ts
            s_order["levels_source"] = s_levels_src
            s_order["style_source"] = s_style_src
            pend_all = load_pending_orders(root)
            pend_all.append(s_order)
            save_pending_orders(root, pend_all)
            events.append(
                {
                    "kind": "info",
                    "message": (
                        f"{label} тень pending {_action_ru(shadow_action)} "
                        f"стиль={s_entry_style} @ signal={s_signal_px:.4f} "
                        f"(id={s_order.get('id')}) — метка без риска для банка"
                    ),
                }
            )

    if micro_train and (resolved > 0 or shadow_resolved > 0):
        _append_learn_events(events, root, epochs=int(train_epochs))

    ms = model_status(root)
    return {
        "ok": True,
        "events": events,
        "opens": len(still_open),
        "resolved": resolved,
        "shadow_open": len(still_shadow),
        "shadow_resolved": shadow_resolved,
        "suggestion": suggestion,
        "model": ms,
        "symbol": sym,
        "interval": iv,
        "market": kind,
        "horizon": h,
        "explore_gate": explore_gate,
        "error": None,
    }


def run_live_universe_tick(
    project_root: str | Path,
    *,
    symbols: Sequence[str],
    interval: str = DEFAULT_INTERVAL,
    window: int = DEFAULT_WINDOW,
    horizon: int = DEFAULT_LIVE_HORIZON,
    fee: float | None = None,
    thr: float = DEFAULT_THR,
    sync_limit: int = DEFAULT_SYNC_LIMIT,
    max_keep: int = DEFAULT_MAX_KEEP,
    micro_train: bool = True,
    train_epochs: int = 15,
    explore: bool = True,
    explore_rate: float = DEFAULT_EXPLORE_RATE,
    explore_when_idle: bool = True,
    explore_live_cap: int | None = DEFAULT_EXPLORE_LIVE_CAP,
    markets: Sequence[str] | str | None = None,
    futures_symbols: Sequence[str] | None = None,
    exec_interval: str | None = None,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    trail_pct: float = DEFAULT_TRAIL_PCT,
    rng: Optional[Any] = None,
    fetch: Optional[Callable[..., dict[str, Any]]] = None,
    fetch_spot: Optional[Callable[..., dict[str, Any]]] = None,
    fetch_futures: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run ``run_live_tick`` for each (symbol, market); one micro-train if any resolved."""
    if isinstance(markets, str):
        market_kinds: tuple[MarketKind, ...] = parse_markets(markets)
    elif markets is None:
        market_kinds = (DEFAULT_MARKET,)
    else:
        seen_m: set[MarketKind] = set()
        market_kinds_list: list[MarketKind] = []
        for m in markets:
            kind = normalize_market(m)
            if kind not in seen_m:
                seen_m.add(kind)
                market_kinds_list.append(kind)
        market_kinds = tuple(market_kinds_list) or (DEFAULT_MARKET,)

    explore_gate = resolve_explore_enabled(
        project_root, explore=explore, explore_live_cap=explore_live_cap
    )
    explore_eff = bool(explore_gate.get("enabled"))
    # Children: already gated; pass cap=0 so they don't re-log / re-count.
    child_explore = explore_eff
    child_cap = 0

    def _uniq(seq: Sequence[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for s in seq:
            u = (s or "").strip().upper()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    spot_syms = _uniq(symbols) or [DEFAULT_SYMBOL]
    fut_syms = _uniq(futures_symbols) if futures_symbols is not None else list(spot_syms)
    if "futures" in market_kinds and not fut_syms:
        fut_syms = [DEFAULT_SYMBOL]

    jobs: list[tuple[str, MarketKind]] = []
    for kind in market_kinds:
        if kind == "futures":
            for s in fut_syms:
                jobs.append((s, "futures"))
        else:
            for s in spot_syms:
                jobs.append((s, "spot"))

    active_keys = {(s, m) for s, m in jobs}

    # Orphan opens (wrong symbol or market) — resolve only.
    orphan_jobs: list[tuple[str, MarketKind]] = []
    seen_orphans: set[tuple[str, MarketKind]] = set()
    for p in load_open_positions(project_root):
        u = str(p.get("symbol") or "").strip().upper()
        if not u:
            continue
        mk = _pos_market(p)
        key = (u, mk)
        if key not in active_keys and key not in seen_orphans:
            seen_orphans.add(key)
            orphan_jobs.append(key)
    orphan_jobs.sort()

    events: list[dict[str, Any]] = []
    total_resolved = 0
    last_suggestion: dict[str, Any] | None = None
    last_ok = True
    last_error: str | None = None
    opens_count = 0
    idle_waits = 0

    if explore and not explore_eff and explore_gate.get("reason") == "cap":
        events.append(
            {
                "kind": "info",
                "message": (
                    f"исследование выкл: live-меток {explore_gate.get('live')} "
                    f"≥ порога {explore_gate.get('cap')} — доверяем модели"
                ),
            }
        )

    def _fetch_for(kind: str) -> Optional[Callable[..., dict[str, Any]]]:
        if kind == "futures":
            return fetch_futures if fetch_futures is not None else fetch
        return fetch_spot if fetch_spot is not None else fetch

    def _run_one(sym: str, kind: str, *, allow_open: bool) -> None:
        nonlocal total_resolved, opens_count, idle_waits, last_suggestion, last_ok, last_error
        one = run_live_tick(
            project_root,
            symbol=sym,
            interval=interval,
            window=window,
            horizon=horizon,
            fee=fee,
            thr=thr,
            sync_limit=sync_limit,
            max_keep=max_keep,
            micro_train=False,
            train_epochs=train_epochs,
            explore=child_explore if allow_open else False,
            explore_rate=explore_rate,
            explore_when_idle=explore_when_idle if allow_open else False,
            explore_live_cap=child_cap,
            allow_open=allow_open,
            market=kind,
            exec_interval=exec_interval,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            trail_pct=trail_pct,
            rng=rng,
            fetch=_fetch_for(kind),
        )
        for ev in one.get("events") or []:
            events.append(ev)
        total_resolved += int(one.get("resolved") or 0)
        opens_count = int(one.get("opens") or opens_count)
        if one.get("idle_wait"):
            idle_waits += 1
        if one.get("suggestion"):
            last_suggestion = one.get("suggestion")
        if not one.get("ok"):
            last_ok = False
            last_error = str(one.get("error") or last_error)

    if orphan_jobs:
        orphan_labels = [f"{s} [{'fut' if m == 'futures' else 'spot'}]" for s, m in orphan_jobs]
        events.append(
            {
                "kind": "info",
                "message": (
                    "старые paper вне текущих списков Spot/Futures — только закрытие метки "
                    f"(новых сделок по ним нет): {', '.join(orphan_labels)}"
                ),
            }
        )
        for sym, mk in orphan_jobs:
            _run_one(sym, mk, allow_open=False)

    for sym, mk in jobs:
        _run_one(sym, mk, allow_open=True)

    if micro_train and total_resolved > 0:
        _append_learn_events(events, Path(project_root).resolve(), epochs=int(train_epochs))

    interesting = {"sync", "outcome", "paper", "explore", "learn", "error", "hold", "wait"}
    has_interesting = any(e.get("kind") in interesting for e in events)
    if has_interesting:
        mk_s = "+".join(market_kinds)
        if "spot" in market_kinds and "futures" in market_kinds:
            scope = f"spot={', '.join(spot_syms)}; fut={', '.join(fut_syms)}"
        elif "futures" in market_kinds:
            scope = f"fut={', '.join(fut_syms)}"
        else:
            scope = ", ".join(spot_syms)
        events.insert(
            0,
            {
                "kind": "info",
                "message": f"universe ({mk_s}): {scope} ({len(jobs)} пар)",
            },
        )
    else:
        # Fully silent idle — status bar already shows opens; avoid spam every auto-tick.
        events = []

    ms = model_status(project_root)
    return {
        "ok": last_ok,
        "events": events,
        "opens": opens_count,
        "resolved": total_resolved,
        "suggestion": last_suggestion,
        "model": ms,
        "symbols": spot_syms,
        "futures_symbols": fut_syms if "futures" in market_kinds else [],
        "markets": list(market_kinds),
        "orphans": [f"{s}/{m}" for s, m in orphan_jobs],
        "symbol": spot_syms[0] if spot_syms else DEFAULT_SYMBOL,
        "interval": (interval or DEFAULT_INTERVAL).strip(),
        "horizon": max(1, int(horizon)),
        "explore_gate": explore_gate,
        "error": last_error,
        "idle": not has_interesting,
    }
