"""One-ticker market brief from local candles + MLP + LLM shadow book."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from eurika.ml.cursor_hourly_brief import _tf_view, load_analysis_prefs
from eurika.ml.live_paper import load_open_positions
from eurika.ml.llm_shadow import load_shadow_opens
from eurika.ml.llm_shadow_orders import load_shadow_pending
from eurika.ml.market_model import predict_action, predict_levels
from eurika.ml.market_store import normalize_market


_SYMBOL_RE = re.compile(r"\b([A-Z]{2,15})USDT\b", re.I)
_BARE_SYM_RE = re.compile(
    r"\b(BTC|ETH|SOL|ADA|XAU|BNB|DOGE|XRP|LINK|AVAX|MU|SNDK|SOXL|KORU|SKHYNIX)\b",
    re.I,
)


def parse_ticker_request(message: str) -> tuple[str, str] | None:
    """Return (SYMBOL, market) from a chat ask, or None."""
    text = message or ""
    m = _SYMBOL_RE.search(text.upper().replace("/", ""))
    if m:
        symbol = m.group(1).upper() + "USDT"
    else:
        m2 = _BARE_SYM_RE.search(text)
        if not m2:
            return None
        symbol = m2.group(1).upper() + "USDT"
    low = text.lower()
    if any(tok in low for tok in ("fut", "фьюч", "perp", "perpetual")):
        market = "futures"
    elif "spot" in low or "спот" in low:
        market = "spot"
    else:
        market = "futures"
    return symbol, market


def _fmt_pct(val: object) -> str:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    return f"{x * 100:.2f}%"


def _fmt_num(val: object, digits: int = 4) -> str:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    return f"{x:.{digits}f}"


def _feat_line(feat: dict[str, Any]) -> str:
    keys = (
        "ret_1",
        "ret_4",
        "sma_ratio",
        "atr_burst",
        "bb_pos",
        "rsi_14",
        "macd_hist",
        "volatility",
        "vol_z",
        "range_break",
    )
    parts = []
    for k in keys:
        if k not in feat:
            continue
        try:
            parts.append(f"{k}={float(feat[k]):+.4f}")
        except (TypeError, ValueError):
            continue
    return ", ".join(parts) if parts else "нет фич (нужен sync/Live)"


def format_ticker_market_brief(
    project_root: str | Path,
    symbol: str,
    *,
    market: str = "futures",
    sync: bool = True,
) -> str:
    """Structured TF1/TF2 + MLP + shadow brief for one symbol."""
    root = Path(project_root).resolve()
    sym = str(symbol or "").strip().upper()
    kind = normalize_market(market)
    book = "fut" if kind == "futures" else "spot"
    tf1, tf2, _markets = load_analysis_prefs(root)

    if sync:
        try:
            from eurika.ml.market_store import sync_klines

            for interval in dict.fromkeys([tf1, tf2, "1m"]):
                try:
                    sync_klines(root, symbol=sym, interval=interval, market=kind, limit=200)
                except Exception:
                    continue
        except Exception:
            pass

    v1 = _tf_view(root, sym, book, tf1)
    v2 = _tf_view(root, sym, book, tf2)
    f1 = v1.get("features") or {}
    f2 = v2.get("features") or {}
    close = v1.get("close") if v1.get("close") is not None else v2.get("close")

    vec = v1.get("feature_vec") or v2.get("feature_vec") or []
    pred: dict[str, Any] = {}
    levels: dict[str, Any] = {}
    if vec:
        try:
            pred = predict_action(root, vec) or {}
        except Exception as exc:
            pred = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            levels = predict_levels(root, vec) or {}
        except Exception as exc:
            levels = {"error": f"{type(exc).__name__}: {exc}"}

    action = str(pred.get("action") or "—")
    probs = pred.get("probs") if isinstance(pred.get("probs"), dict) else {}
    tp = levels.get("tp_pct")
    sl = levels.get("sl_pct")
    trail = levels.get("trail_pct")

    opens = [
        p
        for p in load_open_positions(root)
        if str(p.get("symbol") or "").upper() == sym
        and normalize_market(p.get("market")) == kind
        and not p.get("shadow")
    ]
    llm_opens = [
        p
        for p in load_shadow_opens(root)
        if str(p.get("symbol") or "").upper() == sym and normalize_market(p.get("market")) == kind
    ]
    llm_pend = [
        p
        for p in load_shadow_pending(root)
        if str(p.get("symbol") or "").upper() == sym and normalize_market(p.get("market")) == kind
    ]

    # Simple dual-TF read (not indicator-rules; descriptive).
    ret4_1 = float(f1.get("ret_4") or 0.0)
    sma2 = float(f2.get("sma_ratio") or 0.0)
    if action == "BUY" and sma2 > 0 and ret4_1 >= 0:
        bias = "скорее продолжение вверх на старшем ТФ при согласии 15m"
    elif action == "SELL" and sma2 < 0:
        bias = "скорее давление вниз"
    elif sma2 > 0.03 and ret4_1 < 0:
        bias = "1h ещё выше SMA, 15m откат — не chase market-long"
    elif sma2 < -0.03 and ret4_1 > 0:
        bias = "1h слаб, 15m отскок — осторожно с лонгом"
    else:
        bias = "смешанный / ждать уровень"

    entry_hint = "HOLD / ждать"
    if action == "BUY":
        entry_hint = "MLP: BUY (общая policy, не per-ticker стратегия)"
    elif action == "SELL":
        entry_hint = "MLP: SELL (общая policy)"

    lines = [
        f"## {sym} [{book}] — разбор",
        "",
        f"Цена (TF1={tf1}): **{_fmt_num(close, 2) if close else '—'}**",
        f"Перспектива (описательно по TF1/TF2): {bias}",
        "",
        f"### TF1 {tf1}",
        _feat_line(f1) if f1 else "_нет свечей — включи Live или sync_",
        "",
        f"### TF2 {tf2}",
        _feat_line(f2) if f2 else "_нет свечей_",
        "",
        "### MLP (общая модель)",
        f"Сторона: **{action}**"
        + (
            f" · HOLD={probs.get('HOLD', 0):.2f} BUY={probs.get('BUY', 0):.2f} "
            f"SELL={probs.get('SELL', 0):.2f}"
            if probs
            else ""
        ),
        f"Уровни модели: TP {_fmt_pct(tp)}, SL {_fmt_pct(sl)}, trail {_fmt_pct(trail)}"
        + (f" [{levels.get('source')}]" if levels.get("source") else ""),
        f"Вход: {entry_hint}",
        "",
        "### Книги сейчас",
    ]
    if opens:
        for p in opens:
            lines.append(
                f"- MLP paper: {p.get('action')} entry={_fmt_num(p.get('entry'), 2)} "
                f"tp={_fmt_pct(p.get('tp_pct'))} sl={_fmt_pct(p.get('sl_pct'))}"
            )
    else:
        lines.append("- MLP paper: нет open")
    if llm_opens:
        for p in llm_opens:
            lines.append(
                f"- LLM shadow open: {p.get('action')} entry={_fmt_num(p.get('entry'), 2)} "
                f"tp={_fmt_pct(p.get('tp_pct'))} sl={_fmt_pct(p.get('sl_pct'))}"
            )
    else:
        lines.append("- LLM shadow open: нет")
    if llm_pend:
        for p in llm_pend:
            lines.append(
                f"- LLM pending: {p.get('action')} {p.get('entry_style')} "
                f"limit={_fmt_num(p.get('limit_px'), 2)} stop={_fmt_num(p.get('stop_px'), 2)} "
                f"tp={_fmt_pct(p.get('tp_pct'))} sl={_fmt_pct(p.get('sl_pct'))}"
            )
    else:
        lines.append("- LLM pending: нет")

    lines.extend(
        [
            "",
            "_Это paper-разбор по локальным свечам Binance sync; live-ордеров нет. "
            "MLP — общая policy на форму движения, не отдельная стратегия тикера._",
        ]
    )
    return "\n".join(lines)
