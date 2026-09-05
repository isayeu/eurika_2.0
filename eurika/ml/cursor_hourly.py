"""Hourly Cursor teacher: independent market read → journal + MLP labels.

Never opens paper and never echoes MLP/gate decisions as the verdict.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from eurika.ml.market_journal import append_market_journal, load_market_journal
from eurika.ml.market_store import ml_root
from eurika.ml.paper_trader import is_executed_trade, load_paper_trades

INTERVAL_MS = 15 * 60 * 1000
KIND = "cursor_hour"
MAX_FACTS_CHARS = 2800
MAX_TEXT_CHARS = 8000
ChatFn = Callable[[str], tuple[str | None, str | None]]


def stamp_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "cursor_hourly.json"


def load_stamp(project_root: str | Path) -> dict[str, Any]:
    path = stamp_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_stamp(project_root: str | Path, blob: dict[str, Any]) -> Path:
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


def _sum_num(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]
    return sum(vals) if vals else None


def _symbol_edges(rows: list[dict[str, Any]]) -> list[tuple[str, float, int]]:
    buckets: dict[str, list[float]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym or not isinstance(row.get("edge"), (int, float)):
            continue
        buckets.setdefault(sym, []).append(float(row["edge"]))
    ranked = [
        (sym, sum(vals), len(vals))
        for sym, vals in buckets.items()
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def hour_snapshot(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    lookback_ms: int = INTERVAL_MS,
) -> dict[str, Any]:
    """Read-only hour facts from paper_trades + journal + cost gate."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    since = now - max(60_000, int(lookback_ms))
    closed = [
        t
        for t in load_paper_trades(root)
        if int(t.get("exit_ts") or 0) >= since
    ]
    executed = [t for t in closed if is_executed_trade(t)]
    live_rows = [t for t in executed if t.get("live") and not t.get("shadow")]
    shadow_rows = [t for t in executed if t.get("shadow")]
    by_exit = Counter(str(t.get("exit_reason") or "?") for t in live_rows)
    ranked = _symbol_edges(live_rows)
    journal = load_market_journal(root, limit=4000)
    gate_rejects = 0
    for row in journal:
        ts = int(row.get("ts") or 0)
        if ts < since:
            continue
        msg = str(row.get("message") or "")
        if str(row.get("kind") or "") == "hold" and "отклонён" in msg:
            gate_rejects += 1
    gate: dict[str, Any] = {}
    try:
        from eurika.ml.entry_cost import cost_gate_path, load_cost_gate

        gate = load_cost_gate(root)
        path = cost_gate_path(root)
        if path.is_file():
            extra = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(extra, dict) and "covers_cost" in extra:
                gate["covers_cost"] = extra.get("covers_cost")
    except Exception:
        gate = {}
    return {
        "ok": True,
        "now_ms": now,
        "since_ms": since,
        "live_n": len(live_rows),
        "shadow_n": len(shadow_rows),
        "sum_edge_live": _sum_num(live_rows, "edge"),
        "sum_pnl_live": _sum_num(live_rows, "pnl_usdt"),
        "by_exit": dict(by_exit),
        "best_symbols": ranked[:3],
        "worst_symbols": list(reversed(ranked[-3:])) if ranked else [],
        "gate_rejects": gate_rejects,
        "gate": {
            "expansion_min": gate.get("expansion_min"),
            "covers_cost": gate.get("covers_cost"),
            "expected_edge": gate.get("expected_edge"),
        },
    }


def _fmt_edge(val: object) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):+.3%}"
    return "n/a"


def _fmt_usd(val: object) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):+.2f}"
    return "n/a"


def _fmt_symbols(items: list[tuple[str, float, int]]) -> str:
    if not items:
        return "—"
    return ", ".join(f"{sym} Σedge={edge:+.3%} n={n}" for sym, edge, n in items)


def format_hour_facts(snap: dict[str, Any]) -> str:
    gate = snap.get("gate") or {}
    covers = gate.get("covers_cost")
    covers_s = "yes" if covers is True else "no" if covers is False else "n/a"
    exp = gate.get("expansion_min")
    exp_s = f"{float(exp):+.2f}" if isinstance(exp, (int, float)) else "n/a"
    by_exit = snap.get("by_exit") or {}
    exits = ", ".join(f"{k}={v}" for k, v in sorted(by_exit.items())) or "—"
    return "\n".join(
        [
            "MLP EXAM (last 60m) — справка, не копировать вердикт",
            f"  live closed={snap.get('live_n', 0)} shadow closed={snap.get('shadow_n', 0)}",
            f"  live Σedge={_fmt_edge(snap.get('sum_edge_live'))} "
            f"ΣPnL={_fmt_usd(snap.get('sum_pnl_live'))}",
            f"  exits: {exits}",
            f"  best: {_fmt_symbols(list(snap.get('best_symbols') or []))}",
            f"  worst: {_fmt_symbols(list(snap.get('worst_symbols') or []))}",
            f"  cost-gate rejects this hour={snap.get('gate_rejects', 0)} "
            f"expansion_min={exp_s} covers_cost={covers_s}",
        ]
    )


def build_prompt(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
) -> str:
    from eurika.ml.cursor_hourly_brief import (
        LEADING_HAND_RULES,
        collect_ticker_cards,
        format_ticker_cards,
        load_analysis_prefs,
    )
    from eurika.ml.llm_shadow import format_shadow_opens_for_prompt

    root = Path(project_root).resolve()
    snap = hour_snapshot(root, now_ms=now_ms)
    cards = collect_ticker_cards(root, now_ms=now_ms if now_ms is not None else snap.get("now_ms"))
    facts = format_hour_facts(snap)
    if len(facts) > MAX_FACTS_CHARS:
        facts = facts[: MAX_FACTS_CHARS - 1] + "…"
    return (
        LEADING_HAND_RULES
        + "\n"
        + format_ticker_cards(cards, markets=load_analysis_prefs(root)[2])
        + "\n\n"
        + facts
        + "\n\n"
        + format_shadow_opens_for_prompt(root)
        + "\n\n"
        + (
            "FINAL JSON (required). Prose never places orders — only shadow_actions do.\n"
            '{"samples":[...],"shadow_actions":[...]}\n'
            "shadow_actions rules:\n"
            "- wait-for-level / bounce / breakout → "
            '{"action":"place","side":"BUY|SELL","entry_style":"limit|stop|oco",'
            '"limit_px":N,"stop_px":N,"invalidate_px":N,'
            '"tp_pct":0.024,"sl_pct":0.008,"trail_pct":0.008}\n'
            "- enter now → "
            '{"action":"open","side":"BUY|SELL","entry_style":"market",'
            '"tp_pct":0.024,"sl_pct":0.008,"trail_pct":0.008}\n'
            "- manage existing LLM SHADOW OPENS/PENDING → "
            "hold | update | cancel | close | add (numeric fields when changing levels).\n"
            "- no setup → omit place/open for that ticker (samples.enter=no|wait is enough).\n"
            "Prices absolute (limit_px/stop_px), tp/sl as fractions; prefer TP≈3×SL."
        )
    )


def journal_body(text: str) -> str:
    """Reasoning for the feed. The labels JSON is protocol, not something to read."""
    body = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", text or "", flags=re.S)
    idx = body.rfind('"samples"')
    if idx >= 0:
        start = body.rfind("{", 0, idx + 1)
        if start >= 0:
            body = body[:start]
    body = body.strip()
    if len(body) > MAX_TEXT_CHARS:
        body = body[: MAX_TEXT_CHARS - 1] + "…"
    return body or "пустой ответ"


def _default_chat(prompt: str) -> tuple[str | None, str | None]:
    from eurika.agent.cursor_judge import complete_chat

    return complete_chat(prompt)


def _ensure_analysis_candles(project_root: str | Path) -> None:
    """Best-effort sync of TF1/TF2 + 1m for open/pending shadow symbols.

    Without Live-tick running, shadow fill/resolve needs fresh 1m candles too.
    """
    from eurika.ml.cursor_hourly_brief import load_analysis_prefs, wanted_store_kinds
    from eurika.ml.llm_shadow import load_shadow_opens
    from eurika.ml.llm_shadow_orders import load_shadow_pending
    from eurika.ml.market_store import sync_klines
    from eurika.ml.universe import load_ticker_lists

    root = Path(project_root).resolve()
    tf1, tf2, markets = load_analysis_prefs(root)
    wanted = wanted_store_kinds(markets)
    lists = load_ticker_lists(root)
    jobs: list[tuple[str, str]] = []
    if "spot" in wanted:
        jobs.extend((sym, "spot") for sym in lists.get("spot") or [])
    if "futures" in wanted:
        jobs.extend((sym, "futures") for sym in lists.get("futures") or [])
    seen_iv = list(dict.fromkeys([tf1, tf2]))
    for symbol, kind in jobs:
        for interval in seen_iv:
            try:
                sync_klines(root, symbol=symbol, interval=interval, market=kind, limit=200)
            except Exception:
                continue
    # Shadow opens + pendings need 1m candles for fill/TP/SL even when Live is off.
    shadow_needs: set[tuple[str, str]] = set()
    for pos in list(load_shadow_opens(root)) + list(load_shadow_pending(root)):
        sym = str(pos.get("symbol") or "").upper()
        mkt = str(pos.get("market") or "spot").lower()
        if sym:
            shadow_needs.add((sym, mkt))
    for symbol, kind in shadow_needs:
        try:
            sync_klines(root, symbol=symbol, interval="1m", market=kind, limit=400)
        except Exception:
            continue


def run_hourly_critique(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    force: bool = False,
    complete_chat: ChatFn | None = None,
    persist: bool = True,
    train: bool = True,
) -> dict[str, Any]:
    """One independent Cursor market-read. Journal + teacher samples; no paper open."""
    from eurika.ml.cursor_hourly_brief import collect_ticker_cards

    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    if not force and not is_due(root, now_ms=now):
        return {"ok": True, "skipped": "not_due", "persisted": False}
    _ensure_analysis_candles(root)
    cards = collect_ticker_cards(root, now_ms=now)
    prompt = build_prompt(root, now_ms=now)
    chat = complete_chat or _default_chat
    text, err = chat(prompt)
    ok = bool(text) and not err
    full = (text or err or "пустой ответ").strip()
    body = journal_body(full)
    teacher: dict[str, Any] = {"parsed": 0, "stored": 0, "skipped": 0}
    trained: dict[str, Any] | None = None
    shadow: dict[str, Any] | None = None
    if ok:
        from eurika.ml.llm_teacher import harvest_teacher
        from eurika.ml.llm_shadow import (
            apply_shadow_actions,
            ingest_pending_fills,
            open_from_teacher_rows,
            parse_shadow_actions,
            resolve_llm_shadow,
        )

        # Labels come from the untruncated answer: the JSON block sits after the prose.
        teacher = harvest_teacher(root, full, cards, now_ms=now)
        try:
            filled = ingest_pending_fills(root, now_ms=now)
            actions = parse_shadow_actions(full)
            managed = apply_shadow_actions(root, actions)
            raw_rows = teacher.get("rows")
            teacher_rows: list[dict[str, Any]] = raw_rows if isinstance(raw_rows, list) else []
            opened = open_from_teacher_rows(root, teacher_rows)
            resolved = resolve_llm_shadow(root, now_ms=now)
            shadow = {
                "managed": managed.get("applied"),
                "pending_filled": int(filled.get("filled") or 0),
                "pending_cancelled": int(filled.get("cancelled") or 0),
                "opened": int(opened.get("opened") or 0),
                "rejected": int(opened.get("rejected") or 0),
                "closed": int(resolved.get("closed") or 0),
                "waiting": int(resolved.get("waiting") or 0),
            }
        except Exception as exc:
            shadow = {"error": f"{type(exc).__name__}: {exc}"}
        if train and int(teacher.get("stored") or 0) > 0:
            try:
                from eurika.ml.market_model import train_market_levels_policy, train_market_policy

                trained = train_market_policy(root, epochs=12)
                train_market_levels_policy(root, epochs=12)
            except Exception as exc:
                trained = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    extra = ""
    stored_n = int(teacher.get("stored") or 0)
    if stored_n:
        extra = f" [метки MLP={stored_n}"
        if trained and trained.get("ok"):
            extra += f", дообучение={trained.get('train_accuracy')}"
        elif trained and trained.get("error"):
            extra += ", дообучение пропущено"
        extra += "]"
    if shadow and not shadow.get("error"):
        raw_managed = shadow.get("managed")
        managed = raw_managed if isinstance(raw_managed, dict) else {}
        extra += (
            f" [LLM shadow open={int(shadow.get('opened') or 0)}"
            f" fill={int(shadow.get('pending_filled') or 0)}"
            f" close={int(shadow.get('closed') or 0)}"
            f" wait={int(shadow.get('waiting') or 0)}]"
        )
        if managed:
            extra += (
                f" [manage place={int(managed.get('place') or 0)}"
                f" open={int(managed.get('open') or 0)}"
                f" close={int(managed.get('close') or 0)}"
                f" add={int(managed.get('add') or 0)}"
                f" upd={int(managed.get('update') or 0)}"
                f" cancel={int(managed.get('cancel') or 0)}]"
            )
    elif shadow and shadow.get("error"):
        extra += " [LLM shadow error]"
    message = f"LLM 15м: {body}{extra}"
    persisted = False
    if persist:
        append_market_journal(
            root,
            message,
            kind=KIND,
            extras={
                "ok": ok,
                "source": "cursor",
                "teacher_n": stored_n,
                "llm_shadow_opened": int(shadow.get("opened") or 0) if isinstance(shadow, dict) else 0,
                "llm_shadow_closed": int(shadow.get("closed") or 0) if isinstance(shadow, dict) else 0,
            },
        )
        persisted = True
    save_stamp(
        root,
        {
            "last_ms": now,
            "ok": ok,
            "error": (err or "") if not ok else "",
            "teacher_n": stored_n,
        },
    )
    return {
        "ok": ok,
        "skipped": "",
        "text": body if ok else "",
        "error": err or ("" if ok else body),
        "message": message,
        "persisted": persisted,
        "kind": KIND,
        "teacher": teacher,
        "shadow": shadow,
        "trained": trained,
    }
