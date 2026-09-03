"""Market dashboard report: MLP paper + LLM shadow + portfolio agent + opens."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.live_paper import load_open_positions, load_shadow_positions
from eurika.ml.market_store import load_candles, normalize_market
from eurika.ml.paper_orders import load_pending_orders
from eurika.ml.paper_trader import fee_for_market, label_trade


def _md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _fmt_px(val: object) -> str:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "—"
    if x >= 100:
        return f"{x:.2f}"
    if x >= 1:
        return f"{x:.4f}"
    return f"{x:.6f}"


def _fmt_pct(val: object) -> str:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    return f"{x * 100:.2f}%"


def _fmt_usd(val: object) -> str:
    try:
        x = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    return f"{x:+.2f}"


def _last_close(project_root: Path, symbol: str, market: str) -> float | None:
    for interval in ("1m", "15m", "1h"):
        bars = load_candles(project_root, symbol, interval, market=market)
        if not bars:
            continue
        try:
            px = float(bars[-1].get("close") or 0.0)
        except (TypeError, ValueError):
            continue
        if px > 0:
            return px
    return None


def _unrealized(pos: Mapping[str, Any], *, mark: float | None) -> dict[str, float | None]:
    if mark is None or mark <= 0:
        return {"edge": None, "pnl_usdt": None}
    entry = float(pos.get("entry") or 0.0)
    action = str(pos.get("action") or "").upper()
    if entry <= 0 or action not in {"BUY", "SELL"}:
        return {"edge": None, "pnl_usdt": None}
    market = normalize_market(pos.get("market"))
    lab = label_trade(entry, mark, action, fee=fee_for_market(market))
    edge = float(lab.get("edge") or 0.0)
    notion = float(pos.get("notional_usdt") or 0.0)
    margin = float(pos.get("margin_usdt") or 0.0)
    pnl = edge * notion if notion > 0 else None
    if pnl is not None and pnl < 0 and margin > 0:
        pnl = max(pnl, -margin)
    return {"edge": edge, "pnl_usdt": pnl}


def _open_rows(
    project_root: Path,
    positions: Sequence[Mapping[str, Any]],
    *,
    limit: int = 24,
) -> list[list[object]]:
    rows: list[list[object]] = []
    for pos in list(positions)[:limit]:
        symbol = str(pos.get("symbol") or "").upper()
        market = normalize_market(pos.get("market"))
        mark = _last_close(project_root, symbol, market)
        unr = _unrealized(pos, mark=mark)
        rows.append(
            [
                symbol,
                "fut" if market == "futures" else "spot",
                str(pos.get("action") or "").upper(),
                _fmt_px(pos.get("entry")),
                _fmt_px(mark),
                _fmt_pct(pos.get("tp_pct")),
                _fmt_pct(pos.get("sl_pct")),
                pos.get("entry_style") or "market",
                _fmt_usd(unr.get("pnl_usdt")) if unr.get("pnl_usdt") is not None else "—",
            ]
        )
    return rows


def _pending_rows(
    orders: Sequence[Mapping[str, Any]],
    *,
    limit: int = 24,
    live_only: bool | None = None,
) -> list[list[object]]:
    rows: list[list[object]] = []
    for order in orders:
        if str(order.get("status") or "pending") != "pending":
            continue
        is_shadow = bool(order.get("shadow"))
        if live_only is True and is_shadow:
            continue
        if live_only is False and not is_shadow:
            continue
        market = normalize_market(order.get("market"))
        rows.append(
            [
                str(order.get("symbol") or "").upper(),
                "fut" if market == "futures" else "spot",
                str(order.get("action") or "").upper(),
                order.get("entry_style") or "—",
                _fmt_px(order.get("limit_px")),
                _fmt_px(order.get("stop_px")),
                _fmt_pct(order.get("tp_pct")),
                _fmt_pct(order.get("sl_pct")),
            ]
        )
        if len(rows) >= limit:
            break
    return rows


def _earn_rows(positions: Sequence[Mapping[str, Any]], *, limit: int = 24) -> list[list[object]]:
    rows: list[list[object]] = []
    for pos in list(positions)[:limit]:
        try:
            amt = float(pos.get("amount") or pos.get("amount_usdt") or pos.get("principal_usdt") or 0.0)
            amt_s = f"{amt:.2f}"
        except (TypeError, ValueError):
            amt_s = "—"
        rows.append(
            [
                str(pos.get("asset") or pos.get("symbol") or "").upper(),
                str(pos.get("kind") or pos.get("earn_type") or pos.get("type") or "—"),
                amt_s,
                _fmt_pct(pos.get("apr") or pos.get("apy")),
            ]
        )
    return rows


def format_now_books_block(project_root: str | Path = ".") -> str:
    """Open/pending tables for MLP paper, portfolio agent, and LLM shadow."""
    root = Path(project_root).resolve()
    from eurika.ml.assistant_paper import load_opens as load_assistant_opens
    from eurika.ml.assistant_paper import load_pending as load_assistant_pending
    from eurika.ml.earn_monitor import load_earn_positions
    from eurika.ml.llm_shadow import load_shadow_opens
    from eurika.ml.llm_shadow_orders import load_shadow_pending

    mlp_opens = [p for p in load_open_positions(root) if not p.get("shadow")]
    mlp_shadow_opens = load_shadow_positions(root)
    mlp_pending = load_pending_orders(root)
    port_opens = load_assistant_opens(root)
    port_pending = load_assistant_pending(root)
    earn_pos = load_earn_positions(root)
    llm_opens = load_shadow_opens(root)
    llm_pending = load_shadow_pending(root)

    lines = [
        "## Сейчас (opens / pending)",
        "",
        "Нереализованный PnL — оценка по последней 1m/15m close и round-trip fee; не исполнение.",
        "",
        "### MLP paper opens",
    ]
    open_rows = _open_rows(root, mlp_opens)
    if open_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "entry", "mark", "TP", "SL", "style", "uPnL $"],
                open_rows,
            )
        )
    else:
        lines.append("_нет открытых live-позиций_")

    lines.extend(["", "### MLP pending (live)"])
    pend_rows = _pending_rows(mlp_pending, live_only=True)
    if pend_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "style", "limit", "stop", "TP", "SL"],
                pend_rows,
            )
        )
    else:
        lines.append("_нет live pending_")

    lines.extend(["", "### Portfolio agent trade opens"])
    port_open_rows = _open_rows(root, port_opens)
    if port_open_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "entry", "mark", "TP", "SL", "style", "uPnL $"],
                port_open_rows,
            )
        )
    else:
        lines.append("_нет portfolio trade opens_")

    lines.extend(["", "### Portfolio agent pending"])
    port_pend_rows = _pending_rows(port_pending)
    if port_pend_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "style", "limit", "stop", "TP", "SL"],
                port_pend_rows,
            )
        )
    else:
        lines.append("_нет portfolio pending_")

    lines.extend(["", "### Portfolio earn (paper)"])
    earn_rows = _earn_rows(earn_pos)
    if earn_rows:
        lines.append(_md_table(["asset", "type", "amount $", "APR"], earn_rows))
    else:
        lines.append("_нет earn positions_")

    if mlp_shadow_opens:
        lines.extend(
            [
                "",
                "### MLP explore/gate shadow opens",
                _md_table(
                    ["тикер", "книга", "side", "entry", "mark", "TP", "SL", "style", "uPnL $"],
                    _open_rows(root, mlp_shadow_opens),
                ),
            ]
        )

    lines.extend(["", "### LLM shadow opens"])
    llm_open_rows = _open_rows(root, llm_opens)
    if llm_open_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "entry", "mark", "TP", "SL", "style", "uPnL $"],
                llm_open_rows,
            )
        )
    else:
        lines.append("_нет открытых LLM shadow_")

    lines.extend(["", "### LLM shadow pending"])
    llm_pend_rows = _pending_rows(llm_pending)
    if llm_pend_rows:
        lines.append(
            _md_table(
                ["тикер", "книга", "side", "style", "limit", "stop", "TP", "SL"],
                llm_pend_rows,
            )
        )
    else:
        lines.append("_нет LLM pending_")

    return "\n".join(lines)


def format_market_dashboard_report(project_root: str | Path = ".") -> str:
    """One Market-tab report: now-books + portfolio agent + MLP + LLM shadow."""
    root = Path(project_root).resolve()
    from eurika.ml.learning_status import format_market_learning_report
    from eurika.ml.llm_teacher_stats import format_llm_shadow_report
    from eurika.ml.portfolio_agent import format_portfolio_status

    now = format_now_books_block(root)
    try:
        portfolio = format_portfolio_status(root)
    except Exception as exc:
        portfolio = f"# Portfolio agent — статус\n_ошибка: {exc}_"
    mlp = format_market_learning_report(project_root=root)
    shadow = format_llm_shadow_report(root)
    return "\n\n".join(
        [
            "# Market отчёт",
            now,
            portfolio,
            mlp,
            shadow,
        ]
    )
