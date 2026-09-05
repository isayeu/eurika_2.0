"""Aggregate paper-market learning progress for CLI / Qt (no secrets)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from eurika.ml.live_paper import load_open_positions
from eurika.ml.market_model import model_status
from eurika.ml.market_store import market_status, ml_root, normalize_market
from eurika.ml.paper_portfolio import portfolio_status
from eurika.ml.paper_trader import is_executed_trade, load_paper_trades, paper_status

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


def market_economic_verdict(st: dict[str, Any] | None) -> dict[str, Any]:
    """Judge paper Market by bankroll/edge, not by classification accuracy.

    Accuracy can be >0.5 while fees and sizing still drain equity. Chat and agents
    must treat negative Δ equity / negative mean edge as a loss, never «неплохо».
    """
    data = st if isinstance(st, dict) else {}
    bank = data.get("portfolio") or {}
    pnl = data.get("pnl") or {}
    pnl_live = pnl.get("live") or {}
    equity_delta = bank.get("session_pnl_usdt")
    if not isinstance(equity_delta, (int, float)):
        eq = bank.get("equity_usdt")
        start = bank.get("start_equity_usdt")
        if isinstance(eq, (int, float)) and isinstance(start, (int, float)):
            equity_delta = float(eq) - float(start)
        else:
            equity_delta = None
    mean_edge = pnl_live.get("mean_edge")
    if not isinstance(mean_edge, (int, float)):
        mean_edge = (pnl.get("all") or {}).get("mean_edge")
    edge_n = int(pnl_live.get("n") or pnl_live.get("edge_n") or 0)
    if edge_n <= 0:
        edge_n = int((pnl.get("all") or {}).get("n") or (pnl.get("all") or {}).get("edge_n") or 0)
    sum_pnl = pnl_live.get("sum_pnl_usdt")
    reasons: list[str] = []
    losing = False
    winning = False
    if isinstance(equity_delta, (int, float)):
        if float(equity_delta) <= -1.0:
            losing = True
            reasons.append(f"equity Δ={float(equity_delta):+.2f} USDT")
        elif float(equity_delta) >= 1.0:
            winning = True
            reasons.append(f"equity Δ={float(equity_delta):+.2f} USDT")
    if isinstance(mean_edge, (int, float)) and edge_n >= 20:
        if float(mean_edge) < 0.0:
            losing = True
            reasons.append(f"net edge/сделку={float(mean_edge):+.3%} (n={edge_n})")
        elif float(mean_edge) > 0.0 and not losing:
            winning = True
            reasons.append(f"net edge/сделку={float(mean_edge):+.3%} (n={edge_n})")
    if isinstance(sum_pnl, (int, float)) and float(sum_pnl) <= -1.0:
        losing = True
        if not any(r.startswith("PnL") for r in reasons):
            reasons.append(f"live PnL={float(sum_pnl):+.2f} USDT")
    if losing:
        label = "убыток"
        tone = "loss"
        next_step = (
            "ждать: копить опыт под текущими воротами; "
            "убыток экзамена ≠ сменить стратегию / новый entry / explore on"
        )
    elif winning:
        label = "в плюсе"
        tone = "gain"
        next_step = "держать скелет; смотреть, устойчив ли плюс на 24ч/72ч"
    else:
        label = "около нуля / мало данных"
        tone = "flat"
        next_step = "ждать больше закрытий под воротами"
        if not reasons:
            reasons.append("недостаточно закрытых сделок или Δ≈0")
    return {
        "tone": tone,
        "label": label,
        "equity_delta_usdt": float(equity_delta) if isinstance(equity_delta, (int, float)) else None,
        "mean_edge": float(mean_edge) if isinstance(mean_edge, (int, float)) else None,
        "reasons": reasons,
        "next_step": next_step,
        "note": "accuracy ≠ прибыль; суди по equity/edge после fee",
    }


def format_market_verdict_line(st: dict[str, Any] | None) -> str:
    v = market_economic_verdict(st)
    why = "; ".join(str(r) for r in (v.get("reasons") or [])[:3]) or "n/a"
    nxt = str(v.get("next_step") or "").strip()
    line = f"  вердикт: {v.get('label')} — {why} ({v.get('note')})"
    if nxt:
        line += f"\n  дальше: {nxt}"
    return line


def market_learning_status(project_root: str | Path) -> dict[str, Any]:
    """Snapshot of paper learning progress under ``.eurika/ml/``."""
    root = Path(project_root).resolve()
    paper = paper_status(root)
    model = model_status(root)
    market = market_status(root)
    opens = load_open_positions(root)
    rows = load_paper_trades(root)
    executed_rows = [r for r in rows if is_executed_trade(r)]
    live_rows = [r for r in executed_rows if r.get("live")]
    live_spot = [r for r in live_rows if _market_bucket(r) == "spot"]
    live_fut = [r for r in live_rows if _market_bucket(r) == "futures"]
    open_spot = [p for p in opens if _market_bucket(p) == "spot"]
    open_fut = [p for p in opens if _market_bucket(p) == "futures"]
    live_correct = sum(1 for r in live_rows if r.get("correct"))

    all_stats = _slice_stats(executed_rows)
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
        bank = portfolio_status(root)
    except Exception:
        bank = {}

    raw_meta = model.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    root_ml = ml_root(root)
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
            "heads": {
                "entry": _head_brief(meta, bool(model.get("weights_exist"))),
                "exit": _head_brief(
                    _as_dict(model.get("exit_meta")),
                    bool(model.get("exit_weights_exist")),
                ),
                "levels": _head_brief(
                    _as_dict(model.get("levels_meta")),
                    bool(model.get("levels_weights_exist")),
                ),
                "style": _head_brief(
                    _as_dict(model.get("style_meta")),
                    bool(model.get("style_weights_exist")),
                ),
            },
        },
        "gate": _gate_brief(root),
        "teacher": {
            "file_n": _jsonl_count(root_ml / "llm_teacher_samples.jsonl"),
            "mixed_in_entry": meta.get("llm_teacher_samples"),
            "hourly": _json_obj(root_ml / "cursor_hourly.json"),
            "analysis": _json_obj(root_ml / "llm_analysis.json"),
        },
        "market": market,
    }


def _json_obj(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    n += 1
    except OSError:
        return 0
    return n


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _head_brief(meta: dict[str, Any], weights_exist: bool) -> dict[str, Any]:
    return {
        "weights_exist": weights_exist,
        "samples": meta.get("samples"),
        "train_accuracy": meta.get("train_accuracy"),
        "train_mae": meta.get("train_mae"),
        "device": meta.get("device"),
        "llm_teacher_samples": meta.get("llm_teacher_samples"),
        "arch": meta.get("arch"),
        "hidden": meta.get("hidden"),
    }


def _gate_brief(project_root: Path) -> dict[str, Any]:
    try:
        from eurika.ml.entry_cost import load_cost_gate

        gate = dict(load_cost_gate(project_root))
    except Exception:
        gate = {}
    extra = _json_obj(ml_root(project_root) / "weights" / "entry_cost_gate.json")
    for key in ("covers_cost", "scanned", "markets", "calibrated", "required_edge"):
        if key in extra and key not in gate:
            gate[key] = extra[key]
    return gate


def _as_learning_status(
    st: dict[str, Any] | str | Path | None,
    project_root: str | Path,
) -> dict[str, Any]:
    if isinstance(st, (str, Path)):
        return market_learning_status(st)
    if st is not None:
        return st
    return market_learning_status(project_root)


def _fmt_usd(val: object) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):+.2f}"
    return "n/a"


def _fmt_num(val: object, digits: int = 2) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):.{digits}f}"
    return "n/a"


def _md_table(headers: list[str], rows: list[list[object]]) -> str:
    def cell(x: object) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ")

    head = "| " + " | ".join(cell(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


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
        format_market_verdict_line(data),
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
            f"  net edge/сделку: всего={_fmt_edge(pnl_all.get('mean_edge'))} "
            f"(n={pnl_all.get('n', 0)}) · live={_fmt_edge(pnl_live.get('mean_edge'))} "
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
    lines.append(
        "  note: без live-ордеров; Chat → Market для тиков; "
        "успех = equity/net edge после fee, не accuracy"
    )
    return "\n".join(lines)


def format_market_learning_report(
    st: dict[str, Any] | str | Path | None = None,
    project_root: str | Path = ".",
) -> str:
    """Full Chat answer: verdict, GFM tables, heads, gate, teacher (Russian)."""
    data = _as_learning_status(st, project_root)
    paper = data.get("paper") or {}
    live = data.get("live") or {}
    opens = data.get("opens") or {}
    model = data.get("model") or {}
    pnl = data.get("pnl") or {}
    bank = data.get("portfolio") or {}
    teacher = data.get("teacher") or {}
    gate = data.get("gate") or {}
    heads = model.get("heads") or {}
    live_spot = live.get("spot") or {}
    live_fut = live.get("futures") or {}
    pnl_all = pnl.get("all") or {}
    pnl_live = pnl.get("live") or {}
    pnl_sess = pnl.get("session") or {}
    verdict = market_economic_verdict(data)
    series_n = len((data.get("market") or {}).get("series") or [])
    positions = list(opens.get("positions") or [])

    eq = float(bank.get("equity_usdt") or 0)
    start = float(bank.get("start_equity_usdt") or 0)
    lines = [
        "## Paper-экзамен (без ордеров на биржу)",
        "",
        f"**Вердикт:** {verdict.get('label')} — "
        + "; ".join(str(r) for r in (verdict.get("reasons") or [])[:4]),
        "",
        f"**Дальше:** {verdict.get('next_step')}",
        "",
        "Accuracy — не прибыль: мелкие плюсы против более крупных минусов и комиссии. "
        "Судим по equity и net edge после fee.",
        "",
        "### Банк",
        _md_table(
            ["показатель", "значение"],
            [
                ["equity", f"{eq:.2f} USDT"],
                ["старт", f"{start:.0f} USDT"],
                ["Δ", f"{_fmt_usd(bank.get('session_pnl_usdt'))} USDT"],
                [
                    "маржа used/max",
                    f"{_fmt_num(bank.get('margin_used_usdt'), 1)} / "
                    f"{_fmt_num(bank.get('max_margin_usdt'), 1)}",
                ],
            ],
        ),
        "",
        "### Экзамен (live закрытия)",
        _md_table(
            ["срез", "n", "BUY", "SELL", "accuracy", "mean edge", "Σ PnL USDT"],
            [
                [
                    "live всего",
                    live.get("count", 0),
                    (live_spot.get("buys") or 0) + (live_fut.get("buys") or 0),
                    (live_spot.get("sells") or 0) + (live_fut.get("sells") or 0),
                    _fmt_num(live.get("accuracy"), 3),
                    _fmt_edge(pnl_live.get("mean_edge")),
                    _fmt_usd(pnl_live.get("sum_pnl_usdt")),
                ],
                [
                    "live spot",
                    live_spot.get("count", 0),
                    live_spot.get("buys", 0),
                    live_spot.get("sells", 0),
                    _fmt_num(live_spot.get("accuracy"), 3),
                    _fmt_edge(live_spot.get("mean_edge")),
                    _fmt_usd(live_spot.get("sum_pnl_usdt")),
                ],
                [
                    "live futures",
                    live_fut.get("count", 0),
                    live_fut.get("buys", 0),
                    live_fut.get("sells", 0),
                    _fmt_num(live_fut.get("accuracy"), 3),
                    _fmt_edge(live_fut.get("mean_edge")),
                    _fmt_usd(live_fut.get("sum_pnl_usdt")),
                ],
                [
                    "сессия (с вкл. Live)",
                    pnl_sess.get("n") or pnl_sess.get("count") or 0,
                    "—",
                    "—",
                    "—",
                    _fmt_edge(pnl_sess.get("mean_edge")),
                    _fmt_usd(pnl_sess.get("sum_pnl_usdt")),
                ],
            ],
        ),
        "",
        "### Вся выборка (live + тени)",
        _md_table(
            ["показатель", "значение"],
            [
                ["закрытий paper (экзамен)", paper.get("count", 0)],
                ["BUY / SELL", f"{paper.get('buys', 0)} / {paper.get('sells', 0)}"],
                ["accuracy paper", _fmt_num(paper.get("accuracy"), 3)],
                ["строк с edge", pnl_all.get("n", 0)],
                ["mean edge (все)", _fmt_edge(pnl_all.get("mean_edge"))],
                ["тени (shadow)", paper.get("shadow_count", 0)],
                ["cancelled", paper.get("cancelled_count", 0)],
                ["свечные серии", series_n],
            ],
        ),
    ]
    buys = int(paper.get("buys") or 0)
    sells = int(paper.get("sells") or 0)
    if buys + sells >= 20 and buys > sells * 3:
        lines.extend(
            [
                "",
                f"Перекос стороны: BUY {buys} vs SELL {sells} — это залипание entry, "
                "не отдельная стратегия на тикер.",
            ]
        )
    lines.extend(["", "### Открыто сейчас"])
    if not positions:
        lines.append("_нет открытых paper-позиций_")
    else:
        open_rows: list[list[object]] = []
        for p in positions[:_OPEN_LIST_LIMIT]:
            mk = "fut" if p.get("market") == "futures" else "spot"
            open_rows.append(
                [
                    p.get("symbol") or "?",
                    mk,
                    p.get("action") or "?",
                    _fmt_num(p.get("entry"), 4),
                    p.get("horizon") or "—",
                    _fmt_num(p.get("margin_usdt"), 2),
                    p.get("source") or "—",
                ]
            )
        lines.append(
            _md_table(
                ["тикер", "книга", "сторона", "вход", "гор.", "маржа", "источник"],
                open_rows,
            )
        )
        rest = len(positions) - min(len(positions), _OPEN_LIST_LIMIT)
        if rest > 0:
            lines.append(f"_… ещё {rest}_")

    def _acc_or_mae(head: dict[str, Any]) -> str:
        if isinstance(head.get("train_accuracy"), (int, float)):
            return f"acc {_fmt_num(head.get('train_accuracy'), 3)}"
        if isinstance(head.get("train_mae"), (int, float)):
            return f"MAE {_fmt_num(head.get('train_mae'), 3)}"
        return "n/a"

    head_rows = []
    for key, title in (
        ("entry", "entry MLP"),
        ("exit", "exit MLP"),
        ("levels", "levels"),
        ("style", "style"),
    ):
        h = _as_dict(heads.get(key))
        llm_n = h.get("llm_teacher_samples")
        extra = f" · LLM {llm_n}" if llm_n else ""
        head_rows.append(
            [
                title,
                "да" if h.get("weights_exist") else "нет",
                h.get("samples") if h.get("samples") is not None else "n/a",
                _acc_or_mae(h) + extra,
                h.get("device") or "—",
            ]
        )
    lines.extend(
        [
            "",
            "### Обучение голов (in-sample ≠ экзамен)",
            _md_table(
                ["голова", "веса", "сэмплы", "метрика", "device"],
                head_rows,
            ),
            "",
            "In-sample accuracy/MAE — не walk-forward. Головы учатся на live **и** тенях; "
            "деньги считает только live.",
            "",
            "### Стоимостные ворота",
            _md_table(
                ["показатель", "значение"],
                [
                    ["порог expansion_min", _fmt_num(gate.get("expansion_min"), 3)],
                    ["cost_mult", _fmt_num(gate.get("cost_mult"), 2)],
                    ["expected_edge", _fmt_edge(gate.get("expected_edge"))],
                    [
                        "covers_cost",
                        (
                            "да"
                            if gate.get("covers_cost") is True
                            else "нет"
                            if gate.get("covers_cost") is False
                            else "—"
                        ),
                    ],
                    ["калибровка n", gate.get("samples", 0)],
                    ["источник", gate.get("source") or "—"],
                ],
            ),
        ]
    )
    hourly = teacher.get("hourly") or {}
    analysis = teacher.get("analysis") or {}
    last_hourly = hourly.get("saved_at") or hourly.get("last_ms") or "—"
    hourly_ok = hourly.get("ok")
    hourly_s = (
        "ok"
        if hourly_ok is True
        else ("ошибка" if hourly_ok is False else "n/a")
    )
    lines.extend(
        [
            "",
            "### LLM-учитель (не открывает paper)",
            _md_table(
                ["показатель", "значение"],
                [
                    ["строк в llm_teacher_samples", teacher.get("file_n", 0)],
                    ["подмешано в последний entry train", teacher.get("mixed_in_entry") or 0],
                    ["hourly Cursor", f"{hourly_s} · {last_hourly}"],
                    ["hourly teacher_n", hourly.get("teacher_n") or "—"],
                    [
                        "LLM анализ TF/книга",
                        f"{analysis.get('tf1') or '—'} + {analysis.get('tf2') or '—'} / "
                        f"{analysis.get('markets') or '—'}",
                    ],
                ],
            ),
            "",
            "Live-ордеров нет. Explore / новый entry по убытку экзамена не включаем.",
        ]
    )
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
    load_journal: Any = None
    try:
        from eurika.ml.market_journal import load_market_journal

        load_journal = load_market_journal
    except Exception:
        load_journal = None

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

    # Recent model advice from journal (legacy: older builds wrote every-tick analysis).
    # Compact feed no longer persists analysis/hold/sync — opens + bank are the source of truth.
    advice: dict[tuple[str, str], dict[str, Any]] = {}
    last_ts = 0
    if load_journal is not None:
        try:
            rows = load_journal(root, limit=journal_tail)
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

    if advice:
        mix = Counter(str(a["action"]) for a in advice.values())
        soft_n = sum(1 for a in advice.values() if a.get("soft"))
        lines.append(
            f"  советы модели (последние ~{max(1, lookback_ms // 60000)} мин): "
            f"n={len(advice)} HOLD={mix.get('HOLD', 0)} BUY={mix.get('BUY', 0)} "
            f"SELL={mix.get('SELL', 0)} soft={soft_n}"
        )
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
    else:
        lines.append(
            "  советы модели: лента компактная (без per-tick analysis) — "
            "смотри открытые позиции выше и статус Live"
        )

    se = pnl_live.get("sum_edge")
    su = pnl_live.get("sum_pnl_usdt")
    edge_s = f"{float(se):+.2%}" if isinstance(se, (int, float)) else "n/a"
    usd_s = f"{float(su):+.2f}" if isinstance(su, (int, float)) else "n/a"
    lines.append(f"  live PnL: edge={edge_s} · USDT={usd_s}")
    lines.append(format_market_verdict_line(st))
    if model.get("weights_exist"):
        lines.append(
            f"  entry MLP: samples={model.get('samples')} "
            f"train_acc={model.get('train_accuracy')} (общая на все тикеры, 24 фичи)"
        )
    lines.append(
        "  вывод: экономика — по вердикту/equity и открытым позициям; "
        "accuracy in-sample ≠ экзамен. "
        "Вопрос про устройство модели — отдельно («одна модель или на каждый тикер?»)."
    )
    return "\n".join(lines)
