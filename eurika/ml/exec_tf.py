"""Execution timeframe helpers: signal on main TF, fill/exit on 1m (TP/SL)."""

from __future__ import annotations

from typing import Any, Optional, Sequence

DEFAULT_EXEC_INTERVAL = "1m"
DEFAULT_TP_PCT = 0.003  # 0.3%
DEFAULT_SL_PCT = 0.003
# Model may close early only if unrealized edge ≥ this fraction of TP (0 if no TP).
# Lower = bank winners sooner (horizon was eating edge in live paper).
DEFAULT_MODEL_EXIT_TP_FRAC = 0.25
# Soft CLOSE lean (prob) may exit at this frac even if argmax is still HOLD.
DEFAULT_MODEL_EXIT_SOFT_TP_FRAC = 0.20
DEFAULT_MODEL_EXIT_SOFT_CLOSE_P = 0.45
# Bank partial when CLOSE>HOLD and unrealized ≥ this frac of TP.
DEFAULT_MODEL_EXIT_BANK_TP_FRAC = 0.30
# After MFE armed (≥ arm×TP), bank sooner when edge gave back keep_frac of peak.
DEFAULT_MODEL_EXIT_MFE_ARM_TP_FRAC = 0.30
DEFAULT_MODEL_EXIT_MFE_KEEP_FRAC = 0.65
DEFAULT_MODEL_EXIT_MFE_BANK_TP_FRAC = 0.12
DEFAULT_MODEL_EXIT_MFE_CLOSE_P = 0.32
# Time-stop (anti-horizon): arm earlier, exit on milder giveback, fewer bars.
DEFAULT_TIME_STOP_ARM_TP_FRAC = 0.28
DEFAULT_TIME_STOP_KEEP_FRAC = 0.40  # keep ≤40% of peak MFE → exit
DEFAULT_TIME_STOP_MIN_ABS = 0.0020  # 0.20% floor when TP tiny/zero
DEFAULT_TIME_STOP_MIN_BARS_FRAC = 0.12
DEFAULT_TIME_STOP_MIN_BARS = 6

EXIT_FEATURE_NAMES = (
    "ret_1",
    "unrealized_edge",
    "bars_frac",
    "dist_to_tp",
    "dist_to_sl",
    "hl_range",
)

_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def interval_ms(interval: str) -> int:
    iv = (interval or "").strip().lower()
    return int(_INTERVAL_MS.get(iv, 900_000))


def main_horizon_to_exec(horizon_main: int, main_interval: str, exec_interval: str = DEFAULT_EXEC_INTERVAL) -> int:
    """Convert N bars on main TF → bars on exec TF (ceil via integer division + max 1)."""
    h = max(1, int(horizon_main))
    ms_main = interval_ms(main_interval)
    ms_exec = max(1, interval_ms(exec_interval))
    return max(1, (h * ms_main + ms_exec - 1) // ms_exec)


def _bar_high_low(c: dict[str, Any]) -> tuple[float, float, float]:
    close = float(c["close"])
    high = float(c.get("high") or close)
    low = float(c.get("low") or close)
    return high, low, close


def find_entry_index(candles: Sequence[dict[str, Any]], entry_ts: int) -> int:
    """Index of entry bar (exact open_time, else first bar >= entry_ts).

    If ``entry_ts`` is older than the first retained candle, return -1 (scrolled
    out of the window). Remapping to index 0 would restart the horizon every
    tick and leave the position open forever.
    """
    if not candles:
        return -1
    first_ts = int(candles[0].get("open_time") or 0)
    if int(entry_ts) < first_ts:
        return -1
    for i, c in enumerate(candles):
        if int(c.get("open_time") or 0) == int(entry_ts):
            return i
    for i, c in enumerate(candles):
        if int(c.get("open_time") or 0) >= int(entry_ts):
            return i
    return -1


def directional_edge(entry: float, px: float, action: str, *, fee: float = 0.0) -> float:
    """Signed edge for BUY/SELL at price ``px`` (fee subtracted once)."""
    if entry <= 0 or px <= 0:
        return 0.0
    raw = (px / entry) - 1.0
    act = (action or "").upper()
    if act == "BUY":
        return raw - fee
    if act == "SELL":
        return (-raw) - fee
    return 0.0


def path_excursions(
    candles: Sequence[dict[str, Any]],
    *,
    entry_ts: int,
    entry: float,
    action: str,
    exit_ts: int | None = None,
) -> dict[str, Any]:
    """MFE/MAE along path after entry (through exit_ts if given).

    Returns mfe_pct, mae_pct, entry_timing_score (= mfe - mae), mfe_bars, mae_bars.
    """
    empty = {
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "entry_timing_score": 0.0,
        "mfe_bars": 0,
        "mae_bars": 0,
        "entry_idx": -1,
        "end_idx": -1,
    }
    if entry <= 0 or not candles:
        return empty
    act = (action or "").upper()
    if act not in ("BUY", "SELL"):
        return empty
    idx = find_entry_index(candles, entry_ts)
    if idx < 0:
        return empty
    end_i = len(candles) - 1
    if exit_ts is not None:
        for i in range(idx, len(candles)):
            if int(candles[i].get("open_time") or 0) == int(exit_ts):
                end_i = i
                break
            if int(candles[i].get("open_time") or 0) > int(exit_ts):
                end_i = max(idx, i - 1)
                break
    mfe = 0.0
    mae = 0.0
    mfe_bars = 0
    mae_bars = 0
    for i in range(idx + 1, end_i + 1):
        high, low, _close = _bar_high_low(candles[i])
        if act == "BUY":
            fav = (high / entry) - 1.0
            adv = (entry - low) / entry if low > 0 else 0.0
        else:
            fav = (entry - low) / entry if low > 0 else 0.0
            adv = (high / entry) - 1.0
        bars = i - idx
        if fav > mfe:
            mfe = fav
            mfe_bars = bars
        if adv > mae:
            mae = adv
            mae_bars = bars
    return {
        "mfe_pct": float(mfe),
        "mae_pct": float(mae),
        "entry_timing_score": float(mfe - mae),
        "mfe_bars": int(mfe_bars),
        "mae_bars": int(mae_bars),
        "entry_idx": idx,
        "end_idx": end_i,
    }


def exit_feature_vector(
    candles_exec: Sequence[dict[str, Any]],
    *,
    entry_ts: int,
    entry: float,
    action: str,
    horizon_exec: int,
    tp_pct: float = 0.0,
    sl_pct: float = 0.0,
    fee: float = 0.0,
    at_index: int | None = None,
) -> Optional[list[float]]:
    """6-dim exit features at last (or ``at_index``) exec bar after entry."""
    if entry <= 0 or not candles_exec:
        return None
    act = (action or "").upper()
    if act not in ("BUY", "SELL"):
        return None
    idx = find_entry_index(candles_exec, entry_ts)
    if idx < 0:
        return None
    i = len(candles_exec) - 1 if at_index is None else int(at_index)
    if i <= idx or i >= len(candles_exec):
        return None
    high, low, close = _bar_high_low(candles_exec[i])
    prev_close = float(candles_exec[i - 1]["close"]) if i > 0 else close
    ret_1 = (close / prev_close) - 1.0 if prev_close > 0 else 0.0
    unreal = directional_edge(entry, close, act, fee=fee)
    h_exec = max(1, int(horizon_exec))
    bars_held = i - idx
    bars_frac = min(1.0, float(bars_held) / float(h_exec))
    tp = max(0.0, float(tp_pct))
    sl = max(0.0, float(sl_pct))
    if act == "BUY":
        sl_px = entry * (1.0 - sl) if sl > 0 else 0.0
        dist_to_sl = ((close - sl_px) / entry) if sl > 0 and entry > 0 else 1.0
        tp_px = entry * (1.0 + tp) if tp > 0 else 0.0
        dist_to_tp = ((tp_px - close) / entry) if tp > 0 and entry > 0 else 1.0
    else:
        sl_px = entry * (1.0 + sl) if sl > 0 else 0.0
        dist_to_sl = ((sl_px - close) / entry) if sl > 0 and entry > 0 else 1.0
        tp_px = entry * (1.0 - tp) if tp > 0 else 0.0
        dist_to_tp = ((close - tp_px) / entry) if tp > 0 and entry > 0 else 1.0
    hl_range = (high - low) / entry if entry > 0 else 0.0
    return [
        float(ret_1),
        float(unreal),
        float(bars_frac),
        float(dist_to_tp),
        float(dist_to_sl),
        float(hl_range),
    ]


def retro_exit_samples(
    candles_exec: Sequence[dict[str, Any]],
    *,
    entry_ts: int,
    entry: float,
    action: str,
    exit_ts: int,
    horizon_exec: int,
    tp_pct: float = 0.0,
    sl_pct: float = 0.0,
    fee: float = 0.0,
    meta: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Label 1m bars: HOLD until MFE peak, CLOSE at/after peak when edge slips."""
    act = (action or "").upper()
    if act not in ("BUY", "SELL") or entry <= 0:
        return []
    idx = find_entry_index(candles_exec, entry_ts)
    if idx < 0:
        return []
    end_i = idx
    for i in range(idx, len(candles_exec)):
        if int(candles_exec[i].get("open_time") or 0) == int(exit_ts):
            end_i = i
            break
    else:
        end_i = find_entry_index(candles_exec, exit_ts)
        if end_i < 0:
            end_i = len(candles_exec) - 1

    # Peak favorable close-edge along path
    peak_edge = float("-inf")
    peak_i = idx + 1
    edges: list[tuple[int, float]] = []
    for i in range(idx + 1, end_i + 1):
        close = float(candles_exec[i]["close"])
        e = directional_edge(entry, close, act, fee=fee)
        edges.append((i, e))
        if e >= peak_edge:
            peak_edge = e
            peak_i = i

    base = dict(meta or {})
    out: list[dict[str, Any]] = []
    running_mfe = 0.0
    for i, e in edges:
        running_mfe = max(running_mfe, float(e))
        giveback = max(0.0, running_mfe - float(e))
        vec = exit_feature_vector(
            candles_exec,
            entry_ts=entry_ts,
            entry=entry,
            action=act,
            horizon_exec=horizon_exec,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            fee=fee,
            at_index=i,
        )
        if vec is None:
            continue
        if i < peak_i:
            label = "HOLD"
        elif i == peak_i:
            label = "CLOSE"
        else:
            # After peak: CLOSE if edge worsened from peak, else HOLD
            label = "CLOSE" if e < peak_edge - 1e-12 else "HOLD"
        row = {
            **base,
            "kind": "exit_sample",
            "exit_label": label,
            "feature_vec": vec,
            "unrealized_edge": e,
            "mfe_pct": float(running_mfe),
            "giveback": float(giveback),
            "bar_ts": int(candles_exec[i].get("open_time") or 0),
            "entry_ts": int(entry_ts),
            "action": act,
            "entry": entry,
        }
        out.append(row)
    return out


def model_exit_min_edge(tp_pct: float, *, frac: float = DEFAULT_MODEL_EXIT_TP_FRAC) -> float:
    """Minimum unrealized edge to allow model early CLOSE."""
    tp = max(0.0, float(tp_pct))
    f = max(0.0, float(frac))
    return tp * f if tp > 0 else 0.0


def should_model_exit(
    pred_x: dict[str, Any],
    unrealized_edge: float,
    tp_pct: float,
    *,
    hard_frac: float = DEFAULT_MODEL_EXIT_TP_FRAC,
    soft_frac: float = DEFAULT_MODEL_EXIT_SOFT_TP_FRAC,
    soft_close_p: float = DEFAULT_MODEL_EXIT_SOFT_CLOSE_P,
    bank_frac: float = DEFAULT_MODEL_EXIT_BANK_TP_FRAC,
    mfe_pct: float | None = None,
    mfe_arm_frac: float = DEFAULT_MODEL_EXIT_MFE_ARM_TP_FRAC,
    mfe_keep_frac: float = DEFAULT_MODEL_EXIT_MFE_KEEP_FRAC,
    mfe_bank_frac: float = DEFAULT_MODEL_EXIT_MFE_BANK_TP_FRAC,
    mfe_close_p: float = DEFAULT_MODEL_EXIT_MFE_CLOSE_P,
) -> bool:
    """Exit-first: CLOSE on argmax, soft CLOSE lean, bank when CLOSE>HOLD, or MFE-fade."""
    unreal = float(unrealized_edge)
    probs = pred_x.get("probs") if isinstance(pred_x.get("probs"), dict) else None
    close_p = float((probs or {}).get("CLOSE") or 0.0)
    hold_p = float((probs or {}).get("HOLD") or 0.0)
    action = str(pred_x.get("action") or "HOLD").upper()
    hard = model_exit_min_edge(tp_pct, frac=hard_frac)
    if action == "CLOSE" and unreal >= hard - 1e-12:
        return True
    soft = model_exit_min_edge(tp_pct, frac=soft_frac)
    if close_p >= float(soft_close_p) and unreal >= soft - 1e-12:
        return True
    bank = model_exit_min_edge(tp_pct, frac=bank_frac)
    if close_p > hold_p and unreal >= bank - 1e-12:
        return True
    # Peak MFE then giveback → bank earlier (complements time_stop on bar walk).
    if mfe_pct is not None:
        mfe = float(mfe_pct)
        arm = model_exit_min_edge(tp_pct, frac=mfe_arm_frac)
        if arm <= 0:
            arm = DEFAULT_TIME_STOP_MIN_ABS
        if mfe >= arm - 1e-12 and unreal <= mfe * float(mfe_keep_frac) + 1e-12:
            mfe_bank = model_exit_min_edge(tp_pct, frac=mfe_bank_frac)
            if unreal >= mfe_bank - 1e-12 and (
                close_p >= float(mfe_close_p) or close_p >= hold_p
            ):
                return True
    return False


def time_stop_arm_threshold(tp_pct: float) -> float:
    """MFE that must be seen before time-stop can fire."""
    tp = max(0.0, float(tp_pct))
    return max(DEFAULT_TIME_STOP_MIN_ABS, tp * DEFAULT_TIME_STOP_ARM_TP_FRAC)


def should_time_stop(
    *,
    mfe_pct: float,
    cur_fav_pct: float,
    bars_held: int,
    horizon_exec: int,
    tp_pct: float = 0.0,
    arm_tp_frac: float = DEFAULT_TIME_STOP_ARM_TP_FRAC,
    keep_frac: float = DEFAULT_TIME_STOP_KEEP_FRAC,
    min_abs: float = DEFAULT_TIME_STOP_MIN_ABS,
    min_bars_frac: float = DEFAULT_TIME_STOP_MIN_BARS_FRAC,
    min_bars: int = DEFAULT_TIME_STOP_MIN_BARS,
) -> bool:
    """True when a real favorable move faded — exit before dead horizon."""
    h = max(1, int(horizon_exec))
    need_bars = max(int(min_bars), int(h * float(min_bars_frac)))
    if int(bars_held) < need_bars:
        return False
    arm = max(float(min_abs), max(0.0, float(tp_pct)) * float(arm_tp_frac))
    mfe = float(mfe_pct)
    if mfe < arm - 1e-12:
        return False
    cur = float(cur_fav_pct)
    # Gave back most of the peak move, or back to flat/red after having been armed.
    if cur <= mfe * float(keep_frac) + 1e-12:
        return True
    if cur <= 0.0:
        return True
    return False


def simulate_exec_exit(
    candles_exec: Sequence[dict[str, Any]],
    *,
    entry_ts: int,
    entry: float,
    action: str,
    horizon_exec: int,
    tp_pct: float = 0.0,
    sl_pct: float = 0.0,
    trail_pct: float = 0.0,
    trail_extreme: float | None = None,
) -> Optional[dict[str, Any]]:
    """Walk exec TF after entry; TP/SL/trailing on high/low, else exit at horizon close.

    Trailing activates only after favorable excursion ≥ trail_pct
    (BUY: extreme ≥ entry*(1+trail); SELL: extreme ≤ entry*(1-trail)).
    Then SL = extreme*(1∓trail), never looser than hard SL.
    ``trail_extreme`` seed is used only when the entry bar is missing from the
    window (scrolled out); if entry is visible, extreme is recomputed from path.
    If TP and SL both touch the same bar → pessimistic SL (paper honesty).
    Time-stop: after MFE armed (≥~0.28×TP), exit on close if move mostly given back
    (anti-horizon) — reason ``time_stop``.
    Returns None if not enough bars yet.
    """
    if entry <= 0 or not candles_exec:
        return None
    act = (action or "").upper()
    if act not in ("BUY", "SELL"):
        return None
    idx = find_entry_index(candles_exec, entry_ts)
    if idx < 0:
        return None

    h_exec = max(1, int(horizon_exec))
    tp = max(0.0, float(tp_pct))
    sl = max(0.0, float(sl_pct))
    trail = max(0.0, float(trail_pct))
    last_i = len(candles_exec) - 1
    start = idx + 1
    if start > last_i and last_i < idx + h_exec:
        return None

    end_i = min(last_i, idx + h_exec)
    if start > end_i:
        return None

    # Persist trail_extreme across ticks only when the entry bar scrolled out of the
    # candle window. If entry is still visible, always recompute from the path —
    # otherwise a seed from a *later* bar can false-trigger trail on an early bar
    # when we re-walk from start (MFE≈0, exit=extreme×(1±trail)).
    exact_entry = int(candles_exec[idx].get("open_time") or 0) == int(entry_ts)
    extreme = float(entry)
    if (
        not exact_entry
        and trail_extreme is not None
        and float(trail_extreme) > 0
    ):
        seed = float(trail_extreme)
        if act == "BUY":
            extreme = max(extreme, seed)
        else:
            extreme = min(extreme, seed)
    if act == "BUY":
        hard_sl = entry * (1.0 - sl) if sl > 0 else 0.0
    else:
        hard_sl = entry * (1.0 + sl) if sl > 0 else 0.0

    for i in range(start, end_i + 1):
        high, low, close = _bar_high_low(candles_exec[i])
        if act == "BUY":
            if high > extreme:
                extreme = high
        else:
            if extreme <= 0 or low < extreme:
                extreme = low

        hit_tp = False
        hit_sl = False
        tp_px = 0.0
        sl_px = 0.0
        reason_sl = "sl"
        trail_active = False
        trail_sl = 0.0

        if act == "BUY":
            if tp > 0:
                tp_px = entry * (1.0 + tp)
                hit_tp = high >= tp_px
            # Trail only after ≥ trail_pct favorable move (not on noise ticks).
            if trail > 0 and extreme >= entry * (1.0 + trail) - 1e-12:
                trail_sl = extreme * (1.0 - trail)
                trail_active = True
            candidates = [x for x in (hard_sl, trail_sl if trail_active else 0.0) if x > 0]
            if candidates:
                sl_px = max(candidates)
                hit_sl = low <= sl_px
                if trail_active and trail_sl >= hard_sl - 1e-15 and abs(sl_px - trail_sl) <= 1e-12 and hit_sl:
                    reason_sl = "trail"
        else:
            if tp > 0:
                tp_px = entry * (1.0 - tp)
                hit_tp = low <= tp_px
            if trail > 0 and extreme > 0 and extreme <= entry * (1.0 - trail) + 1e-12:
                trail_sl = extreme * (1.0 + trail)
                trail_active = True
            if hard_sl > 0 and trail_active and trail_sl > 0:
                sl_px = min(hard_sl, trail_sl)
            else:
                sl_px = hard_sl or trail_sl
            if sl_px > 0:
                hit_sl = high >= sl_px
                if (
                    trail_active
                    and trail_sl > 0
                    and (hard_sl <= 0 or trail_sl <= hard_sl + 1e-15)
                    and abs(sl_px - trail_sl) <= 1e-12
                    and hit_sl
                ):
                    reason_sl = "trail"

        if hit_sl and hit_tp:
            return {
                "exit": sl_px,
                "exit_ts": int(candles_exec[i]["open_time"]),
                "reason": reason_sl,
                "bars_held": i - idx,
                "ready": True,
                "trail_extreme": extreme,
            }
        if hit_sl:
            return {
                "exit": sl_px,
                "exit_ts": int(candles_exec[i]["open_time"]),
                "reason": reason_sl,
                "bars_held": i - idx,
                "ready": True,
                "trail_extreme": extreme,
            }
        if hit_tp:
            return {
                "exit": tp_px,
                "exit_ts": int(candles_exec[i]["open_time"]),
                "reason": "tp",
                "bars_held": i - idx,
                "ready": True,
                "trail_extreme": extreme,
            }

        # Anti-horizon: bank faded MFE on close (before hard horizon bar).
        if i < idx + h_exec:
            if act == "BUY":
                mfe_pct = (extreme - entry) / entry
                cur_fav = (close - entry) / entry
            else:
                mfe_pct = (entry - extreme) / entry if extreme > 0 else 0.0
                cur_fav = (entry - close) / entry
            if should_time_stop(
                mfe_pct=mfe_pct,
                cur_fav_pct=cur_fav,
                bars_held=i - idx,
                horizon_exec=h_exec,
                tp_pct=tp,
            ):
                return {
                    "exit": close,
                    "exit_ts": int(candles_exec[i]["open_time"]),
                    "reason": "time_stop",
                    "bars_held": i - idx,
                    "ready": True,
                    "trail_extreme": extreme,
                }

        if i == idx + h_exec:
            return {
                "exit": close,
                "exit_ts": int(candles_exec[i]["open_time"]),
                "reason": "horizon",
                "bars_held": h_exec,
                "ready": True,
                "trail_extreme": extreme,
            }

    age = last_i - idx
    return {
        "exit": None,
        "exit_ts": None,
        "reason": "wait",
        "bars_held": max(0, age),
        "ready": False,
        "left": max(0, h_exec - age),
        "horizon_exec": h_exec,
        "trail_extreme": extreme,
    }
