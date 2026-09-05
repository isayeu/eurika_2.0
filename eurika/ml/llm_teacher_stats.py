"""Aggregate LLM teacher outcomes from ``llm_teacher_samples.jsonl`` (no shell)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eurika.ml.llm_teacher import load_teacher_samples
from eurika.ml.llm_shadow import (
    load_shadow_opens,
    load_shadow_trades,
    shadow_portfolio_status,
)


def llm_teacher_history_stats(
    project_root: str | Path,
    *,
    refresh: bool = True,
) -> dict[str, Any]:
    """Count settled LLM rows: n+/n−, mean edge, pending/skip — all time on disk."""
    root = Path(project_root).resolve()
    settle_run: dict[str, Any] | None = None
    if refresh:
        try:
            from eurika.ml.llm_teacher_settle import settle_teacher

            settle_run = settle_teacher(root)
        except Exception as exc:
            settle_run = {"error": f"{type(exc).__name__}: {exc}"}

    rows = load_teacher_samples(root)
    pending = [r for r in rows if not r.get("settled")]
    settled = [r for r in rows if r.get("settled")]
    skipped = [r for r in settled if r.get("skip")]
    expired = [r for r in settled if r.get("expired")]
    graded = [
        r
        for r in settled
        if not r.get("skip") and isinstance(r.get("edge"), (int, float))
    ]
    plus = [r for r in graded if float(r["edge"]) > 0]
    minus = [r for r in graded if float(r["edge"]) <= 0]
    directional_win = [
        r for r in graded if str(r.get("side") or "").upper() in {"BUY", "SELL"}
    ]
    yes_entries = [r for r in graded if str(r.get("enter") or "") == "yes"]

    edges = [float(r["edge"]) for r in graded]
    mean_edge = sum(edges) / len(edges) if edges else None

    by_source: dict[str, dict[str, int]] = {}
    for r in graded:
        src = str(r.get("settle_source") or "unknown")
        bucket = by_source.setdefault(src, {"n": 0, "plus": 0, "minus": 0})
        bucket["n"] += 1
        if float(r["edge"]) > 0:
            bucket["plus"] += 1
        else:
            bucket["minus"] += 1

    return {
        "project_root": str(root),
        "total": len(rows),
        "pending": len(pending),
        "settled": len(settled),
        "skipped": len(skipped),
        "expired": len(expired),
        "graded_n": len(graded),
        "plus_n": len(plus),
        "minus_n": len(minus),
        "directional_win_n": len(directional_win),
        "yes_entry_graded_n": len(yes_entries),
        "mean_edge": mean_edge,
        "by_source": by_source,
        "settle_run": settle_run,
    }


def _fmt_edge(val: float | None) -> str:
    if not isinstance(val, float):
        return "n/a"
    return f"{val:+.3%}"


def format_llm_teacher_stats_report(
    st: dict[str, Any] | str | Path | None = None,
    project_root: str | Path = ".",
    *,
    refresh: bool = True,
) -> str:
    """Markdown report for Chat (Russian, GFM tables)."""
    if isinstance(st, dict):
        data = st
    else:
        root = st if isinstance(st, (str, Path)) else project_root
        data = llm_teacher_history_stats(root, refresh=refresh)

    plus_n = int(data.get("plus_n") or 0)
    minus_n = int(data.get("minus_n") or 0)
    graded_n = int(data.get("graded_n") or 0)
    mean_edge = data.get("mean_edge")
    win_pct = (100.0 * plus_n / graded_n) if graded_n else None

    summary_rows = [
        ["всего строк в файле", str(data.get("total", 0))],
        ["ожидают settle (pending)", str(data.get("pending", 0))],
        ["settled (все)", str(data.get("settled", 0))],
        ["skip (не в train, напр. верный HOLD)", str(data.get("skipped", 0))],
        ["expired (>24ч без пути)", str(data.get("expired", 0))],
        ["**graded** (settled, не skip, есть edge)", f"**{graded_n}**"],
        ["**в плюсе** (edge > 0)", f"**{plus_n}**"],
        ["в минусе / ноль (edge ≤ 0)", str(minus_n)],
        [
            "доля плюса среди graded",
            f"{win_pct:.1f}%" if win_pct is not None else "n/a",
        ],
        ["средний edge graded", _fmt_edge(mean_edge if isinstance(mean_edge, float) else None)],
        ["directional win (side остался BUY/SELL)", str(data.get("directional_win_n", 0))],
    ]

    lines = [
        "## LLM-учитель: исходы прогнозов (вся история на диске)",
        "",
        f"`{data.get('project_root')}` · файл `llm_teacher_samples.jsonl`",
        "",
        "Оценка: после `settle_teacher` строка с **BUY/SELL** считается в плюсе, "
        "если сопоставленный путь (live close или свечи TP/SL) дал **edge > 0** после fee. "
        "Убыточный совет → метка HOLD и минус в graded.",
        "",
        "### Сводка",
        "| показатель | значение |",
        "| --- | --- |",
    ]
    for left, right in summary_rows:
        lines.append(f"| {left} | {right} |")

    by_source = data.get("by_source") or {}
    if by_source:
        lines.extend(["", "### По источнику settle", "| источник | graded | в плюсе | в минусе |", "| --- | --- | --- | --- |"])
        for src in sorted(by_source):
            b = by_source[src]
            lines.append(f"| {src} | {b.get('n', 0)} | {b.get('plus', 0)} | {b.get('minus', 0)} |")

    settle_run = data.get("settle_run")
    if isinstance(settle_run, dict) and settle_run:
        if settle_run.get("error"):
            lines.extend(["", f"_settle при запросе: {settle_run['error']}_"])
        elif int(settle_run.get("settled") or 0) or int(settle_run.get("expired") or 0):
            lines.extend(
                [
                    "",
                    f"_Этот запрос: новых settle={settle_run.get('settled', 0)}, "
                    f"expired={settle_run.get('expired', 0)}, pending={settle_run.get('pending', 0)}_",
                ]
            )

    lines.extend(
        [
            "",
            "Это **не** paper PnL и **не** train accuracy — только оценка советов LLM по пути свечей. "
            "Объём строк в файле ≠ число прибыльных прогнозов.",
        ]
    )
    return "\n".join(lines)


_EXECUTION_LINK_KEYS = (
    "used_in_trade",
    "opened_paper",
    "paper_open",
    "executed",
    "from_llm",
    "llm_advice",
)


def llm_teacher_execution_audit(project_root: str | Path) -> dict[str, Any]:
    """Did paper MLP ever open because of LLM advice? (architecture + disk check)."""
    root = Path(project_root).resolve()
    rows = load_teacher_samples(root)
    from eurika.ml.paper_trader import is_executed_trade, load_paper_trades

    live_trades = [
        t for t in load_paper_trades(root) if is_executed_trade(t) and t.get("live")
    ]
    llm_tagged_trades = [
        t
        for t in live_trades
        if any(
            token in str(t.get("source") or "").lower()
            for token in ("llm", "teacher", "cursor")
        )
    ]
    link_keys_hit: dict[str, int] = {}
    for row in rows:
        for key in _EXECUTION_LINK_KEYS:
            if row.get(key):
                link_keys_hit[key] = link_keys_hit.get(key, 0) + 1

    live_settle = [
        r
        for r in rows
        if r.get("settled")
        and str(r.get("settle_source") or "").lower() == "live"
        and not r.get("skip")
    ]
    meta_llm_mixed = 0
    try:
        from eurika.ml.market_model import meta_path

        mp = meta_path(root)
        if mp.is_file():
            import json

            meta = json.loads(mp.read_text(encoding="utf-8"))
            meta_llm_mixed = int(meta.get("llm_teacher_samples") or 0)
    except Exception:
        meta_llm_mixed = 0

    return {
        "project_root": str(root),
        "live_trades_n": len(live_trades),
        "paper_trades_llm_source_n": len(llm_tagged_trades),
        "teacher_samples_n": len(rows),
        "teacher_execution_keys": link_keys_hit,
        "teacher_settled_via_live_n": len(live_settle),
        "entry_train_llm_mixed_n": meta_llm_mixed,
        "executes_by_design": False,
    }


def format_llm_teacher_execution_report(
    project_root: str | Path = ".",
) -> str:
    """Answer: did MLP paper ever trade on LLM advice? (Russian markdown)."""
    data = llm_teacher_execution_audit(project_root)
    live_n = int(data.get("live_trades_n") or 0)
    llm_trades = int(data.get("paper_trades_llm_source_n") or 0)
    live_settle = int(data.get("teacher_settled_via_live_n") or 0)
    mixed = int(data.get("entry_train_llm_mixed_n") or 0)
    exec_keys = data.get("teacher_execution_keys") or {}

    verdict = (
        "**Нет** — paper MLP **не исполняет** советы LLM и **не подменяет** argmax."
        if llm_trades == 0 and not exec_keys
        else "**Да (анomaly)** — найдены сделки с llm/teacher в source."
    )

    exec_n = sum(exec_keys.values()) if exec_keys else 0
    lines = [
        "## ML и советы LLM-учителя",
        "",
        f"`{data.get('project_root')}`",
        "",
        verdict,
        "",
        "### Как устроено (код)",
        "- `cursor_hourly` → journal + `harvest_teacher` → **`llm_teacher_samples.jsonl`**; "
        "**paper не открывается**.",
        "- `llm_teacher.py`: метки **только для train**; never opens paper / never replaces argmax.",
        "- Вход paper = **entry MLP** + ворота + soft/explore; не прямой вызов LLM.",
        "- LLM-метки подмешиваются в **дообучение** (`mix_teacher_xy`) — косвенный эффект на веса, "
        "не команда «войти сейчас».",
        "",
        "### Проверка на диске",
        "| проверка | результат |",
        "| --- | --- |",
        f"| live-сделок в `paper_trades.jsonl` | {live_n} |",
        f"| из них `source` содержит llm/teacher/cursor | **{llm_trades}** |",
        f"| поля исполнения в teacher samples | {exec_n} |",
        f"| teacher settle через live close (оценка совпадения, не причина входа) | {live_settle} |",
        f"| LLM-строк в последнем entry train | {mixed} |",
        "",
        "### Вывод",
        "Paper **ни разу** не открывался *потому что* LLM так сказал. "
        f"{live_settle} советов LLM оценены post-hoc по **уже случившимся** live-закрытиям MLP — "
        "это совпадение для settle, не следование совету.",
    ]
    return "\n".join(lines)


def llm_shadow_history_stats(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    trades = load_shadow_trades(root)
    opens = load_shadow_opens(root)
    port = shadow_portfolio_status(root)
    edges = [float(r["edge"]) for r in trades if isinstance(r.get("edge"), (int, float))]
    pnls = [float(r["pnl_usdt"]) for r in trades if isinstance(r.get("pnl_usdt"), (int, float))]
    plus = sum(1 for r in trades if isinstance(r.get("edge"), (int, float)) and float(r["edge"]) > 0)
    spot = [r for r in trades if str(r.get("market") or "spot") == "spot"]
    fut = [r for r in trades if str(r.get("market") or "") == "futures"]
    return {
        "project_root": str(root),
        "portfolio": port,
        "opens_n": len(opens),
        "trades_n": len(trades),
        "plus_n": plus,
        "minus_n": max(0, len(trades) - plus),
        "mean_edge": (sum(edges) / len(edges)) if edges else None,
        "sum_pnl_usdt": sum(pnls) if pnls else 0.0,
        "spot_n": len(spot),
        "futures_n": len(fut),
    }


def format_llm_shadow_report(project_root: str | Path = ".") -> str:
    root = Path(project_root).resolve()
    st = llm_shadow_history_stats(root)
    port = st.get("portfolio") or {}
    try:
        from eurika.ml.learning_status import market_learning_status

        mlp = market_learning_status(root)
    except Exception:
        mlp = {}
    live = (mlp.get("pnl") or {}).get("live") or {}
    bank = mlp.get("portfolio") or {}
    lines = [
        "## LLM Shadow Portfolio",
        "",
        f"`{st.get('project_root')}`",
        "",
        "Отдельный теневой банк для hourly LLM-советов: market / limit / stop / OCO, "
        "свои TP/SL/trail/horizon, без записи в `paper_portfolio.json` и `paper_trades.jsonl`.",
        "",
        "### LLM shadow",
        "| показатель | значение |",
        "| --- | --- |",
        f"| equity | {float(port.get('equity_usdt') or 0.0):.2f} USDT |",
        f"| старт | {float(port.get('start_equity_usdt') or 0.0):.0f} USDT |",
        f"| Δ | {float(port.get('session_pnl_usdt') or 0.0):+.2f} USDT |",
        f"| открыто | {int(st.get('opens_n') or 0)} |",
        f"| pending | {int(port.get('pending_n') or 0)} |",
        f"| закрыто | {int(st.get('trades_n') or 0)} |",
        f"| в плюсе | {int(st.get('plus_n') or 0)} |",
        f"| в минусе/0 | {int(st.get('minus_n') or 0)} |",
        f"| mean edge | {_fmt_edge(st.get('mean_edge') if isinstance(st.get('mean_edge'), float) else None)} |",
        f"| Σ PnL USDT | {float(st.get('sum_pnl_usdt') or 0.0):+.2f} |",
        f"| split spot/fut | {int(st.get('spot_n') or 0)} / {int(st.get('futures_n') or 0)} |",
        "",
        "### Сравнение с MLP paper",
        "| экзамен | n | mean edge | Σ PnL | equity Δ |",
        "| --- | --- | --- | --- | --- |",
        f"| MLP paper live | {int(live.get('n') or 0)} | {_fmt_edge(live.get('mean_edge') if isinstance(live.get('mean_edge'), float) else None)} | {float(live.get('sum_pnl_usdt') or 0.0):+.2f} | {float(bank.get('session_pnl_usdt') or 0.0):+.2f} |",
        f"| LLM shadow | {int(st.get('trades_n') or 0)} | {_fmt_edge(st.get('mean_edge') if isinstance(st.get('mean_edge'), float) else None)} | {float(st.get('sum_pnl_usdt') or 0.0):+.2f} | {float(port.get('session_pnl_usdt') or 0.0):+.2f} |",
    ]
    return "\n".join(lines)
