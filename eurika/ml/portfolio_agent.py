"""Holistic portfolio agent: monitor market + earn + trade; Eurika learns via teacher.

Each cycle the LLM reads the full universe snapshot, both paper books (trade+earn),
writes prose + ``portfolio_actions`` + ``samples`` for teacher harvest.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from eurika.ml.assistant_paper import (
    SYNC_1M_LIMIT,
    _ts_iso,
    append_journal,
    apply_assistant_actions,
    ensure_portfolio,
    load_journal_tail,
    load_memory,
    run_book_tick,
    save_memory,
    sync_assistant_symbols,
)
from eurika.ml.earn_monitor import (
    accrue_earn_yield,
    apply_earn_actions,
    ensure_earn_portfolio,
    fetch_earn_rates,
    load_earn_rates,
)
from eurika.ml.llm_shadow import _try_obj
from eurika.ml.market_store import ml_root
from eurika.ml.portfolio_snapshot import (
    build_portfolio_market_snapshot,
    ensure_portfolio_candles,
    expand_portfolio_universe,
    format_portfolio_books,
    format_universe_overview,
)

ChatFn = Callable[[str], tuple[str | None, str | None]]
MAX_TEXT_CHARS = 14_000
INTERVAL_MS = 15 * 60 * 1000


def stamp_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "portfolio_agent_stamp.json"


def load_stamp(project_root: str | Path) -> dict[str, Any]:
    path = stamp_path(project_root)
    if not path.is_file():
        return {}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_stamp(project_root: str | Path, blob: dict[str, Any]) -> Path:
    import json

    path = stamp_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(blob)
    payload["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def is_due(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    interval_ms: int = INTERVAL_MS,
) -> bool:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    last = load_stamp(project_root).get("last_ms")
    try:
        last_ms = int(last) if last is not None else 0
    except (TypeError, ValueError):
        last_ms = 0
    if last_ms <= 0:
        return True
    return now - last_ms >= max(60_000, int(interval_ms))


def format_portfolio_status(project_root: str | Path) -> str:
    """Short status for Chat / Market (no LLM call)."""
    root = Path(project_root).resolve()
    lines = [
        "# Portfolio agent — статус",
        format_portfolio_digest(root),
        "",
        format_universe_overview(root),
    ]
    stamp = load_stamp(root)
    last = stamp.get("last_ms")
    if last:
        try:
            lines.append(f"last_cycle: {stamp.get('saved_at') or int(last)}")
        except (TypeError, ValueError):
            pass
    else:
        lines.append("last_cycle: ещё не было")
    lines.append(
        "\nЗапуск: Market → «Portfolio агент» / кнопка «Цикл», "
        "чат «запусти portfolio цикл», или CLI "
        "`python -m eurika.ml.assistant_paper portfolio-once`."
    )
    return "\n".join(lines)


def _pct(a: float, b: float) -> float | None:
    if a <= 0 or b <= 0:
        return None
    return (a / b - 1.0) * 100.0


def _last_mark(root: Path, symbol: str, market: str) -> float | None:
    from eurika.ml.market_store import load_candles, normalize_market

    sym = str(symbol or "").upper()
    mk = normalize_market(market)
    for iv in ("1m", "15m", "1h"):
        bars = load_candles(root, sym, iv, market=mk)
        if not bars:
            continue
        try:
            px = float(bars[-1].get("close") or 0.0)
        except (TypeError, ValueError):
            continue
        if px > 0:
            return px
    return None


def _fmt_money(v: float | None, *, signed: bool = False) -> str:
    if v is None:
        return "—"
    if signed:
        return f"{float(v):+.2f}$"
    return f"{float(v):.2f}$"


def _fmt_pct_pts(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{float(v):+.2f}%"


def _open_line(root: Path, pos: Mapping[str, Any]) -> str:
    from eurika.ml.market_store import normalize_market
    from eurika.ml.paper_trader import fee_for_market, label_trade

    sym = str(pos.get("symbol") or "").upper()
    side = str(pos.get("action") or "").upper()
    entry = float(pos.get("entry") or 0.0)
    market = normalize_market(pos.get("market"))
    mark = _last_mark(root, sym, market)
    margin = float(pos.get("margin_usdt") or 0.0)
    notion = float(pos.get("notional_usdt") or 0.0)
    tp = float(pos.get("tp_pct") or 0.0)
    sl = float(pos.get("sl_pct") or 0.0)
    bits = [f"{sym} {side}", f"вход {entry:.6g}" if entry > 0 else "вход —"]
    if mark is not None:
        bits.append(f"сейчас {mark:.6g}")
        if entry > 0 and side in {"BUY", "SELL"}:
            lab = label_trade(entry, mark, side, fee=fee_for_market(market))
            edge = float(lab.get("edge") or 0.0)
            pnl = edge * notion if notion > 0 else None
            if pnl is not None and pnl < 0 and margin > 0:
                pnl = max(pnl, -margin)
            bits.append(f"uPnL {_fmt_money(pnl, signed=True)} ({_fmt_pct_pts(edge * 100.0)})")
            if side == "BUY":
                if tp > 0:
                    tp_px = entry * (1.0 + tp)
                    bits.append(f"до TP {_fmt_pct_pts((tp_px / mark - 1.0) * 100.0 if mark > 0 else None)}")
                if sl > 0:
                    sl_px = entry * (1.0 - sl)
                    bits.append(f"запас до SL {_fmt_pct_pts((mark / sl_px - 1.0) * 100.0 if sl_px > 0 else None)}")
            else:
                if tp > 0:
                    tp_px = entry * (1.0 - tp)
                    bits.append(f"до TP {_fmt_pct_pts((mark / tp_px - 1.0) * 100.0 if tp_px > 0 else None)}")
                if sl > 0:
                    sl_px = entry * (1.0 + sl)
                    bits.append(f"запас до SL {_fmt_pct_pts((sl_px / mark - 1.0) * 100.0 if mark > 0 else None)}")
    else:
        bits.append("цена н/д")
    if margin > 0:
        bits.append(f"маржа {_fmt_money(margin)}")
    return " · ".join(bits)


def _pending_line(root: Path, order: Mapping[str, Any]) -> str:
    from eurika.ml.market_store import normalize_market

    sym = str(order.get("symbol") or "").upper()
    side = str(order.get("action") or "").upper()
    style = str(order.get("entry_style") or "limit")
    market = normalize_market(order.get("market"))
    mark = _last_mark(root, sym, market)
    limit_px = order.get("limit_px")
    stop_px = order.get("stop_px")
    inv = order.get("invalidate_px")
    margin = float(order.get("margin_usdt") or 0.0)
    try:
        limit_f = float(limit_px) if limit_px is not None else None
    except (TypeError, ValueError):
        limit_f = None
    try:
        stop_f = float(stop_px) if stop_px is not None else None
    except (TypeError, ValueError):
        stop_f = None
    try:
        inv_f = float(inv) if inv is not None else None
    except (TypeError, ValueError):
        inv_f = None

    bits = [f"{sym} {side} {style}"]
    if limit_f and limit_f > 0:
        bits.append(f"лимит {limit_f:.6g}")
    if stop_f and stop_f > 0:
        bits.append(f"стоп {stop_f:.6g}")
    if mark is not None:
        bits.append(f"сейчас {mark:.6g}")
        target = limit_f if style == "limit" and limit_f else stop_f
        if target and target > 0:
            if side == "BUY" and style == "limit":
                # need price to drop to limit
                dist = (mark / target - 1.0) * 100.0
                bits.append(f"до входа ещё −{abs(dist):.2f}%" if dist > 0 else f"в зоне входа ({dist:+.2f}%)")
            elif side == "SELL" and style == "limit":
                dist = (target / mark - 1.0) * 100.0
                bits.append(f"до входа ещё −{abs(dist):.2f}%" if dist > 0 else f"в зоне входа ({dist:+.2f}%)")
            elif style == "stop" and side == "BUY":
                dist = (target / mark - 1.0) * 100.0
                bits.append(f"до триггера {_fmt_pct_pts(dist)}")
            elif style == "stop" and side == "SELL":
                dist = (mark / target - 1.0) * 100.0
                bits.append(f"до триггера {_fmt_pct_pts(dist)}")
    if inv_f and inv_f > 0:
        bits.append(f"отмена @{inv_f:.6g}")
        if mark is not None and mark > 0:
            if side == "BUY":
                # BUY: cancel when price dumps to inv (low <= inv)
                dist = (mark / inv_f - 1.0) * 100.0
                bits.append(
                    "уже у уровня отмены" if dist <= 0 else f"до отмены вниз {_fmt_pct_pts(dist)}"
                )
            else:
                dist = (inv_f / mark - 1.0) * 100.0
                bits.append(
                    "уже у уровня отмены" if dist <= 0 else f"до отмены вверх {_fmt_pct_pts(dist)}"
                )
        # Dead pending: BUY limit can never fill if invalidate sits above limit
        if (
            side == "BUY"
            and style == "limit"
            and limit_f
            and inv_f >= limit_f
        ):
            bits.append("⚠ inv≥лимит — снимут до входа")
        if (
            side == "SELL"
            and style == "limit"
            and limit_f
            and inv_f <= limit_f
        ):
            bits.append("⚠ inv≤лимит — снимут до входа")
    if margin > 0:
        bits.append(f"маржа {_fmt_money(margin)}")
    return " · ".join(bits)


def format_portfolio_digest(
    project_root: str | Path,
    *,
    cycle: Mapping[str, Any] | None = None,
) -> str:
    """Human-readable bank + book snapshot for Market feed / Chat."""
    from eurika.ml.assistant_paper import load_opens, load_pending
    from eurika.ml.holistic_portfolio import reconcile_holistic, total_equity

    root = Path(project_root).resolve()
    h = reconcile_holistic(root)
    opens = load_opens(root)
    pending = load_pending(root)
    eq = float(h.get("equity_usdt") or total_equity(h) or 0.0)
    start = float(h.get("start_equity_usdt") or eq)
    cash = float(h.get("cash_free_usdt") or 0.0)
    margin = float(h.get("trade_margin_usdt") or 0.0)
    realized = float(h.get("trade_realized_pnl_usdt") or 0.0)

    # Aggregate unrealized from opens
    u_sum = 0.0
    u_n = 0
    open_lines: list[str] = []
    for pos in opens:
        open_lines.append("  • " + _open_line(root, pos))
        # parse pnl from mark again lightly
        from eurika.ml.market_store import normalize_market
        from eurika.ml.paper_trader import fee_for_market, label_trade

        mark = _last_mark(root, str(pos.get("symbol") or ""), normalize_market(pos.get("market")))
        entry = float(pos.get("entry") or 0.0)
        side = str(pos.get("action") or "").upper()
        notion = float(pos.get("notional_usdt") or 0.0)
        mgn = float(pos.get("margin_usdt") or 0.0)
        if mark and entry > 0 and side in {"BUY", "SELL"} and notion > 0:
            edge = float(label_trade(entry, mark, side, fee=fee_for_market(normalize_market(pos.get("market")))).get("edge") or 0.0)
            pnl = edge * notion
            if pnl < 0 and mgn > 0:
                pnl = max(pnl, -mgn)
            u_sum += pnl
            u_n += 1

    pend_lines = ["  • " + _pending_line(root, o) for o in pending]

    ok = True if cycle is None else bool(cycle.get("ok"))
    title = "Portfolio агент — цикл OK" if ok else "Portfolio агент — цикл с ошибкой"
    if cycle is None:
        title = "Portfolio агент — статус"

    lines = [
        title,
        (
            f"Банк: equity {_fmt_money(eq)} (Δ {_fmt_money(eq - start, signed=True)} от старта) · "
            f"cash {_fmt_money(cash)} · маржа {_fmt_money(margin)} · "
            f"realized {_fmt_money(realized, signed=True)}"
            + (f" · uPnL {_fmt_money(u_sum, signed=True)}" if u_n else " · uPnL 0.00$ (нет opens)")
        ),
        f"Позиции: открыто {len(opens)} · pending {len(pending)}",
    ]
    if open_lines:
        lines.append("Открыто:")
        lines.extend(open_lines)
    else:
        lines.append("Открыто: нет")
    if pend_lines:
        lines.append("Pending:")
        lines.extend(pend_lines)
    else:
        lines.append("Pending: нет")

    if cycle is not None:
        raw_trade = cycle.get("trade")
        raw_earn = cycle.get("earn")
        trade: dict[str, Any] = raw_trade if isinstance(raw_trade, dict) else {}
        earn: dict[str, Any] = raw_earn if isinstance(raw_earn, dict) else {}
        lines.append(
            "За цикл: "
            f"place={int(trade.get('place') or 0)} "
            f"open={int(trade.get('open') or 0)} "
            f"close={int(trade.get('close') or 0)} "
            f"cancel={int(trade.get('cancel') or 0)} "
            f"hold={int(trade.get('hold') or 0)} "
            f"blocked={int(trade.get('blocked') or 0)}"
            + (
                f" · earn dep={int(earn.get('deposit') or 0)} red={int(earn.get('redeem') or 0)}"
                if not PORTFOLIO_FUTURES_ONLY
                else ""
            )
            + f" · actions={int(cycle.get('actions_n') or 0)}"
        )
        notes = cycle.get("block_notes") if isinstance(cycle.get("block_notes"), list) else []
        if notes:
            lines.append("Blocked: " + "; ".join(str(x) for x in notes[:6]))
        body = str(cycle.get("body") or "").strip()
        verdict = ""
        for key in ("**Вердикт:**", "Вердикт:"):
            idx = body.find(key)
            if idx >= 0:
                # keep multi-line verdict until blank line / next section / JSON
                chunk = body[idx + len(key) :].strip()
                parts: list[str] = []
                for ln in chunk.split("\n"):
                    s = ln.strip()
                    if not s or s.startswith("{") or s.startswith("```") or s.startswith("---"):
                        break
                    if s.startswith("#") or s.startswith("###"):
                        break
                    parts.append(s)
                    if sum(len(p) for p in parts) >= 900:
                        break
                verdict = " ".join(parts).strip()
                break
        if not verdict and body:
            for ln in body.split("\n"):
                s = ln.strip().lstrip("#").strip()
                if s and not s.startswith("Цикл ") and "range_break" not in s.lower():
                    verdict = s
                    break
        if verdict:
            verdict = verdict.replace("**", "")
            if len(verdict) > 900:
                verdict = verdict[:899].rstrip() + "…"
            lines.append(f"Вердикт: {verdict}")
        err = cycle.get("error")
        if err:
            lines.append(f"Ошибка: {err}")
    return "\n".join(lines)


# Temporary ops mode: futures paper only (earn/spot deposits disabled).
PORTFOLIO_FUTURES_ONLY = True

PORTFOLIO_AGENT_RULES = (
    "Ты агент holistic portfolio Eurika: paper futures — ищешь, где заработать на фьючерсах.\n"
    "Paper-only: без live-ордеров. **Единый банк ~1000 USDT** (HOLISTIC CASH POOL) = "
    "cash_free под trade margin. **Earn и spot сейчас ВЫКЛЮЧЕНЫ** — не deposit/redeem earn, "
    "не торгуй spot. MLP exam и shadow — не трогать.\n"
    "\n"
    "Каждый цикл:\n"
    "  1) FUTURES UNIVERSE — весь Binance USDT-M perpetual (24h overview), не узкий ticker_lists.\n"
    "  2) DETAIL SNAPSHOT — 15m+1h: сначала ASSISTANT BOOK (opens/pending), затем топ movers.\n"
    "  3) BOOKS — cash_free / margin / opens / pending / REENTRY GUARDS.\n"
    "  4) MEMORY — прошлые циклы.\n"
    "Приоритет анализа: открытые и pending позиции; потом сильные движения по рынку.\n"
    "\n"
    "Проза — тезисы и память. JSON portfolio_actions — только TRADE:\n"
    "  product=trade, market=futures, action=open|place|update|cancel|close|hold,\n"
    "  symbol, side, уровни (limit_px / tp_pct / sl_pct). Idle cash держи в cash_free.\n"
    "  Для BUY limit: invalidate_px НИЖЕ limit (отмена при сносе вниз). "
    "Для SELL limit: invalidate_px ВЫШЕ limit. Иначе ордер неисполним.\n"
    "  R:R: цель TP≈3×SL (пример 2.4% / 0.8%); не ставь TP≤SL. Скелет поднимет TP, "
    "если ratio < 1.5. Не снимай крошечный плюс — structure/trail только после заметного MFE.\n"
    "  После SL скелет блокирует тот же symbol+side ~2ч — не «восстанавливай» тот же лимит; "
    "выбери другую идею или hold/wait. Один и тот же limit_px — не чаще 2 place за 4ч "
    "(скелет отклонит лишнее).\n"
    "\n"
    "Для обучения Eurika добавь samples (как LLM 15м teacher) по fut из снимка:\n"
    '  enter=yes|no|wait, side=BUY|SELL|HOLD, tp_pct/sl_pct доли.\n'
    "В конце вердикт 2–4 строки, затем ОДИН JSON:\n"
    '{"samples":[{"symbol":"BTCUSDT","market":"fut","enter":"wait","side":"HOLD"}],'
    '"portfolio_actions":[{"product":"trade","symbol":"ETHUSDT","market":"futures",'
    '"action":"place","side":"BUY","entry_style":"limit","limit_px":3500,'
    '"tp_pct":0.024,"sl_pct":0.008}]}\n'
)


def _json_root_start(raw: str) -> int | None:
    for key in ("portfolio_actions", "assistant_actions", "samples"):
        m = re.search(rf"\{{[\s\n]*\"{key}\"", raw)
        if m:
            return m.start()
    return None


def parse_portfolio_actions(text: str) -> list[dict[str, Any]]:
    raw = text or ""
    blobs: list[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fence:
        blobs.append(fence.group(1))
    start = _json_root_start(raw)
    if start is not None:
        blobs.append(raw[start:])
    blobs.append(raw)
    for blob in blobs:
        data = _try_obj(blob)
        if not data:
            continue
        for field in ("portfolio_actions", "assistant_actions"):
            rows = data.get(field)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    return []


def portfolio_journal_body(text: str) -> str:
    body = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", text or "", flags=re.S)
    for key in ('"portfolio_actions"', '"assistant_actions"', '"samples"'):
        idx = body.rfind(key.strip('"'))
        if idx >= 0:
            start = body.rfind("{", 0, idx + 1)
            if start >= 0:
                body = body[:start]
    body = body.strip()
    if len(body) > MAX_TEXT_CHARS:
        body = body[: MAX_TEXT_CHARS - 1] + "…"
    return body or "пустой ответ"


def _split_actions(actions: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    earn_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    for raw in actions:
        product = str(raw.get("product") or "").strip().lower()
        if product == "earn":
            if not PORTFOLIO_FUTURES_ONLY:
                earn_rows.append(dict(raw))
            continue
        if product in {"trade", "spot", "fut", "futures"} or raw.get("symbol"):
            row = dict(raw)
            if product in {"spot", "fut", "futures"} and "market" not in row:
                row["market"] = "futures" if product in {"fut", "futures"} else "spot"
            if PORTFOLIO_FUTURES_ONLY:
                market = str(row.get("market") or "futures").strip().lower()
                if market in {"spot", "sp"}:
                    continue
                row["market"] = "futures"
                row["product"] = "trade"
            trade_rows.append(row)
    return earn_rows, trade_rows


def apply_portfolio_actions(
    root: str | Path,
    actions: Sequence[Mapping[str, Any]],
    *,
    rates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    earn_rows, trade_rows = _split_actions(actions)
    earn_out = apply_earn_actions(root, earn_rows, rates=rates) if earn_rows else {"applied": {}}
    trade_out = apply_assistant_actions(root, trade_rows) if trade_rows else {"applied": {}}
    earn_ap = earn_out.get("applied") if isinstance(earn_out.get("applied"), dict) else {}
    trade_ap = trade_out.get("applied") if isinstance(trade_out.get("applied"), dict) else {}
    return {
        "earn": earn_ap,
        "trade": trade_ap,
        "earn_equity_usdt": earn_out.get("equity_usdt"),
        "closed_rows": trade_out.get("closed_rows") or [],
        "block_notes": trade_out.get("block_notes") or [],
    }


def format_memory_block(root: str | Path, *, limit: int = 4) -> str:
    memory = load_memory(root)
    lines = ["MEMORY (прошлые portfolio-циклы)"]
    summary = str(memory.get("last_summary") or "").strip()
    lines.append(f"last_summary: {summary[:2000]}" if summary else "last_summary: (нет)")
    tail = load_journal_tail(root, limit=limit, kind="portfolio_cycle")
    if not tail:
        tail = load_journal_tail(root, limit=limit, kind="agent_cycle")
    if tail:
        lines.append("journal_tail:")
        for row in tail:
            lines.append(f"  [{row.get('ts_iso')}] {str(row.get('text') or '')[:1000]}")
    else:
        lines.append("journal_tail: (пусто)")
    return "\n".join(lines)


def build_portfolio_prompt(root: str | Path, *, now_ms: int | None = None) -> str:
    root = Path(root).resolve()
    now = int(now_ms or time.time() * 1000)
    rates = None if PORTFOLIO_FUTURES_ONLY else load_earn_rates(root)
    _cards, market_text = build_portfolio_market_snapshot(root)
    blocks = [
        PORTFOLIO_AGENT_RULES,
        f"TIME {_ts_iso(now)}",
        format_universe_overview(root),
        market_text,
        format_portfolio_books(root, rates=rates),
    ]
    if PORTFOLIO_FUTURES_ONLY:
        blocks.append(
            "MODE: FUTURES ONLY — ignore EARN RATES / earn positions; do not emit product=earn."
        )
    blocks.append(format_memory_block(root))
    return "\n\n".join(blocks)


def _default_chat(prompt: str) -> tuple[str | None, str | None]:
    from eurika.agent.cursor_judge import complete_chat

    return complete_chat(
        prompt,
        lease_priority="market",
        lease_purpose="portfolio_agent",
    )


def _harvest_learning(
    root: Path,
    full: str,
    cards: Sequence[dict[str, Any]],
    *,
    now_ms: int,
) -> dict[str, Any]:
    from eurika.ml.llm_teacher import harvest_teacher

    try:
        return harvest_teacher(root, full, cards, now_ms=now_ms)
    except Exception as exc:
        return {"parsed": 0, "stored": 0, "skipped": 0, "error": f"{type(exc).__name__}: {exc}"}


def run_portfolio_cycle(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    complete_chat: ChatFn | None = None,
    fetch_rates: bool = True,
) -> dict[str, Any]:
    """Holistic cycle: accrue earn → book tick → rates → LLM → apply → book tick → teacher → journal."""
    root = Path(project_root).resolve()
    now = int(now_ms or time.time() * 1000)
    from eurika.ml.holistic_portfolio import ensure_holistic, reconcile_holistic

    ensure_holistic(root)
    ensure_portfolio(root)
    ensure_earn_portfolio(root)
    expand_portfolio_universe(root)

    accrue = accrue_earn_yield(root, now_ms=now)
    pre = run_book_tick(root, now_ms=now, auto_place=False, write_journal=False)

    rates: dict[str, Any] = load_earn_rates(root)
    if fetch_rates:
        try:
            rates = fetch_earn_rates(root)
        except Exception:
            pass
    ensure_portfolio_candles(root, limit_1m=SYNC_1M_LIMIT)
    from eurika.ml.portfolio_snapshot import collect_portfolio_pairs

    sym_set = {s for s, _ in collect_portfolio_pairs(root)}
    sync_assistant_symbols(root, sorted(sym_set), limit_1m=SYNC_1M_LIMIT)

    cards, _ = build_portfolio_market_snapshot(root)
    prompt = build_portfolio_prompt(root, now_ms=now)
    chat = complete_chat or _default_chat
    text, err = chat(prompt)
    ok = bool(text) and not err
    full = (text or err or "пустой ответ").strip()
    body = portfolio_journal_body(full)
    actions = parse_portfolio_actions(full) if ok else []
    managed: dict[str, Any] = {"earn": {}, "trade": {}}
    if ok and actions:
        managed = apply_portfolio_actions(root, actions, rates=rates)

    post = run_book_tick(root, now_ms=now, auto_place=False, write_journal=False)
    teacher = _harvest_learning(root, full, cards, now_ms=now) if ok else {"stored": 0}

    raw_earn_ap = managed.get("earn")
    raw_trade_ap = managed.get("trade")
    earn_ap: dict[str, Any] = raw_earn_ap if isinstance(raw_earn_ap, dict) else {}
    trade_ap: dict[str, Any] = raw_trade_ap if isinstance(raw_trade_ap, dict) else {}
    block_notes = managed.get("block_notes") if isinstance(managed.get("block_notes"), list) else []
    extra = (
        f" [earn dep={int(earn_ap.get('deposit') or 0)}"
        f" red={int(earn_ap.get('redeem') or 0)}"
        f" | trade place={int(trade_ap.get('place') or 0)}"
        f" open={int(trade_ap.get('open') or 0)}"
        f" close={int(trade_ap.get('close') or 0)}"
        f" blocked={int(trade_ap.get('blocked') or 0)}"
        f" | teacher={int(teacher.get('stored') or 0)}"
        f" accrue={float(accrue.get('accrued_usdt') or 0):.4f}]"
    )
    if block_notes:
        extra += "\nblocked: " + "; ".join(str(x) for x in block_notes[:8])
    message = (
        f"=== PORTFOLIO CYCLE {_ts_iso(now)} ===\n"
        f"{body}\n"
        f"{extra}\n"
        f"\n--- pre-tick ---\n"
        + "\n".join(pre.get("logs") or [])
        + "\n\n--- post-tick ---\n"
        + "\n".join(post.get("logs") or [])
    )
    memory = load_memory(root)
    memory["last_summary"] = body[:4000]
    memory["cycle_count"] = int(memory.get("cycle_count") or 0) + 1
    memory["last_actions_n"] = len(actions)
    memory["last_teacher_stored"] = int(teacher.get("stored") or 0)
    save_memory(root, memory)

    h = reconcile_holistic(root)
    save_stamp(root, {"last_ms": now, "ok": ok, "actions_n": len(actions)})


    append_journal(
        root,
        kind="portfolio_cycle",
        text=message,
        extra={
            "ok": ok,
            "holistic_equity_usdt": h.get("equity_usdt"),
            "cash_free_usdt": h.get("cash_free_usdt"),
            "trade_equity_usdt": post.get("equity_usdt"),
            "earn_equity_usdt": managed.get("earn_equity_usdt"),
            "opens": post.get("opens"),
            "pending": post.get("pending"),
            "actions_n": len(actions),
            "teacher_stored": int(teacher.get("stored") or 0),
            "earn_applied": earn_ap,
            "trade_applied": trade_ap,
        },
    )
    try:
        from eurika.ml.market_journal import append_market_journal

        digest = format_portfolio_digest(
            root,
            cycle={
                "ok": ok,
                "body": body,
                "error": err,
                "actions_n": len(actions),
                "trade": trade_ap,
                "earn": earn_ap,
                "block_notes": block_notes,
            },
        )
        append_market_journal(
            root,
            digest,
            kind="portfolio_agent",
            extras={
                "teacher_stored": int(teacher.get("stored") or 0),
                "equity_usdt": h.get("equity_usdt"),
            },
        )
    except Exception:
        digest = ""
    out = {
        "ok": ok,
        "error": err,
        "body": body,
        "digest": digest or format_portfolio_digest(
            root,
            cycle={
                "ok": ok,
                "body": body,
                "error": err,
                "actions_n": len(actions),
                "trade": trade_ap,
                "earn": earn_ap,
                "block_notes": block_notes,
            },
        ),
        "actions_n": len(actions),
        "earn": earn_ap,
        "trade": trade_ap,
        "block_notes": block_notes,
        "teacher": teacher,
        "holistic_equity_usdt": h.get("equity_usdt"),
        "trade_equity_usdt": post.get("equity_usdt"),
        "earn_equity_usdt": managed.get("earn_equity_usdt"),
        "accrue_usdt": accrue.get("accrued_usdt"),
    }
    return out


# Backwards-compatible alias for assistant_agent imports.
run_agent_cycle = run_portfolio_cycle
