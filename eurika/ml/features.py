"""Lightweight candle features (no TA-lib).

Continuous indicators and structure — raw material for ML, not trade rules.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

FEATURE_NAMES = (
    # Core price / vol (legacy indices 0–11 kept for pad compatibility)
    "ret_1",
    "ret_4",
    "ret_window",
    "sma_ratio",
    "volatility",
    "hl_range",
    "vol_z",
    "atr_burst",
    "range_break",
    "rsi_14",
    "bb_pos",
    "macd_hist",
    # Dynamics / context (no trading thresholds)
    "rsi_delta",
    "bb_pos_delta",
    "macd_hist_delta",
    "bb_width",
    "dist_to_low_20",
    "dist_to_high_20",
    "dist_to_low_40",
    "dist_to_high_40",
    "dist_to_low_win",
    "dist_to_high_win",
    "sma_slope",
    "price_vs_sma_slow",
)

# Enough for RSI(14), BB(20), MACD(12/26/9) warm-up on the same chunk.
DEFAULT_WINDOW = 40

# Auto-extend paper horizon when breakout/impulse features fire.
DEFAULT_IMPULSE_HORIZON = 4
IMPULSE_ATR_BURST_THR = 0.5
IMPULSE_RANGE_BREAK_THR = 0.002

RSI_PERIOD = 14
BB_PERIOD = 20
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
SMA_SLOW_PERIOD = 40
SMA_SLOPE_LOOKBACK = 3


def _closes(candles: Sequence[dict[str, Any]]) -> list[float]:
    return [float(c["close"]) for c in candles]


def _true_ranges(chunk: Sequence[dict[str, Any]]) -> list[float]:
    """Wilder-style TR per bar (first bar uses high-low only)."""
    trs: list[float] = []
    prev_close: float | None = None
    for c in chunk:
        high = float(c.get("high") or c["close"])
        low = float(c.get("low") or c["close"])
        close = float(c["close"])
        hl = high - low
        if prev_close is None or prev_close <= 0:
            trs.append(max(0.0, hl))
        else:
            trs.append(max(hl, abs(high - prev_close), abs(low - prev_close)))
        prev_close = close
    return trs


def _ema(series: Sequence[float], period: int) -> list[float]:
    if not series:
        return []
    p = max(1, int(period))
    k = 2.0 / (p + 1)
    out = [float(series[0])]
    for x in series[1:]:
        out.append(float(x) * k + out[-1] * (1.0 - k))
    return out


def _rsi_centered(closes: Sequence[float], period: int = RSI_PERIOD) -> float:
    """RSI in roughly [-1, 1]: (rsi - 50) / 50. Neutral 0 if too short."""
    p = max(2, int(period))
    if len(closes) < p + 1:
        return 0.0
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - p, len(closes)):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / p
    avg_loss = losses / p
    if avg_loss < 1e-12:
        rsi = 100.0 if avg_gain > 1e-12 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    return (rsi - 50.0) / 50.0


def _bb_pos_width(closes: Sequence[float], period: int = BB_PERIOD) -> tuple[float, float]:
    """Return (bb_pos, bb_width). Width = 2σ / mid (scale-free)."""
    p = max(2, int(period))
    if len(closes) < p:
        return 0.0, 0.0
    window = closes[-p:]
    mid = sum(window) / p
    var = sum((x - mid) ** 2 for x in window) / p
    std = var**0.5
    if mid <= 1e-12 or std < 1e-12:
        return 0.0, 0.0
    pos = (closes[-1] - mid) / (2.0 * std)
    pos = max(-2.0, min(2.0, pos))
    width = (2.0 * std) / mid
    return pos, width


def _bb_pos(closes: Sequence[float], period: int = BB_PERIOD) -> float:
    """Close vs Bollinger mid in ~[-1, 1] (half-band = 1)."""
    return _bb_pos_width(closes, period=period)[0]


def _macd_hist_rel(
    closes: Sequence[float],
    *,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> float:
    """MACD histogram / last close (scale-free)."""
    if len(closes) < max(3, int(slow)):
        return 0.0
    last = float(closes[-1])
    if last <= 0:
        return 0.0
    ef = _ema(closes, fast)
    es = _ema(closes, slow)
    macd_line = [a - b for a, b in zip(ef, es)]
    sig = _ema(macd_line, signal)
    hist = macd_line[-1] - sig[-1]
    return hist / last


def _range_position(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    n: int,
) -> tuple[float, float]:
    """Position in N-bar range: dist_to_low, dist_to_high in [0, 1] of range.

    dist_to_low ≈ 0 near window low; dist_to_high ≈ 0 near window high.
    """
    if not closes or n < 2:
        return 0.5, 0.5
    use = min(int(n), len(closes), len(highs), len(lows))
    if use < 2:
        return 0.5, 0.5
    hi = max(highs[-use:])
    lo = min(lows[-use:])
    last = float(closes[-1])
    span = hi - lo
    if span < 1e-12:
        return 0.5, 0.5
    from_low = (last - lo) / span
    from_high = (hi - last) / span
    return max(0.0, min(1.0, from_low)), max(0.0, min(1.0, from_high))


def impulse_horizon(
    base_h: int,
    features: Mapping[str, float] | Sequence[float] | None,
    *,
    impulse_h: int = DEFAULT_IMPULSE_HORIZON,
    atr_thr: float = IMPULSE_ATR_BURST_THR,
    break_thr: float = IMPULSE_RANGE_BREAK_THR,
) -> int:
    """Return max(base, impulse) when ATR-burst or range-break exceeds thresholds."""
    h = max(1, int(base_h))
    ih = max(1, int(impulse_h))
    atr_burst = 0.0
    range_break = 0.0
    if isinstance(features, Mapping):
        atr_burst = float(features.get("atr_burst") or 0.0)
        range_break = float(features.get("range_break") or 0.0)
    elif isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        try:
            names = list(FEATURE_NAMES)
            if "atr_burst" in names and len(features) > names.index("atr_burst"):
                atr_burst = float(features[names.index("atr_burst")])
            if "range_break" in names and len(features) > names.index("range_break"):
                range_break = float(features[names.index("range_break")])
        except (TypeError, ValueError, IndexError):
            pass
    if atr_burst > atr_thr or abs(range_break) > break_thr:
        return max(h, ih)
    return h


def feature_vector(candles: Sequence[dict[str, Any]], *, window: int = DEFAULT_WINDOW) -> list[float] | None:
    """Build features from the last ``window`` candles. Needs >= window bars."""
    w = max(8, int(window))
    if len(candles) < w:
        return None
    chunk = list(candles[-w:])
    closes = _closes(chunk)
    last = closes[-1]
    if last <= 0:
        return None

    def ret(n: int) -> float:
        if len(closes) <= n or closes[-1 - n] <= 0:
            return 0.0
        return (closes[-1] / closes[-1 - n]) - 1.0

    ret_window = (closes[-1] / closes[0]) - 1.0 if closes[0] > 0 else 0.0
    sma = sum(closes) / len(closes)
    sma_ratio = (last / sma) - 1.0 if sma > 0 else 0.0

    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append((closes[i] / closes[i - 1]) - 1.0)
    if rets:
        mean_r = sum(rets) / len(rets)
        volatility = (sum((r - mean_r) ** 2 for r in rets) / len(rets)) ** 0.5
    else:
        volatility = 0.0

    highs = [float(c.get("high") or c["close"]) for c in chunk]
    lows = [float(c.get("low") or c["close"]) for c in chunk]
    hl_range = ((max(highs) - min(lows)) / last) if last else 0.0

    vols = [float(c.get("volume") or 0.0) for c in chunk]
    mean_v = sum(vols) / len(vols) if vols else 0.0
    if len(vols) > 1 and mean_v > 0:
        var_v = sum((v - mean_v) ** 2 for v in vols) / len(vols)
        std_v = var_v**0.5
        vol_z = (vols[-1] - mean_v) / std_v if std_v > 1e-12 else 0.0
    else:
        vol_z = 0.0

    trs = _true_ranges(chunk)
    mean_tr = sum(trs) / len(trs) if trs else 0.0
    if mean_tr > 1e-12:
        atr_burst = (trs[-1] / mean_tr) - 1.0
    else:
        atr_burst = 0.0

    # Breakout vs prior bars in the window (exclude last bar).
    if len(chunk) >= 2:
        prior_high = max(highs[:-1])
        prior_low = min(lows[:-1])
        if last > prior_high and last > 0:
            range_break = (last - prior_high) / last
        elif last < prior_low and last > 0:
            range_break = (last - prior_low) / last
        else:
            range_break = 0.0
    else:
        range_break = 0.0

    rsi_14 = _rsi_centered(closes)
    bb_pos, bb_width = _bb_pos_width(closes)
    macd_hist = _macd_hist_rel(closes)

    # Deltas vs previous bar (continuous — no thresholds).
    if len(closes) >= 2:
        prev = closes[:-1]
        rsi_delta = rsi_14 - _rsi_centered(prev)
        bb_prev, _ = _bb_pos_width(prev)
        bb_pos_delta = bb_pos - bb_prev
        macd_hist_delta = macd_hist - _macd_hist_rel(prev)
    else:
        rsi_delta = 0.0
        bb_pos_delta = 0.0
        macd_hist_delta = 0.0

    d20_lo, d20_hi = _range_position(closes, highs, lows, 20)
    d40_lo, d40_hi = _range_position(closes, highs, lows, 40)
    dwin_lo, dwin_hi = _range_position(closes, highs, lows, w)

    # Short SMA slope (lookback bars) and slow SMA position.
    slope_n = min(SMA_SLOPE_LOOKBACK, len(closes) - 1)
    if slope_n >= 1:
        sma_now = sum(closes[-min(8, len(closes)) :]) / min(8, len(closes))
        prev_slice = closes[-(min(8, len(closes)) + slope_n) : -slope_n]
        if prev_slice:
            sma_prev = sum(prev_slice) / len(prev_slice)
            sma_slope = (sma_now - sma_prev) / last if last > 0 else 0.0
        else:
            sma_slope = 0.0
    else:
        sma_slope = 0.0

    slow_n = min(SMA_SLOW_PERIOD, len(closes))
    sma_slow = sum(closes[-slow_n:]) / slow_n if slow_n else last
    price_vs_sma_slow = (last / sma_slow) - 1.0 if sma_slow > 0 else 0.0

    return [
        ret(1),
        ret(min(4, w - 1)),
        ret_window,
        sma_ratio,
        volatility,
        hl_range,
        vol_z,
        atr_burst,
        range_break,
        rsi_14,
        bb_pos,
        macd_hist,
        rsi_delta,
        bb_pos_delta,
        macd_hist_delta,
        bb_width,
        d20_lo,
        d20_hi,
        d40_lo,
        d40_hi,
        dwin_lo,
        dwin_hi,
        sma_slope,
        price_vs_sma_slow,
    ]


def features_dict(candles: Sequence[dict[str, Any]], *, window: int = DEFAULT_WINDOW) -> dict[str, float] | None:
    vec = feature_vector(candles, window=window)
    if vec is None:
        return None
    return {name: float(val) for name, val in zip(FEATURE_NAMES, vec)}
