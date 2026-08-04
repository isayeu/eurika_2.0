"""Paper bankroll: 1000 USDT start, risk sizing, futures leverage rule.

No live Binance orders. Tracks equity / margin so live paper can size stakes
toward max profit (USDT), not only Σ edge%.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.market_store import ml_root, normalize_market

DEFAULT_START_EQUITY_USDT = 1000.0
DEFAULT_RISK_FRAC = 0.01  # margin per new trade = 1% equity
DEFAULT_MAX_MARGIN_FRAC = 0.30  # sum open margins ≤ 30% equity
DEFAULT_LEV_MIN = 1.0
DEFAULT_LEV_MAX = 5.0
# Soft-entry futures: never allow high lev at low side_prob (vol-only fallback
# used to push 5× on quiet tape). Hard model still uses full 1…5× confidence.
DEFAULT_SOFT_FUTURES_LEV_MAX = 2.0
# UTC hours that historically drained equity (observe + mild soft cap).
SOFT_RISK_HOURS_UTC = frozenset({7, 8, 9})
# Soft futures levels: tighter SL, earlier trail arm.
SOFT_FUTURES_SL_SCALE = 0.75
SOFT_FUTURES_TRAIL_SCALE = 0.70
SOFT_RISK_HOUR_SL_SCALE = 0.65
SOFT_RISK_HOUR_TRAIL_SCALE = 0.60
# Confidence → leverage: side_prob at equal-thirds (~0.33) → min; ≥0.55 → max.
_CONF_LEV_LO = 1.0 / 3.0
_CONF_LEV_HI = 0.55
# Mild vol dampener on confidence lev (not a substitute for direction).
_VOL_LEV_SOFT = 0.004
_VOL_LEV_HARD = 0.012
# Optional SL-series cap helpers (not applied by default — lev = confidence).
DEFAULT_SL_SOFT_WINDOW = 6
DEFAULT_SL_SOFT_REASONS = frozenset({"sl", "trail"})


def utc_hour_from_ms(ts_ms: int | float | None) -> int | None:
    """UTC hour 0..23 from epoch ms; None if missing/invalid."""
    if ts_ms is None:
        return None
    try:
        ms = int(ts_ms)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return int(datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).hour)


def soft_futures_lev_cap(
    *,
    soft_entry: bool,
    market: str,
    utc_hour: int | None = None,
) -> float | None:
    """Extra lev_max for soft futures, or None if no soft cap applies."""
    if not soft_entry or normalize_market(market) != "futures":
        return None
    if utc_hour is not None and utc_hour in SOFT_RISK_HOURS_UTC:
        return 1.0
    return float(DEFAULT_SOFT_FUTURES_LEV_MAX)


def adjust_soft_futures_levels(
    sl_pct: float,
    trail_pct: float,
    *,
    soft_entry: bool,
    market: str,
    utc_hour: int | None = None,
) -> tuple[float, float, str]:
    """Tighten SL/trail for soft futures (extra in risk hours). Returns sl, trail, tag."""
    sl = max(0.0, float(sl_pct))
    trail = max(0.0, float(trail_pct))
    if not soft_entry or normalize_market(market) != "futures":
        return sl, trail, ""
    if utc_hour is not None and utc_hour in SOFT_RISK_HOURS_UTC:
        sl *= SOFT_RISK_HOUR_SL_SCALE
        trail *= SOFT_RISK_HOUR_TRAIL_SCALE
        return sl, trail, f"soft_fut_h{utc_hour}"
    sl *= SOFT_FUTURES_SL_SCALE
    trail *= SOFT_FUTURES_TRAIL_SCALE
    return sl, trail, "soft_fut"


def paper_portfolio_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "paper_portfolio.json"


def default_portfolio(*, start_equity: float = DEFAULT_START_EQUITY_USDT) -> dict[str, Any]:
    eq = max(1.0, float(start_equity))
    now = int(time.time() * 1000)
    return {
        "version": 1,
        "start_equity_usdt": eq,
        "equity_usdt": eq,
        "margin_used_usdt": 0.0,
        "realized_pnl_usdt": 0.0,
        "risk_frac": DEFAULT_RISK_FRAC,
        "max_margin_frac": DEFAULT_MAX_MARGIN_FRAC,
        "updated_ms": now,
        "created_ms": now,
        "note": "paper bankroll; max profit = grow equity_usdt",
    }


def load_portfolio(project_root: str | Path) -> dict[str, Any]:
    path = paper_portfolio_path(project_root)
    if not path.is_file():
        return default_portfolio()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_portfolio()
    if not isinstance(data, dict):
        return default_portfolio()
    out = default_portfolio()
    out.update({k: data[k] for k in data if k in out or k in ("version", "note", "created_ms")})
    try:
        out["equity_usdt"] = float(data.get("equity_usdt") or out["equity_usdt"])
        out["start_equity_usdt"] = float(data.get("start_equity_usdt") or out["start_equity_usdt"])
        out["margin_used_usdt"] = max(0.0, float(data.get("margin_used_usdt") or 0.0))
        out["realized_pnl_usdt"] = float(data.get("realized_pnl_usdt") or 0.0)
        out["risk_frac"] = float(data.get("risk_frac") or DEFAULT_RISK_FRAC)
        out["max_margin_frac"] = float(data.get("max_margin_frac") or DEFAULT_MAX_MARGIN_FRAC)
    except (TypeError, ValueError):
        return default_portfolio()
    return out


def save_portfolio(project_root: str | Path, portfolio: Mapping[str, Any]) -> Path:
    path = paper_portfolio_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(portfolio)
    blob["updated_ms"] = int(time.time() * 1000)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ensure_portfolio(project_root: str | Path) -> dict[str, Any]:
    """Load or create portfolio file on disk."""
    path = paper_portfolio_path(project_root)
    if path.is_file():
        return load_portfolio(project_root)
    port = default_portfolio()
    save_portfolio(project_root, port)
    return port


def leverage_from_features(
    market: str,
    features: Mapping[str, Any] | Sequence[float] | None = None,
    *,
    lev_min: float = DEFAULT_LEV_MIN,
    lev_max: float = DEFAULT_LEV_MAX,
    side_prob: float | None = None,
    hold_prob: float | None = None,
    soft_entry: bool = False,
) -> float:
    """Spot = 1x. Futures: leverage ≈ confidence in the chosen side.

    ``side_prob`` (BUY or SELL prob) maps 1/3…0.55 → lev_min…lev_max.
    Vol only mildly dampens (does not replace direction/confidence).
    Soft-entry caps ``lev_max`` so low-p / missing-probs cannot reach 5×.
    """
    kind = normalize_market(market)
    if kind != "futures":
        return 1.0
    lo = max(1.0, float(lev_min))
    hi = max(lo, float(lev_max))
    if soft_entry:
        hi = min(hi, float(DEFAULT_SOFT_FUTURES_LEV_MAX))
        hi = max(lo, hi)
    if side_prob is None:
        # Legacy: vol-only curve when no probs (backfill / tests).
        vol = 0.0
        if isinstance(features, Mapping):
            vol = float(features.get("volatility") or 0.0)
        elif isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
            if len(features) > 4:
                try:
                    vol = float(features[4])
                except (TypeError, ValueError):
                    vol = 0.0
        if vol <= _VOL_LEV_SOFT:
            lev = hi
        elif vol >= _VOL_LEV_HARD:
            lev = lo
        else:
            t = (vol - _VOL_LEV_SOFT) / max(1e-12, _VOL_LEV_HARD - _VOL_LEV_SOFT)
            lev = hi - t * (hi - lo)
        return max(lo, min(hi, float(lev)))

    p = max(0.0, min(1.0, float(side_prob)))
    # Strength vs uniform 3-way; soft-entry ~0.24 still gets near-min lev.
    span = max(1e-9, _CONF_LEV_HI - _CONF_LEV_LO)
    strength = max(0.0, min(1.0, (p - _CONF_LEV_LO) / span))
    # Slight discount if HOLD still competitive.
    if hold_prob is not None:
        hp = max(0.0, min(1.0, float(hold_prob)))
        if hp > p:
            strength *= 0.5
        elif hp > 0:
            strength *= max(0.35, min(1.0, (p - hp) / max(0.05, p) + 0.5))
    lev = lo + strength * (hi - lo)
    # Mild vol dampen: high vol → up to −30% of (lev−lo) headroom.
    vol = 0.0
    if isinstance(features, Mapping):
        vol = float(features.get("volatility") or 0.0)
    elif isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        if len(features) > 4:
            try:
                vol = float(features[4])
            except (TypeError, ValueError):
                vol = 0.0
    if vol > _VOL_LEV_SOFT and hi > lo:
        t = min(1.0, (vol - _VOL_LEV_SOFT) / max(1e-12, _VOL_LEV_HARD - _VOL_LEV_SOFT))
        lev = lo + (lev - lo) * (1.0 - 0.3 * t)
    return max(lo, min(hi, float(lev)))


def recent_filled_exit_reasons(
    project_root: str | Path,
    *,
    window: int = DEFAULT_SL_SOFT_WINDOW,
) -> list[str]:
    """Most recent filled exit reasons (newest first); skips cancels / incomplete rows."""
    from eurika.ml.paper_trader import load_paper_trades

    win = max(1, int(window))
    out: list[str] = []
    for row in reversed(load_paper_trades(project_root)):
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") == "exit_sample":
            continue
        reason = str(row.get("exit_reason") or "").strip().lower()
        if not reason or reason.startswith("cancel"):
            continue
        out.append(reason)
        if len(out) >= win:
            break
    return out


def sl_streak_and_count(
    reasons: Sequence[str],
    *,
    sl_reasons: frozenset[str] = DEFAULT_SL_SOFT_REASONS,
) -> tuple[int, int]:
    """Return (consecutive SL streak from tip, SL count in list)."""
    streak = 0
    for r in reasons:
        if r in sl_reasons:
            streak += 1
        else:
            break
    count = sum(1 for r in reasons if r in sl_reasons)
    return streak, count


def soft_lev_max_from_sl(
    *,
    streak: int,
    count_in_window: int,
    lev_max: float = DEFAULT_LEV_MAX,
) -> tuple[float, str]:
    """Cap futures lev_max after SL series. Returns (cap, reason_tag)."""
    hi = max(1.0, float(lev_max))
    st = max(0, int(streak))
    cnt = max(0, int(count_in_window))
    if st >= 3 or cnt >= 4:
        return min(hi, 2.0), f"sl_soft streak={st} n={cnt}→2×"
    if st >= 2 or cnt >= 3:
        return min(hi, 3.0), f"sl_soft streak={st} n={cnt}→3×"
    if st >= 1 or cnt >= 2:
        return min(hi, 4.0), f"sl_soft streak={st} n={cnt}→4×"
    return hi, "vol"


def soft_lev_max_for_root(
    project_root: str | Path,
    *,
    window: int = DEFAULT_SL_SOFT_WINDOW,
    lev_max: float = DEFAULT_LEV_MAX,
) -> tuple[float, str, int, int]:
    """Lookup recent paper exits → softened lev_max. Returns cap, tag, streak, count."""
    reasons = recent_filled_exit_reasons(project_root, window=window)
    streak, count = sl_streak_and_count(reasons)
    cap, tag = soft_lev_max_from_sl(streak=streak, count_in_window=count, lev_max=lev_max)
    return cap, tag, streak, count


def recompute_margin_used(opens: Sequence[Mapping[str, Any]]) -> float:
    total = 0.0
    for p in opens:
        try:
            total += max(0.0, float(p.get("margin_usdt") or 0.0))
        except (TypeError, ValueError):
            continue
    return total


def propose_size(
    portfolio: Mapping[str, Any],
    *,
    market: str,
    features: Mapping[str, Any] | Sequence[float] | None = None,
    risk_frac: float | None = None,
    max_margin_frac: float | None = None,
    lev_max: float | None = None,
    side_prob: float | None = None,
    hold_prob: float | None = None,
    action: str | None = None,
    probs: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
    soft_entry: bool = False,
    utc_hour: int | None = None,
) -> dict[str, Any]:
    """Propose margin/notional/leverage or reject if risk budget exhausted.

    Futures leverage tracks **direction confidence** (side prob), not SL punishment.
    Soft-entry futures get an explicit lev cap (stricter in risk UTC hours).
    ``project_root`` kept for call-site compat; unused (no SL soft-cap by default).
    """
    _ = project_root
    equity = max(1.0, float(portfolio.get("equity_usdt") or DEFAULT_START_EQUITY_USDT))
    used = max(0.0, float(portfolio.get("margin_used_usdt") or 0.0))
    rf = float(risk_frac if risk_frac is not None else portfolio.get("risk_frac") or DEFAULT_RISK_FRAC)
    mf = float(
        max_margin_frac
        if max_margin_frac is not None
        else portfolio.get("max_margin_frac") or DEFAULT_MAX_MARGIN_FRAC
    )
    rf = max(0.001, min(0.05, rf))
    mf = max(rf, min(1.0, mf))
    budget = equity * mf
    free = max(0.0, budget - used)
    margin = min(equity * rf, free)
    if margin < equity * rf * 0.5 or margin < 0.5:
        return {
            "ok": False,
            "reason": "risk_budget",
            "equity_usdt": equity,
            "margin_used_usdt": used,
            "margin_free_usdt": free,
            "max_margin_usdt": budget,
            "leverage": 1.0,
            "margin_usdt": 0.0,
            "notional_usdt": 0.0,
        }
    hi = float(lev_max) if lev_max is not None else DEFAULT_LEV_MAX
    soft_cap = soft_futures_lev_cap(soft_entry=soft_entry, market=market, utc_hour=utc_hour)
    soft_tag = ""
    if soft_cap is not None:
        hi = min(hi, float(soft_cap))
        if utc_hour is not None and utc_hour in SOFT_RISK_HOURS_UTC:
            soft_tag = f"soft_h{utc_hour}"
        else:
            soft_tag = "soft_cap"
    sp = side_prob
    hp = hold_prob
    if probs is not None and sp is None:
        act = str(action or "").upper()
        if act in ("BUY", "SELL"):
            try:
                sp = float(probs.get(act) or 0.0)
            except (TypeError, ValueError):
                sp = None
        try:
            hp = float(probs.get("HOLD") or 0.0) if hp is None else hp
        except (TypeError, ValueError):
            hp = hold_prob
    lev = leverage_from_features(
        market,
        features,
        lev_max=hi,
        side_prob=sp,
        hold_prob=hp,
        soft_entry=soft_entry,
    )
    if soft_tag:
        lev_tag = soft_tag
    elif sp is not None:
        lev_tag = "confidence"
    elif lev_max is not None:
        lev_tag = "cap"
    else:
        lev_tag = "vol"
    notional = margin * lev
    return {
        "ok": True,
        "reason": "sized",
        "equity_usdt": equity,
        "margin_used_usdt": used,
        "margin_free_usdt": free,
        "max_margin_usdt": budget,
        "leverage": lev,
        "lev_max": hi,
        "lev_tag": lev_tag,
        "side_prob": sp,
        "soft_entry": bool(soft_entry),
        "utc_hour": utc_hour,
        "margin_usdt": margin,
        "notional_usdt": notional,
        "risk_frac": rf,
    }


def apply_open(
    project_root: str | Path,
    *,
    margin_usdt: float,
    opens: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reserve margin for a new open (recompute from opens if provided)."""
    port = ensure_portfolio(project_root)
    if opens is not None:
        port["margin_used_usdt"] = recompute_margin_used(opens)
    else:
        port["margin_used_usdt"] = max(0.0, float(port.get("margin_used_usdt") or 0.0)) + max(
            0.0, float(margin_usdt)
        )
    save_portfolio(project_root, port)
    return port


def apply_close(
    project_root: str | Path,
    *,
    margin_usdt: float,
    edge: float,
    notional_usdt: float,
    opens: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Release margin and apply PnL USDT = edge * notional (clamp loss to margin)."""
    port = ensure_portfolio(project_root)
    notion = max(0.0, float(notional_usdt))
    marg = max(0.0, float(margin_usdt))
    pnl = float(edge) * notion
    # Paper safety: cannot lose more than posted margin on this leg.
    if pnl < 0 and marg > 0:
        pnl = max(pnl, -marg)
    port["equity_usdt"] = max(1.0, float(port.get("equity_usdt") or DEFAULT_START_EQUITY_USDT) + pnl)
    port["realized_pnl_usdt"] = float(port.get("realized_pnl_usdt") or 0.0) + pnl
    if opens is not None:
        port["margin_used_usdt"] = recompute_margin_used(opens)
    else:
        port["margin_used_usdt"] = max(0.0, float(port.get("margin_used_usdt") or 0.0) - marg)
    save_portfolio(project_root, port)
    return {**port, "pnl_usdt": pnl}


def portfolio_status(project_root: str | Path) -> dict[str, Any]:
    port = load_portfolio(project_root)
    equity = float(port.get("equity_usdt") or DEFAULT_START_EQUITY_USDT)
    start = float(port.get("start_equity_usdt") or DEFAULT_START_EQUITY_USDT)
    used = float(port.get("margin_used_usdt") or 0.0)
    mf = float(port.get("max_margin_frac") or DEFAULT_MAX_MARGIN_FRAC)
    return {
        "equity_usdt": equity,
        "start_equity_usdt": start,
        "realized_pnl_usdt": float(port.get("realized_pnl_usdt") or 0.0),
        "session_pnl_usdt": equity - start,
        "margin_used_usdt": used,
        "margin_free_usdt": max(0.0, equity * mf - used),
        "max_margin_usdt": equity * mf,
        "risk_frac": float(port.get("risk_frac") or DEFAULT_RISK_FRAC),
        "max_margin_frac": mf,
        "path": str(paper_portfolio_path(project_root)),
    }
