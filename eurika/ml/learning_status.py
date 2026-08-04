"""Aggregate paper-market learning progress for CLI / Qt (no secrets)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from eurika.ml.live_paper import load_open_positions
from eurika.ml.market_model import model_status
from eurika.ml.market_store import market_status, ml_root, normalize_market
from eurika.ml.paper_portfolio import ensure_portfolio, portfolio_status
from eurika.ml.paper_trader import load_paper_trades, paper_status

# How many opens / candle series to print in the human block (count is always full).
_OPEN_LIST_LIMIT = 24
_SERIES_LIST_LIMIT = 16


def live_session_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "live_session.json"


def mark_live_session_start(project_root: str | Path) -> dict[str, Any]:
    """Stamp session start when Live paper is turned on (overwrites previous)."""
    root = Path(project_root).resolve()
    path = live_session_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    started_ms = int(time.time() * 1000)
    blob = {"started_ms": started_ms, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return blob


def load_live_session_started_ms(project_root: str | Path) -> int | None:
    path = live_session_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("started_ms")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _market_bucket(row: dict[str, Any]) -> str:
    return normalize_market(str(row.get("market") or "spot"))


def _row_edge(row: dict[str, Any]) -> float | None:
    e = row.get("edge")
    if isinstance(e, (int, float)):
        return float(e)
    return None


def _row_time_ms(row: dict[str, Any]) -> int | None:
    """Prefer exit time (label closed); fall back to entry ts."""
    for key in ("exit_ts", "ts"):
        raw = row.get(key)
        try:
            if raw is not None:
                return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _slice_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    correct = sum(1 for r in rows if r.get("correct"))
    edges = [_row_edge(r) for r in rows]
    edges_f = [e for e in edges if e is not None]
    sum_edge = sum(edges_f) if edges_f else 0.0
    pnls: list[float] = []
    for r in rows:
        raw = r.get("pnl_usdt")
        if isinstance(raw, (int, float)):
            pnls.append(float(raw))
    sum_pnl = sum(pnls) if pnls else 0.0
    return {
        "count": len(rows),
        "correct": correct,
        "accuracy": (correct / len(rows)) if rows else None,
        "buys": sum(1 for r in rows if str(r.get("action") or "").upper() == "BUY"),
        "sells": sum(1 for r in rows if str(r.get("action") or "").upper() == "SELL"),
        "sum_edge": sum_edge if edges_f else None,
        "mean_edge": (sum_edge / len(edges_f)) if edges_f else None,
        "edge_n": len(edges_f),
        "sum_pnl_usdt": sum_pnl if pnls else None,
        "pnl_n": len(pnls),
    }


def _fmt_edge(val: float | None) -> str:
    if not isinstance(val, float):
        return "n/a"
    return f"{val:+.3%}"


def market_learning_status(project_root: str | Path) -> dict[str, Any]:
    """Snapshot of paper learning progress under ``.eurika/ml/``."""
    root = Path(project_root).resolve()
    paper = paper_status(root)
    model = model_status(root)
    market = market_status(root)
    opens = load_open_positions(root)
    rows = load_paper_trades(root)
    live_rows = [r for r in rows if r.get("live")]
    live_spot = [r for r in live_rows if _market_bucket(r) == "spot"]
    live_fut = [r for r in live_rows if _market_bucket(r) == "futures"]
    open_spot = [p for p in opens if _market_bucket(p) == "spot"]
    open_fut = [p for p in opens if _market_bucket(p) == "futures"]
    live_correct = sum(1 for r in live_rows if r.get("correct"))

    all_stats = _slice_stats(rows)
    live_stats = _slice_stats(live_rows)
    live_spot_stats = _slice_stats(live_spot)
    live_fut_stats = _slice_stats(live_fut)

    session_started = load_live_session_started_ms(root)
    session_rows: list[dict[str, Any]] = []
    if session_started is not None:
        for r in live_rows:
            t = _row_time_ms(r)
            if t is not None and t >= session_started:
                session_rows.append(r)
    session_stats = _slice_stats(session_rows)

    try:
        ensure_portfolio(root)
        bank = portfolio_status(root)
    except Exception:
        bank = {}

    raw_meta = model.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    open_summary = []
    for p in opens:
        open_summary.append(
            {
                "symbol": p.get("symbol"),
                "market": _market_bucket(p),
                "action": p.get("action"),
                "entry": p.get("entry"),
                "horizon": p.get("horizon"),
                "source": p.get("source"),
                "notional_usdt": p.get("notional_usdt"),
                "margin_usdt": p.get("margin_usdt"),
                "leverage": p.get("leverage"),
            }
        )
    # Enrich paper dict with edge totals for callers that only read paper.
    paper = {
        **paper,
        "sum_edge": all_stats.get("sum_edge"),
        "mean_edge": all_stats.get("mean_edge"),
    }
    return {
        "project_root": str(root),
        "paper": paper,
        "live": {
            "count": len(live_rows),
            "correct": live_correct,
            "accuracy": (live_correct / len(live_rows)) if live_rows else None,
            "sum_edge": live_stats.get("sum_edge"),
            "mean_edge": live_stats.get("mean_edge"),
            "sum_pnl_usdt": live_stats.get("sum_pnl_usdt"),
            "spot": live_spot_stats,
            "futures": live_fut_stats,
        },
        "portfolio": bank,
        "pnl": {
            "all": {
                "sum_edge": all_stats.get("sum_edge"),
                "mean_edge": all_stats.get("mean_edge"),
                "n": all_stats.get("edge_n"),
                "sum_pnl_usdt": all_stats.get("sum_pnl_usdt"),
                "pnl_n": all_stats.get("pnl_n"),
            },
            "live": {
                "sum_edge": live_stats.get("sum_edge"),
                "mean_edge": live_stats.get("mean_edge"),
                "n": live_stats.get("edge_n"),
                "sum_pnl_usdt": live_stats.get("sum_pnl_usdt"),
                "pnl_n": live_stats.get("pnl_n"),
            },
            "live_spot": {
                "sum_edge": live_spot_stats.get("sum_edge"),
                "mean_edge": live_spot_stats.get("mean_edge"),
                "n": live_spot_stats.get("edge_n"),
                "sum_pnl_usdt": live_spot_stats.get("sum_pnl_usdt"),
            },
            "live_futures": {
                "sum_edge": live_fut_stats.get("sum_edge"),
                "mean_edge": live_fut_stats.get("mean_edge"),
                "n": live_fut_stats.get("edge_n"),
                "sum_pnl_usdt": live_fut_stats.get("sum_pnl_usdt"),
            },
            "session": {
                "sum_edge": session_stats.get("sum_edge"),
                "mean_edge": session_stats.get("mean_edge"),
                "n": session_stats.get("edge_n"),
                "started_ms": session_started,
                "count": session_stats.get("count"),
                "sum_pnl_usdt": session_stats.get("sum_pnl_usdt"),
                "pnl_n": session_stats.get("pnl_n"),
            },
        },
        "opens": {
            "count": len(opens),
            "spot": len(open_spot),
            "futures": len(open_fut),
            "positions": open_summary,
        },
        "model": {
            "weights_exist": bool(model.get("weights_exist")),
            "torch_available": bool(model.get("torch_available")),
            "train_accuracy": meta.get("train_accuracy"),
            "samples": meta.get("samples"),
            "device": meta.get("device"),
            "weights": model.get("weights"),
        },
        "market": market,
    }


def format_market_learning_block(
    st: dict[str, Any] | str | Path | None = None,
    project_root: str | Path = ".",
) -> str:
    """Human-readable progress block (Russian)."""
    if isinstance(st, (str, Path)):
        data = market_learning_status(st)
    elif st is not None:
        data = st
    else:
        data = market_learning_status(project_root)
    paper = data.get("paper") or {}
    live = data.get("live") or {}
    opens = data.get("opens") or {}
    model = data.get("model") or {}
    market = data.get("market") or {}
    pnl = data.get("pnl") or {}
    bank = data.get("portfolio") or {}
    acc = paper.get("accuracy")
    live_acc = live.get("accuracy")
    live_spot = live.get("spot") or {}
    live_fut = live.get("futures") or {}
    positions = list(opens.get("positions") or [])
    pnl_all = pnl.get("all") or {}
    pnl_live = pnl.get("live") or {}
    pnl_spot = pnl.get("live_spot") or {}
    pnl_fut = pnl.get("live_futures") or {}
    pnl_sess = pnl.get("session") or {}

    def _fmt_usd(val: object) -> str:
        if isinstance(val, (int, float)):
            return f"{float(val):+.2f}"
        return "n/a"

    lines = [
        "MARKET LEARNING (paper)",
        f"  сделки всего: {paper.get('count', 0)} (BUY={paper.get('buys', 0)} SELL={paper.get('sells', 0)})",
        f"  accuracy paper: {acc:.3f}" if isinstance(acc, float) else "  accuracy paper: n/a",
        (
            f"  банк: equity={float(bank.get('equity_usdt') or 0):.2f} USDT "
            f"(старт {float(bank.get('start_equity_usdt') or 0):.0f}, "
            f"Δ={_fmt_usd(bank.get('session_pnl_usdt'))}) · "
            f"маржа {float(bank.get('margin_used_usdt') or 0):.1f}/"
            f"{float(bank.get('max_margin_usdt') or 0):.1f}"
        ),
        (
            f"  PnL Σ edge: всего={_fmt_edge(pnl_all.get('sum_edge'))} "
            f"(n={pnl_all.get('n', 0)}) · live={_fmt_edge(pnl_live.get('sum_edge'))} "
            f"(n={pnl_live.get('n', 0)})"
        ),
        (
            f"  PnL USDT: live={_fmt_usd(pnl_live.get('sum_pnl_usdt'))} "
            f"(n={pnl_live.get('pnl_n', 0)}) · сессия={_fmt_usd(pnl_sess.get('sum_pnl_usdt'))}"
        ),
        (
            f"    live spot={_fmt_edge(pnl_spot.get('sum_edge'))} "
            f"fut={_fmt_edge(pnl_fut.get('sum_edge'))} · "
            f"сессия edge={_fmt_edge(pnl_sess.get('sum_edge'))} "
            f"(n={pnl_sess.get('n', 0)}; с вкл. Live)"
        ),
        f"  live-метки: {live.get('count', 0)}"
        + (f" (accuracy={live_acc:.3f})" if isinstance(live_acc, float) else ""),
        (
            f"    spot={live_spot.get('count', 0)}"
            + (
                f" (acc={live_spot['accuracy']:.3f})"
                if isinstance(live_spot.get("accuracy"), float)
                else ""
            )
            + f"  fut={live_fut.get('count', 0)}"
            + (
                f" (acc={live_fut['accuracy']:.3f})"
                if isinstance(live_fut.get("accuracy"), float)
                else ""
            )
        ),
        (
            f"  открыто paper: {opens.get('count', 0)} "
            f"(spot={opens.get('spot', 0)} fut={opens.get('futures', 0)})"
        ),
    ]
    shown = positions[:_OPEN_LIST_LIMIT]
    for p in shown:
        mk = p.get("market") or "spot"
        mk_s = "fut" if mk == "futures" else "spot"
        lines.append(
            f"    {p.get('symbol')} [{mk_s}] {p.get('action')} @ {p.get('entry')} "
            f"гор.={p.get('horizon')} ({p.get('source')})"
        )
    rest = len(positions) - len(shown)
    if rest > 0:
        lines.append(f"    … ещё {rest}")
    series = list(market.get("series") or [])
    if series:
        lines.append(f"  свечи: {len(series)} серий")
        for s in series[:_SERIES_LIST_LIMIT]:
            mk = s.get("market") or "spot"
            mk_s = "fut" if mk == "futures" else "spot"
            lines.append(f"    [{mk_s}] {s.get('symbol')} {s.get('interval')}: {s.get('count')}")
        more = len(series) - min(len(series), _SERIES_LIST_LIMIT)
        if more > 0:
            lines.append(f"    … ещё {more}")
    else:
        lines.append("  свечи: (пусто)")
    if model.get("weights_exist"):
        lines.append(
            f"  модель: samples={model.get('samples')} "
            f"train_acc={model.get('train_accuracy')} device={model.get('device')}"
        )
    else:
        lines.append("  модель: весов нет")
    lines.append("  note: без live-ордеров; Chat → Market для тиков; PnL = Σ edge (после fee)")
    return "\n".join(lines)


def _parse_analysis_advice(message: str) -> dict[str, Any] | None:
    """Extract symbol/market/action from a journal analysis line."""
    msg = (message or "").strip()
    if not msg.startswith("анализ:"):
        return None
    body = msg[len("анализ:") :].strip()
    parts = body.split()
    if not parts:
        return None
    symbol = parts[0]
    market = "futures" if len(parts) > 1 and parts[1] == "fut" else "spot"
    action = "HOLD"
    if "ПОКУП" in msg:
        action = "BUY"
    elif "ПРОДА" in msg:
        action = "SELL"
    soft = "мягк" in msg
    return {
        "symbol": symbol,
        "market": market,
        "action": action,
        "soft": soft,
        "message": msg,
    }


def format_market_situation_block(
    project_root: str | Path = ".",
    *,
    lookback_ms: int = 45 * 60 * 1000,
    journal_tail: int = 2500,
) -> str:
    """Live paper situation for Chat: bank, opens, recent model advice — not architecture."""
    root = Path(project_root).resolve()
    try:
        from eurika.ml.market_journal import load_market_journal
    except Exception:
        load_market_journal = None  # type: ignore[assignment]

    st = market_learning_status(root)
    bank = st.get("portfolio") or {}
    opens = st.get("opens") or {}
    positions = list(opens.get("positions") or [])
    model = st.get("model") or {}
    pnl_live = (st.get("pnl") or {}).get("live") or {}

    eq = bank.get("equity_usdt")
    start = bank.get("start_equity_usdt")
    dlt = bank.get("session_pnl_usdt")
    used = bank.get("margin_used_usdt")
    mx = bank.get("max_margin_usdt")

    lines: list[str] = ["MARKET СЕЙЧАС (paper, без ордеров на биржу)"]
    if isinstance(eq, (int, float)):
        lines.append(
            f"  банк: equity={float(eq):.2f} USDT "
            f"(старт {float(start or 0):.0f}, Δ={float(dlt or 0):+.2f}$) · "
            f"маржа {float(used or 0):.1f}/{float(mx or 0):.1f}"
        )
    else:
        lines.append("  банк: n/a (ещё нет paper_portfolio.json)")

    buy_n = sum(1 for p in positions if str(p.get("action") or "").upper() == "BUY")
    sell_n = sum(1 for p in positions if str(p.get("action") or "").upper() == "SELL")
    sized = sum(1 for p in positions if p.get("margin_usdt"))
    lines.append(
        f"  открыто: {opens.get('count', 0)} "
        f"(spot={opens.get('spot', 0)} fut={opens.get('futures', 0)}; "
        f"BUY={buy_n} SELL={sell_n}; sized={sized})"
    )
    for p in positions[:12]:
        mk = "fut" if (p.get("market") or "spot") == "futures" else "spot"
        lev = p.get("leverage")
        lev_s = f" ×{float(lev):.1f}" if isinstance(lev, (int, float)) and float(lev) != 1.0 else ""
        m = p.get("margin_usdt")
        m_s = f" m={float(m):.0f}" if isinstance(m, (int, float)) else " legacy"
        lines.append(
            f"    {p.get('symbol')} [{mk}] {p.get('action')}{lev_s}{m_s} ({p.get('source')})"
        )
    if len(positions) > 12:
        lines.append(f"    … ещё {len(positions) - 12}")

    # Recent model advice from journal
    advice: dict[tuple[str, str], dict[str, Any]] = {}
    last_ts = 0
    if load_market_journal is not None:
        try:
            rows = load_market_journal(root, limit=journal_tail)
        except Exception:
            rows = []
        if rows:
            last_ts = int(rows[-1].get("ts") or 0)
        cutoff = last_ts - max(60_000, int(lookback_ms)) if last_ts else 0
        for r in rows:
            if (r.get("kind") or "") != "analysis":
                continue
            if cutoff and int(r.get("ts") or 0) < cutoff:
                continue
            parsed = _parse_analysis_advice(str(r.get("message") or ""))
            if not parsed:
                continue
            key = (str(parsed["symbol"]), str(parsed["market"]))
            advice[key] = parsed

    from collections import Counter

    mix = Counter(str(a["action"]) for a in advice.values())
    soft_n = sum(1 for a in advice.values() if a.get("soft"))
    lines.append(
        f"  советы модели (последние ~{max(1, lookback_ms // 60000)} мин): "
        f"n={len(advice)} HOLD={mix.get('HOLD', 0)} BUY={mix.get('BUY', 0)} "
        f"SELL={mix.get('SELL', 0)} soft={soft_n}"
    )
    # Prefer non-HOLD first for readability
    ordered = sorted(
        advice.values(),
        key=lambda a: (0 if a["action"] != "HOLD" else 1, str(a["symbol"]), str(a["market"])),
    )
    for a in ordered[:16]:
        mk = "fut" if a["market"] == "futures" else "spot"
        tag = "soft" if a.get("soft") else "model"
        lines.append(f"    {a['symbol']} [{mk}] → {a['action']} ({tag})")
    if len(ordered) > 16:
        lines.append(f"    … ещё {len(ordered) - 16}")
    if not advice:
        lines.append("    (нет свежих analysis в journal — включи Live / сделай тик)")

    se = pnl_live.get("sum_edge")
    su = pnl_live.get("sum_pnl_usdt")
    edge_s = f"{float(se):+.2%}" if isinstance(se, (int, float)) else "n/a"
    usd_s = f"{float(su):+.2f}" if isinstance(su, (int, float)) else "n/a"
    lines.append(f"  live PnL: edge={edge_s} · USDT={usd_s}")
    if model.get("weights_exist"):
        lines.append(
            f"  entry MLP: samples={model.get('samples')} "
            f"train_acc={model.get('train_accuracy')} (общая на все тикеры, 24 фичи)"
        )
    lines.append(
        "  вывод: смотри смесь HOLD/BUY/SELL выше — это «что крутится» сейчас; "
        "не per-ticker стратегия. Вопрос про устройство модели — отдельно "
        "(«одна модель или на каждый тикер?»)."
    )
    return "\n".join(lines)
