"""Read-only market snapshot for the Cursor hourly teacher.

Candles and features only. Does not tick, open paper, or echo MLP decisions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eurika.ml.features import FEATURE_NAMES, feature_vector, features_dict
from eurika.ml.live_paper import load_open_positions
from eurika.ml.market_store import load_candles, ml_root
from eurika.ml.universe import load_ticker_lists

MAX_CARDS = 40  # safety ceiling only; normally the full Market ticker list
LLM_TF_CHOICES = ("5m", "15m", "1h", "4h")
DEFAULT_TF1 = "15m"
DEFAULT_TF2 = "1h"
_PROMPT_FEATURES = (
    "ret_1",
    "ret_4",
    "sma_ratio",
    "volatility",
    "atr_burst",
    "range_break",
    "rsi_14",
    "macd_hist",
    "bb_pos",
)

LEADING_HAND_RULES = (
    "Ты независимый разбор рынка для paper-ML Eurika: читаешь принудительно TF1 и TF2 "
    "из MARKET SNAPSHOT (оба ТФ, не один), даёшь СВОЙ совет на ближайшие 15 минут.\n"
    "Не пересказывай решения MLP, ворот cost-gate, shadow-книги и TP/SL модели. "
    "Не оправдывай HOLD/ждать тем, что «ворота отклонили» — это экзамен MLP, не твой вердикт.\n"
    "По КАЖДОМУ тикеру из MARKET SNAPSHOT:\n"
    "  тикер / вход: да|нет|ждать / когда / сторона: BUY|SELL|HOLD / "
    "почему (цена, импульс, структура на TF1 и TF2) / плечо если уместно / свои TP·SL.\n"
    "LIVE BOOK — только чтобы не звать второй live-вход по уже открытому paper; "
    "на совет по стороне и уровням это не влияет.\n"
    "Paper-вход в бою исполняет только MLP+ворота. Не live-ордер на биржу. "
    "Не проси включить Исследование/explore. Не подменяй argmax модели.\n"
    "\n"
    "LLM SHADOW — твоя отдельная книга (не MLP paper). Проза в ленте ордера НЕ ставит. "
    "Любой сетап с уровнем/условием входа обязан быть явным элементом shadow_actions:\n"
    "  • вход сейчас → action=open, entry_style=market, side=BUY|SELL, tp_pct/sl_pct[/trail_pct];\n"
    "  • ждать уровень / отскок / пробой → action=place + entry_style=limit|stop|oco "
    "и ЧИСЛА: limit_px и/или stop_px (и invalidate_px при необходимости), не словами;\n"
    "  • нет сетапа → samples.enter=no|wait и НЕ добавляй place/open по тикеру;\n"
    "  • уже есть LLM SHADOW OPENS/PENDING → hold | update (цены·TP·SL) | cancel | close | add.\n"
    "samples — метки для MLP; shadow_actions — приказы исполнения. Оба блока обязательны в одном JSON.\n"
    "R:R: цель TP≈3×SL (пример 2.4%/0.8%); не ставь TP≤SL. samples+shadow уровни — доли.\n"
    "В конце 2–3 строки вердикта, затем ОДИН JSON:\n"
    '{"samples":[{"symbol":"BTCUSDT","market":"fut","enter":"yes|no|wait",'
    '"side":"BUY|SELL|HOLD","when":"now|wait","leverage":2.0,'
    '"tp_pct":0.024,"sl_pct":0.008,"trail_pct":0.008}],'
    '"shadow_actions":[{"symbol":"BTCUSDT","market":"fut","action":"place",'
    '"side":"BUY","entry_style":"limit","limit_px":71000.0,'
    '"tp_pct":0.024,"sl_pct":0.008,"trail_pct":0.008}]}\n'
    "tp_pct/sl_pct — доли (0.024 = 2.4%), не проценты. Только тикеры из снимка.\n"
    "enter=yes + when=now → обычно open/market; enter=wait с уровнем → place (не молчать).\n"
)


def _mk(market: object) -> str:
    return "fut" if str(market or "spot").lower() in {"futures", "fut"} else "spot"


def _store_market(market: str) -> str:
    return "futures" if market == "fut" else "spot"


def _key(symbol: object, market: object) -> tuple[str, str]:
    return (str(symbol or "").strip().upper(), _mk(market))


def normalize_tf(raw: object, fallback: str) -> str:
    text = str(raw or "").strip().lower()
    return text if text in LLM_TF_CHOICES else fallback


def analysis_prefs_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_analysis.json"


def _normalize_markets(raw: object) -> str:
    text = str(raw or "both").strip().lower()
    if text in {"futures", "fut", "perp"}:
        return "futures"
    if text in {"spot"}:
        return "spot"
    return "both"


def _wanted_books(markets: str) -> set[str]:
    if markets == "futures":
        return {"fut"}
    if markets == "spot":
        return {"spot"}
    return {"spot", "fut"}


def wanted_store_kinds(markets: str) -> set[str]:
    if markets == "futures":
        return {"futures"}
    if markets == "spot":
        return {"spot"}
    return {"spot", "futures"}


def load_analysis_prefs(project_root: str | Path) -> tuple[str, str, str]:
    path = analysis_prefs_path(project_root)
    tf1, tf2, markets = DEFAULT_TF1, DEFAULT_TF2, "both"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            tf1 = normalize_tf(data.get("tf1"), DEFAULT_TF1)
            tf2 = normalize_tf(data.get("tf2"), DEFAULT_TF2)
            markets = _normalize_markets(data.get("markets"))
    return tf1, tf2, markets


def save_analysis_prefs(
    project_root: str | Path,
    tf1: object,
    tf2: object,
    markets: object = "both",
) -> Path:
    path = analysis_prefs_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tf1": normalize_tf(tf1, DEFAULT_TF1),
        "tf2": normalize_tf(tf2, DEFAULT_TF2),
        "markets": _normalize_markets(markets),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _tf_view(
    project_root: Path,
    symbol: str,
    market: str,
    interval: str,
) -> dict[str, Any]:
    kind = _store_market(market)
    candles = load_candles(project_root, symbol, interval, market=kind)
    feat = features_dict(candles) if candles else None
    vec = feature_vector(candles) if candles else None
    last = candles[-1] if candles else None
    close = None
    if isinstance(last, dict) and isinstance(last.get("close"), (int, float)):
        close = float(last["close"])
    return {
        "interval": interval,
        "close": close,
        "bars": len(candles),
        "features": dict(feat or {}),
        "feature_vec": [float(v) for v in (vec or [])],
    }


def _feat_bits(feat: object) -> list[str]:
    bits: list[str] = []
    if not isinstance(feat, dict):
        return bits
    for name in _PROMPT_FEATURES:
        if name not in FEATURE_NAMES:
            continue
        val = feat.get(name)
        if isinstance(val, (int, float)):
            bits.append(f"{name}={float(val):+.4f}")
    return bits


def _num(val: object, digits: int = 4) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):.{digits}f}"
    return "n/a"


def collect_ticker_cards(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Ticker dicts from lists + candles/features (not MLP analysis)."""
    del now_ms  # kept for call-site compatibility
    root = Path(project_root).resolve()
    lists = load_ticker_lists(root)
    tf1, tf2, markets = load_analysis_prefs(root)
    wanted = _wanted_books(markets)
    pairs: list[tuple[str, str]] = []
    if "spot" in wanted:
        pairs.extend((sym, "spot") for sym in lists.get("spot") or [])
    if "fut" in wanted:
        pairs.extend((sym, "fut") for sym in lists.get("futures") or [])
    if not pairs:
        for pos in load_open_positions(root):
            if pos.get("shadow"):
                continue
            key = _key(pos.get("symbol"), pos.get("market"))
            if key[0] and key[1] in wanted:
                pairs.append(key)

    seen: set[tuple[str, str]] = set()
    cards: list[dict[str, Any]] = []
    for symbol, market in pairs:
        key = _key(symbol, market)
        if not key[0] or key in seen:
            continue
        seen.add(key)
        view1 = _tf_view(root, key[0], key[1], tf1)
        view2 = _tf_view(root, key[0], key[1], tf2)
        vec = view1.get("feature_vec") or view2.get("feature_vec") or []
        cards.append(
            {
                "symbol": key[0],
                "market": key[1],
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

    live: dict[tuple[str, str], dict[str, Any]] = {}
    for pos in load_open_positions(root):
        if pos.get("shadow"):
            continue
        key = _key(pos.get("symbol"), pos.get("market"))
        if not key[0]:
            continue
        live[key] = pos
    # Keep LLM shadow opens/pendings in the snapshot even when the list is long.
    shadow_keys: set[tuple[str, str]] = set()
    try:
        from eurika.ml.llm_shadow import load_shadow_opens
        from eurika.ml.llm_shadow_orders import load_shadow_pending

        for row in list(load_shadow_opens(root)) + list(load_shadow_pending(root)):
            key = _key(row.get("symbol"), row.get("market"))
            if key[0]:
                shadow_keys.add(key)
    except Exception:
        shadow_keys = set()
    for card in cards:
        open_pos = live.get(_key(card["symbol"], card["market"]))
        if not open_pos:
            continue
        card["book"] = "open"
        card["side"] = str(open_pos.get("action") or "").upper()
        entry = open_pos.get("entry") or open_pos.get("signal_px")
        if isinstance(entry, (int, float)):
            card["entry"] = float(entry)

    cards.sort(
        key=lambda c: (
            0 if c.get("feature_vec") else 1,
            0 if _key(c.get("symbol"), c.get("market")) in live else 1,
            0 if _key(c.get("symbol"), c.get("market")) in shadow_keys else 1,
            -abs(float((c.get("features") or {}).get("atr_burst") or 0.0)),
            -abs(float((c.get("features") or {}).get("ret_1") or 0.0)),
            str(c.get("symbol") or ""),
        )
    )
    return cards[:MAX_CARDS]


def format_ticker_cards(cards: list[dict[str, Any]], *, markets: str | None = None) -> str:
    if not cards:
        mode = markets or "both"
        return f"MARKET SNAPSHOT markets={mode}: (пусто — нет тикеров или свечей; нужен Live-тик)"
    tf1 = str(cards[0].get("tf1") or DEFAULT_TF1)
    tf2 = str(cards[0].get("tf2") or DEFAULT_TF2)
    if markets is None:
        books = {str(c.get("market") or "spot") for c in cards}
        if books <= {"fut"}:
            markets = "futures"
        elif books <= {"spot"}:
            markets = "spot"
        else:
            markets = "both"
    lines = [
        f"MARKET SNAPSHOT TF1={tf1} TF2={tf2} markets={markets} "
        "(оба ТФ принудительно; не решения MLP)",
    ]
    for card in cards:
        mk = card.get("market") or "spot"
        lines.append(f"  {card.get('symbol')} [{mk}]")
        for tag, view in (("TF1", card.get("view1")), ("TF2", card.get("view2"))):
            block = view if isinstance(view, dict) else {}
            iv = block.get("interval") or "?"
            head = f"    {tag} {iv} close={_num(block.get('close'))}"
            if block.get("bars"):
                head += f" bars={block['bars']}"
            lines.append(head)
            bits = _feat_bits(block.get("features"))
            if bits:
                lines.append("      " + " ".join(bits))
            elif not block.get("feature_vec"):
                lines.append("      нет фич (мало свечей)")
    live_lines = [
        f"  {c.get('symbol')} [{c.get('market')}] live {c.get('side') or '?'} @ {_num(c.get('entry'))}"
        for c in cards
        if c.get("book") == "open"
    ]
    if live_lines:
        lines.append("LIVE BOOK (не копировать; не второй live-вход)")
        lines.extend(live_lines)
    return "\n".join(lines)
