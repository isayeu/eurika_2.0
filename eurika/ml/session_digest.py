"""Session digest: «пока тебя не было» — what paper market did since last UI open.

No live orders. Pure read of `.eurika/ml/` artifacts + last-seen stamp.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from eurika.ml.live_paper import load_open_positions
from eurika.ml.market_store import ml_root
from eurika.ml.paper_portfolio import load_portfolio, portfolio_status
from eurika.ml.paper_trader import load_paper_trades

DEFAULT_LOOKBACK_MS = 12 * 60 * 60 * 1000  # first visit / stale: last 12h
MAX_LOOKBACK_MS = 7 * 24 * 60 * 60 * 1000


def session_seen_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "session_seen.json"


def load_session_seen(project_root: str | Path) -> dict[str, Any]:
    path = session_seen_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def mark_session_seen(
    project_root: str | Path,
    *,
    equity_usdt: float | None = None,
) -> dict[str, Any]:
    """Stamp «user saw Market» so the next open digests from here."""
    root = Path(project_root).resolve()
    path = session_seen_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    blob: dict[str, Any] = {
        "seen_ms": now,
        "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if equity_usdt is None:
        try:
            equity_usdt = float(portfolio_status(root).get("equity_usdt") or 0)
        except Exception:
            equity_usdt = None
    if isinstance(equity_usdt, (int, float)):
        blob["equity_usdt"] = float(equity_usdt)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return blob


def _fmt_ago(ms: int, now_ms: int) -> str:
    dt = max(0, int(now_ms) - int(ms))
    mins = dt // 60_000
    if mins < 60:
        return f"{mins} мин"
    hours = mins // 60
    if hours < 48:
        return f"{hours} ч"
    return f"{hours // 24} д"


def _tf(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%d.%m %H:%M")
    except Exception:
        return "?"


def build_session_digest(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    lookback_ms: int = DEFAULT_LOOKBACK_MS,
    mark_seen: bool = False,
) -> dict[str, Any]:
    """Aggregate paper activity since last seen (or lookback)."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    seen = load_session_seen(root)
    raw_seen = seen.get("seen_ms")
    try:
        prev_ms = int(raw_seen) if raw_seen is not None else None
    except (TypeError, ValueError):
        prev_ms = None
    if prev_ms is None or prev_ms <= 0 or now - prev_ms > MAX_LOOKBACK_MS:
        since_ms = now - max(60_000, int(lookback_ms))
        since_kind = "lookback"
    else:
        since_ms = prev_ms
        since_kind = "last_seen"

    prev_eq = seen.get("equity_usdt")
    try:
        prev_eq_f = float(prev_eq) if prev_eq is not None else None
    except (TypeError, ValueError):
        prev_eq_f = None

    try:
        bank = portfolio_status(root)
    except Exception:
        bank = {}
    eq = bank.get("equity_usdt")
    try:
        eq_f = float(eq) if eq is not None else None
    except (TypeError, ValueError):
        eq_f = None

    rows = [t for t in load_paper_trades(root) if t.get("live")]
    closed = [t for t in rows if (t.get("exit_ts") or 0) >= since_ms]
    filled = [t for t in closed if not str(t.get("exit_reason") or "").startswith("cancel")]
    cancelled = [t for t in closed if str(t.get("exit_reason") or "").startswith("cancel")]

    by_exit: Counter[str] = Counter(str(t.get("exit_reason") or "?") for t in filled)
    edges = [float(t["edge"]) for t in filled if isinstance(t.get("edge"), (int, float))]
    pnls = [float(t["pnl_usdt"]) for t in filled if isinstance(t.get("pnl_usdt"), (int, float))]
    wins = sum(1 for e in edges if e > 0)

    opens = load_open_positions(root)
    buy_n = sum(1 for o in opens if str(o.get("action") or "").upper() == "BUY")
    sell_n = sum(1 for o in opens if str(o.get("action") or "").upper() == "SELL")

    eq_delta = None
    if eq_f is not None and prev_eq_f is not None:
        eq_delta = eq_f - prev_eq_f
    elif eq_f is not None:
        try:
            start = float(load_portfolio(root).get("start_equity_usdt") or eq_f)
            eq_delta = eq_f - start
        except Exception:
            eq_delta = None

    out: dict[str, Any] = {
        "ok": True,
        "since_ms": since_ms,
        "since_kind": since_kind,
        "since_ago": _fmt_ago(since_ms, now),
        "since_at": _tf(since_ms),
        "now_ms": now,
        "equity_usdt": eq_f,
        "equity_delta_usdt": eq_delta,
        "filled": len(filled),
        "cancelled": len(cancelled),
        "wins": wins,
        "sum_edge": sum(edges) if edges else None,
        "sum_pnl_usdt": sum(pnls) if pnls else None,
        "by_exit": dict(by_exit),
        "opens": len(opens),
        "opens_buy": buy_n,
        "opens_sell": sell_n,
        "margin_used_usdt": bank.get("margin_used_usdt"),
        "max_margin_usdt": bank.get("max_margin_usdt"),
    }
    if mark_seen:
        mark_session_seen(root, equity_usdt=eq_f)
        out["marked_seen"] = True
    return out


def format_session_digest(data: dict[str, Any] | str | Path, project_root: str | Path = ".") -> str:
    """Human Russian block for Chat / Market transcript."""
    if isinstance(data, (str, Path)):
        st = build_session_digest(data)
    else:
        st = data
    if not st.get("ok"):
        return "DIGEST: нет данных"

    lines = ["ПОКА ТЕБЯ НЕ БЫЛО (paper)"]
    kind = "с прошлого визита" if st.get("since_kind") == "last_seen" else "за окно"
    lines.append(f"  период: {kind} с {st.get('since_at')} (~{st.get('since_ago')})")

    eq = st.get("equity_usdt")
    dlt = st.get("equity_delta_usdt")
    if isinstance(eq, (int, float)):
        dlt_s = f"{float(dlt):+.2f}$" if isinstance(dlt, (int, float)) else "n/a"
        lines.append(f"  банк: equity={float(eq):.2f} USDT · Δ={dlt_s}")

    filled = int(st.get("filled") or 0)
    canc = int(st.get("cancelled") or 0)
    wins = int(st.get("wins") or 0)
    se = st.get("sum_edge")
    sp = st.get("sum_pnl_usdt")
    edge_s = f"{float(se):+.2%}" if isinstance(se, (int, float)) else "n/a"
    pnl_s = f"{float(sp):+.2f}$" if isinstance(sp, (int, float)) else "n/a"
    lines.append(
        f"  закрыто: fill={filled} (wins={wins}/{filled or 0}) cancel={canc} · "
        f"Σedge={edge_s} · ΣPnL={pnl_s}"
    )

    by_exit = st.get("by_exit") or {}
    if by_exit:
        order = ["model", "time_stop", "trail", "tp", "horizon", "sl"]
        bits = []
        for k in order:
            if k in by_exit:
                bits.append(f"{k}={by_exit[k]}")
        for k, v in sorted(by_exit.items()):
            if k not in order:
                bits.append(f"{k}={v}")
        lines.append("  выходы: " + ", ".join(bits))

    opens = int(st.get("opens") or 0)
    lines.append(
        f"  открыто сейчас: {opens} (BUY={st.get('opens_buy', 0)} SELL={st.get('opens_sell', 0)}) · "
        f"маржа {float(st.get('margin_used_usdt') or 0):.0f}/"
        f"{float(st.get('max_margin_usdt') or 0):.0f}"
    )

    # One-line verdict
    sl_n = int(by_exit.get("sl") or 0)
    hz_n = int(by_exit.get("horizon") or 0)
    ts_n = int(by_exit.get("time_stop") or 0)
    model_n = int(by_exit.get("model") or 0)
    if filled == 0:
        verdict = "сделок не было — тихий период или Live был выкл"
    elif isinstance(dlt, (int, float)) and dlt <= -1.0:
        verdict = "банк просел — смотри SL/horizon vs model в «выходы»"
    elif isinstance(dlt, (int, float)) and dlt >= 1.0:
        verdict = "банк вырос — model/trail отрабатывают"
    elif sl_n >= max(3, model_n):
        verdict = "SL давит — карусель/вола; cooldown после SL должен резать reopen"
    elif hz_n > ts_n + model_n and hz_n >= 3:
        verdict = "много горизонта — time-stop ещё мало или MFE не вооружался"
    else:
        verdict = "смешанный период — смотри equity и доли выходов"
    lines.append(f"  вывод: {verdict}")
    return "\n".join(lines)
