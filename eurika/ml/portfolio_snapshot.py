"""Holistic market snapshot: full USDT-M futures universe + book priority."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Sequence

from eurika.ml.assistant_paper import SCAN_SYMBOLS, load_opens, load_pending
from eurika.ml.cursor_hourly_brief import (
    DEFAULT_TF1,
    DEFAULT_TF2,
    _feat_bits,
    _num,
    _tf_view,
    collect_ticker_cards,
    format_ticker_cards,
    load_analysis_prefs,
)
from eurika.ml.earn_monitor import DEFAULT_EARN_ASSETS, format_earn_book_for_prompt, load_earn_rates
from eurika.ml.market_store import ml_root, sync_klines
from eurika.ml.universe import load_ticker_lists

MAX_SNAPSHOT_CARDS = 28
MAX_OVERVIEW_ROWS = 40
FUTURES_UNIVERSE_TTL_MS = 6 * 60 * 60 * 1000


def futures_universe_cache_path(root: str | Path) -> Path:
    return ml_root(root) / "futures_universe_cache.json"


def _now_ms() -> int:
    return int(time.time() * 1000)


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


def book_futures_symbols(root: str | Path) -> list[str]:
    """Assistant opens + pending futures symbols (priority set)."""
    out: list[str] = []
    seen: set[str] = set()
    for row in list(load_opens(root)) + list(load_pending(root)):
        sym = str(row.get("symbol") or "").upper()
        mk = str(row.get("market") or "").lower()
        if mk and mk not in {"futures", "fut", "um", "perp", "perpetual"}:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def load_futures_universe(
    root: str | Path,
    *,
    force_refresh: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """USDT-M perpetual symbols from Binance (cached) or ticker_lists fallback."""
    root = Path(root).resolve()
    now = int(now_ms or _now_ms())
    path = futures_universe_cache_path(root)
    cached = _read_json(path, {})
    if (
        not force_refresh
        and isinstance(cached, dict)
        and isinstance(cached.get("symbols"), list)
        and cached.get("symbols")
        and now - int(cached.get("fetched_ms") or 0) < FUTURES_UNIVERSE_TTL_MS
    ):
        return {
            "ok": True,
            "symbols": [str(s).upper() for s in cached["symbols"] if str(s).strip()],
            "source": "cache",
            "fetched_ms": int(cached.get("fetched_ms") or 0),
            "error": None,
        }

    from eurika.integrations.binance_readonly import list_usdtm_perpetuals

    try:
        live = list_usdtm_perpetuals()
    except Exception as exc:
        live = {"ok": False, "symbols": [], "error": str(exc)}

    if live.get("ok") and live.get("symbols"):
        symbols = [str(s).upper() for s in live["symbols"]]
        blob = {"fetched_ms": now, "count": len(symbols), "symbols": symbols}
        _write_json(path, blob)
        return {"ok": True, "symbols": symbols, "source": "binance", "fetched_ms": now, "error": None}

    lists = load_ticker_lists(root)
    fallback = [str(s).upper() for s in (lists.get("futures") or SCAN_SYMBOLS) if str(s).strip()]
    for sym in book_futures_symbols(root):
        if sym not in fallback:
            fallback.append(sym)
    return {
        "ok": bool(fallback),
        "symbols": fallback,
        "source": "ticker_lists_fallback",
        "fetched_ms": int(cached.get("fetched_ms") or 0) if isinstance(cached, dict) else 0,
        "error": live.get("error"),
    }


def fetch_futures_24hr_rows() -> dict[str, Any]:
    from eurika.integrations.binance_readonly import futures_ticker_24hr

    try:
        return futures_ticker_24hr()
    except Exception as exc:
        return {"ok": False, "rows": [], "count": 0, "error": str(exc)}


def select_detail_futures_symbols(
    universe: Sequence[str],
    rows_24hr: Sequence[dict[str, Any]],
    *,
    book: Sequence[str],
    limit: int = MAX_SNAPSHOT_CARDS,
) -> list[str]:
    """Book first, then strongest 24h movers among the full universe."""
    limit = max(1, int(limit))
    uni = {str(s).upper() for s in universe if str(s).strip()}
    chosen: list[str] = []
    seen: set[str] = set()
    for sym in book:
        s = str(sym).upper()
        if s and s not in seen:
            seen.add(s)
            chosen.append(s)
    by_sym = {str(r.get("symbol") or "").upper(): r for r in rows_24hr if isinstance(r, dict)}

    def _move_score(sym: str) -> tuple[float, float]:
        row = by_sym.get(sym) or {}
        chg = abs(float(row.get("price_change_pct") or 0.0))
        vol = float(row.get("quote_volume") or 0.0)
        return (chg, vol)

    movers = sorted(
        [s for s in uni if s not in seen],
        key=lambda s: _move_score(s),
        reverse=True,
    )
    for sym in movers:
        if len(chosen) >= limit:
            break
        chosen.append(sym)
        seen.add(sym)
    # If 24hr empty, fill from universe order.
    if len(chosen) < limit:
        for sym in universe:
            s = str(sym).upper()
            if not s or s in seen:
                continue
            chosen.append(s)
            seen.add(s)
            if len(chosen) >= limit:
                break
    return chosen[:limit]


def collect_portfolio_pairs(root: str | Path) -> list[tuple[str, str]]:
    """Pairs for sync/snapshot. Futures-only: full universe + book; else ticker lists."""
    root = Path(root).resolve()
    try:
        from eurika.ml.portfolio_agent import PORTFOLIO_FUTURES_ONLY
    except Exception:
        PORTFOLIO_FUTURES_ONLY = False

    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []

    if PORTFOLIO_FUTURES_ONLY:
        uni = load_futures_universe(root)
        rows = fetch_futures_24hr_rows().get("rows") or []
        book = book_futures_symbols(root)
        for sym in select_detail_futures_symbols(uni.get("symbols") or [], rows, book=book):
            key = (sym, "fut")
            if key not in seen:
                seen.add(key)
                pairs.append(key)
        return pairs

    lists = load_ticker_lists(root)
    for sym in lists.get("spot") or []:
        key = (str(sym).upper(), "spot")
        if key[0] and key not in seen:
            seen.add(key)
            pairs.append(key)
    for sym in lists.get("futures") or []:
        key = (str(sym).upper(), "fut")
        if key[0] and key not in seen:
            seen.add(key)
            pairs.append(key)
    for row in list(load_opens(root)) + list(load_pending(root)):
        sym = str(row.get("symbol") or "").upper()
        mk = "fut" if str(row.get("market") or "").lower() in {"futures", "fut"} else "spot"
        key = (sym, mk)
        if sym and key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def _annotate_assistant_book(root: str | Path, cards: list[dict[str, Any]]) -> None:
    opens = {
        str(p.get("symbol") or "").upper(): p
        for p in load_opens(root)
        if str(p.get("market") or "").lower() in {"", "futures", "fut", "um", "perp", "perpetual"}
    }
    pending = {
        str(p.get("symbol") or "").upper(): p
        for p in load_pending(root)
        if str(p.get("market") or "").lower() in {"", "futures", "fut", "um", "perp", "perpetual"}
    }
    for card in cards:
        if str(card.get("market") or "") not in {"fut", "futures"}:
            continue
        sym = str(card.get("symbol") or "").upper()
        if sym in opens:
            pos = opens[sym]
            card["book"] = "open"
            card["side"] = str(pos.get("action") or "").upper()
            entry = pos.get("entry") or pos.get("signal_px")
            if isinstance(entry, (int, float)):
                card["entry"] = float(entry)
        elif sym in pending:
            order = pending[sym]
            card["book"] = "pending"
            card["side"] = str(order.get("action") or "").upper()
            entry = order.get("limit_px") or order.get("stop_px") or order.get("signal_px")
            if isinstance(entry, (int, float)):
                card["entry"] = float(entry)


def rank_portfolio_cards(cards: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize assistant book (open/pending), then movers."""

    def _score(card: dict[str, Any]) -> tuple:
        raw_feat = card.get("features")
        feat: dict[str, Any] = raw_feat if isinstance(raw_feat, dict) else {}
        book = str(card.get("book") or "")
        book_rank = 0 if book == "open" else (1 if book == "pending" else 2)
        return (
            book_rank,
            0 if card.get("feature_vec") else 1,
            -abs(float(feat.get("atr_burst") or 0.0)),
            -abs(float(feat.get("ret_1") or 0.0)),
            str(card.get("symbol") or ""),
        )

    ranked = sorted(cards, key=_score)
    return ranked[:MAX_SNAPSHOT_CARDS]


def ensure_portfolio_candles(root: str | Path, *, limit_1m: int = 400) -> None:
    """Sync TF1/TF2 + 1m for detail symbols (book + top movers), not the whole exchange."""
    root = Path(root).resolve()
    tf1, tf2, _markets = load_analysis_prefs(root)
    pairs = collect_portfolio_pairs(root)
    store_kinds = {"spot": "spot", "fut": "futures"}
    seen_iv = list(dict.fromkeys([tf1, tf2]))
    for symbol, market in pairs:
        kind = store_kinds.get(market, "futures")
        for interval in seen_iv:
            try:
                sync_klines(root, symbol=symbol, interval=interval, market=kind, limit=200)
            except Exception:
                continue
        try:
            sync_klines(root, symbol=symbol, interval="1m", market=kind, limit=limit_1m)
        except Exception:
            continue


def _format_futures_overview(
    *,
    universe_n: int,
    source: str,
    rows: Sequence[dict[str, Any]],
    book: Sequence[str],
) -> str:
    lines = [
        f"FUTURES UNIVERSE USDT-M perpetuals n={universe_n} source={source}",
        "  (полный рынок через Binance 24h ticker; детальные карточки — book + топ movers)",
    ]
    if book:
        lines.append("BOOK PRIORITY: " + ", ".join(book))
    ranked = sorted(
        [r for r in rows if isinstance(r, dict) and r.get("symbol")],
        key=lambda r: abs(float(r.get("price_change_pct") or 0.0)),
        reverse=True,
    )[:MAX_OVERVIEW_ROWS]
    if not ranked:
        lines.append("  24h overview: (нет данных — сеть/API)")
        return "\n".join(lines)
    lines.append(f"TOP {len(ranked)} by |24h%|:")
    for row in ranked:
        chg = float(row.get("price_change_pct") or 0.0)
        vol = float(row.get("quote_volume") or 0.0)
        last = row.get("last_price")
        last_s = f"{float(last):.6g}" if isinstance(last, (int, float)) else "n/a"
        vol_s = f"{vol/1e6:.1f}M" if vol >= 1e6 else f"{vol:.0f}"
        mark = " *" if str(row.get("symbol")).upper() in {b.upper() for b in book} else ""
        lines.append(
            f"  {row.get('symbol')}{mark} chg={chg:+.2f}% last={last_s} qvol={vol_s}"
        )
    return "\n".join(lines)


def _build_detail_cards(root: Path, symbols: Sequence[str], *, tf1: str, tf2: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for symbol in symbols:
        sym = str(symbol).upper()
        if not sym:
            continue
        view1 = _tf_view(root, sym, "fut", tf1)
        view2 = _tf_view(root, sym, "fut", tf2)
        vec = view1.get("feature_vec") or view2.get("feature_vec") or []
        cards.append(
            {
                "symbol": sym,
                "market": "fut",
                "tf1": tf1,
                "tf2": tf2,
                "interval": tf1,
                "interval2": tf2,
                "close": view1.get("close") if view1.get("close") is not None else view2.get("close"),
                "bars": view1.get("bars") or 0,
                "bars2": view2.get("bars") or 0,
                "features": view1.get("features") or {},
                "features2": view2.get("features") or {},
                "feature_vec": [float(v) for v in vec],
                "view1": view1,
                "view2": view2,
                "book": "flat",
            }
        )
    return cards


def build_portfolio_market_snapshot(root: str | Path) -> tuple[list[dict[str, Any]], str]:
    """Cards + formatted MARKET SNAPSHOT block."""
    root = Path(root).resolve()
    try:
        from eurika.ml.portfolio_agent import PORTFOLIO_FUTURES_ONLY
    except Exception:
        PORTFOLIO_FUTURES_ONLY = False

    if not PORTFOLIO_FUTURES_ONLY:
        cards = collect_ticker_cards(root)
        _annotate_assistant_book(root, cards)
        cards = rank_portfolio_cards(cards)
        tf1, tf2, markets = load_analysis_prefs(root)
        text = format_ticker_cards(cards, markets=markets)
        if not cards:
            pairs = collect_portfolio_pairs(root)[:MAX_SNAPSHOT_CARDS]
            mini: list[dict[str, Any]] = []
            for symbol, market in pairs:
                view1 = _tf_view(root, symbol, market, tf1)
                view2 = _tf_view(root, symbol, market, tf2)
                mini.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "tf1": tf1,
                        "tf2": tf2,
                        "view1": view1,
                        "view2": view2,
                        "features": view1.get("features") or {},
                        "feature_vec": view1.get("feature_vec") or view2.get("feature_vec") or [],
                        "book": "flat",
                    }
                )
            cards = mini
            lines = [f"MARKET SNAPSHOT TF1={tf1} TF2={tf2} (lists; candles partial)"]
            for card in cards:
                lines.append(f"  {card.get('symbol')} [{card.get('market')}]")
                for tag, view in (("TF1", card.get("view1")), ("TF2", card.get("view2"))):
                    block = view if isinstance(view, dict) else {}
                    head = f"    {tag} {block.get('interval') or '?'} close={_num(block.get('close'))}"
                    bits = _feat_bits(block.get("features"))
                    lines.append(head)
                    if bits:
                        lines.append("      " + " ".join(bits))
            text = "\n".join(lines)
        return cards, text

    # Futures-only: scan whole USDT-M universe; detail book + movers.
    tf1, tf2, _markets = load_analysis_prefs(root)
    tf1 = tf1 or DEFAULT_TF1
    tf2 = tf2 or DEFAULT_TF2
    uni = load_futures_universe(root)
    tick = fetch_futures_24hr_rows()
    rows = [r for r in (tick.get("rows") or []) if str(r.get("symbol") or "").upper() in set(uni.get("symbols") or [])]
    if not rows:
        rows = list(tick.get("rows") or [])
    book = book_futures_symbols(root)
    detail_syms = select_detail_futures_symbols(uni.get("symbols") or [], rows, book=book)
    cards = _build_detail_cards(root, detail_syms, tf1=tf1, tf2=tf2)
    _annotate_assistant_book(root, cards)
    cards = rank_portfolio_cards(cards)
    overview = _format_futures_overview(
        universe_n=len(uni.get("symbols") or []),
        source=str(uni.get("source") or "?"),
        rows=rows,
        book=book,
    )
    detail = format_ticker_cards(cards, markets="futures")
    book_lines = [
        f"  {c.get('symbol')} [{c.get('market')}] {c.get('book')} {c.get('side') or '?'} @ {_num(c.get('entry'))}"
        for c in cards
        if c.get("book") in {"open", "pending"}
    ]
    extra = ""
    if book_lines:
        extra = "\nASSISTANT BOOK (приоритет анализа)\n" + "\n".join(book_lines)
    text = overview + "\n\n" + detail + extra
    return cards, text


def format_portfolio_books(root: str | Path, *, rates: dict[str, Any] | None = None) -> str:
    from eurika.ml.assistant_paper import format_assistant_book_for_prompt
    from eurika.ml.holistic_portfolio import format_holistic_for_prompt

    try:
        from eurika.ml.portfolio_agent import PORTFOLIO_FUTURES_ONLY
    except Exception:
        PORTFOLIO_FUTURES_ONLY = False

    blocks = [
        format_holistic_for_prompt(root),
        format_assistant_book_for_prompt(root),
    ]
    if not PORTFOLIO_FUTURES_ONLY:
        blocks.append(format_earn_book_for_prompt(root, rates=rates or load_earn_rates(root)))
    return "\n\n".join(blocks)


def expand_portfolio_universe(
    root: str | Path,
    *,
    max_spot: int = 32,
    max_futures: int = 32,
) -> dict[str, Any]:
    """Refresh futures universe for holistic; spot lists only when not futures-only."""
    from eurika.ml.universe import load_ticker_lists, save_ticker_lists, symbols_from_balances

    root = Path(root).resolve()
    try:
        from eurika.ml.portfolio_agent import PORTFOLIO_FUTURES_ONLY
    except Exception:
        PORTFOLIO_FUTURES_ONLY = False

    if PORTFOLIO_FUTURES_ONLY:
        uni = load_futures_universe(root, force_refresh=False)
        return {
            "spot_n": 0,
            "fut_n": len(uni.get("symbols") or []),
            "spot_added": [],
            "balances_ok": False,
            "futures_source": uni.get("source"),
            "futures_error": uni.get("error"),
        }

    lists = load_ticker_lists(root)
    spot = list(lists.get("spot") or [])
    fut = list(lists.get("futures") or [])
    added_spot: list[str] = []
    bal_info: dict[str, Any] = {"ok": False, "count": 0}
    try:
        bal_info = symbols_from_balances(project_root=root, max_symbols=max_spot)
        for sym in bal_info.get("symbols") or []:
            s = str(sym).upper()
            if s and s not in spot:
                spot.append(s)
                added_spot.append(s)
    except Exception:
        pass
    if not fut:
        for sym in SCAN_SYMBOLS:
            if sym not in fut:
                fut.append(sym)
    spot = spot[:max_spot]
    fut = fut[:max_futures]
    save_ticker_lists(root, spot=spot, futures=fut)
    return {
        "spot_n": len(spot),
        "fut_n": len(fut),
        "spot_added": added_spot,
        "balances_ok": bool(bal_info.get("ok")),
    }


def format_universe_overview(root: str | Path) -> str:
    try:
        from eurika.ml.portfolio_agent import PORTFOLIO_FUTURES_ONLY
    except Exception:
        PORTFOLIO_FUTURES_ONLY = False

    if PORTFOLIO_FUTURES_ONLY:
        uni = load_futures_universe(root)
        book = book_futures_symbols(root)
        return (
            f"UNIVERSE mode=futures_only usdtm_perps={len(uni.get('symbols') or [])} "
            f"source={uni.get('source')} book={len(book)} "
            f"(полный Binance USDT-M; не ticker_lists.json)"
        )

    lists = load_ticker_lists(root)
    spot_n = len(lists.get("spot") or [])
    fut_n = len(lists.get("futures") or [])
    earn_assets = ", ".join(DEFAULT_EARN_ASSETS)
    return (
        f"UNIVERSE spot_tickers={spot_n} fut_tickers={fut_n} "
        f"earn_assets={earn_assets} (lists from .eurika/ml/ticker_lists.json)"
    )
