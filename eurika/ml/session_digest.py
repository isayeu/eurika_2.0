"""Session digest: «пока тебя не было» — what paper market did since last UI open.

No live orders. Pure read of `.eurika/ml/` artifacts + last-seen stamp.

Three separate paper banks (do not mix):
  1) Live / MLP exam — ``paper_portfolio.json``
  2) Portfolio / holistic — ``holistic_portfolio.json`` (trade+earn)
  3) LLM shadow — ``llm_shadow_portfolio.json``
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

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


def _f(val: object) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def snapshot_three_banks(project_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read Live, Portfolio, LLM-shadow bank snapshots (best-effort)."""
    root = Path(project_root).resolve()
    out: dict[str, dict[str, Any]] = {
        "live": {},
        "portfolio": {},
        "shadow": {},
    }
    try:
        bank = portfolio_status(root)
        out["live"] = {
            "equity_usdt": _f(bank.get("equity_usdt")),
            "margin_used_usdt": _f(bank.get("margin_used_usdt")),
            "max_margin_usdt": _f(bank.get("max_margin_usdt")),
            "start_equity_usdt": _f(bank.get("start_equity_usdt")),
        }
    except Exception:
        pass
    try:
        from eurika.ml.holistic_portfolio import reconcile_holistic

        h = reconcile_holistic(root)
        out["portfolio"] = {
            "equity_usdt": _f(h.get("equity_usdt")),
            "cash_free_usdt": _f(h.get("cash_free_usdt")),
            "earn_principal_usdt": _f(h.get("earn_principal_usdt")),
            "trade_realized_pnl_usdt": _f(h.get("trade_realized_pnl_usdt")),
            "start_equity_usdt": _f(h.get("start_equity_usdt")),
        }
    except Exception:
        pass
    try:
        from eurika.ml.llm_shadow import load_shadow_opens, shadow_portfolio_status

        sh = shadow_portfolio_status(root)
        opens = load_shadow_opens(root)
        out["shadow"] = {
            "equity_usdt": _f(sh.get("equity_usdt")),
            "margin_used_usdt": _f(sh.get("margin_used_usdt")),
            "max_margin_usdt": _f(sh.get("max_margin_usdt")),
            "start_equity_usdt": _f(sh.get("start_equity_usdt")),
            "opens": len(opens),
            "pending_n": int(sh.get("pending_n") or 0),
        }
    except Exception:
        pass
    return out


def mark_session_seen(
    project_root: str | Path,
    *,
    equity_usdt: float | None = None,
    banks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stamp «user saw Market» so the next open digests from here."""
    root = Path(project_root).resolve()
    path = session_seen_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    snap = banks if banks is not None else snapshot_three_banks(root)
    live_eq = equity_usdt
    if live_eq is None:
        live_eq = (snap.get("live") or {}).get("equity_usdt")
    blob: dict[str, Any] = {
        "seen_ms": now,
        "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if isinstance(live_eq, (int, float)):
        blob["equity_usdt"] = float(live_eq)
    port_eq = (snap.get("portfolio") or {}).get("equity_usdt")
    if isinstance(port_eq, (int, float)):
        blob["equity_portfolio_usdt"] = float(port_eq)
    sh_eq = (snap.get("shadow") or {}).get("equity_usdt")
    if isinstance(sh_eq, (int, float)):
        blob["equity_shadow_usdt"] = float(sh_eq)
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


def _bank_delta(
    now_eq: float | None,
    prev_eq: float | None,
    *,
    start_eq: float | None = None,
) -> float | None:
    if now_eq is None:
        return None
    if prev_eq is not None:
        return now_eq - prev_eq
    if start_eq is not None:
        return now_eq - start_eq
    return None


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

    snap = snapshot_three_banks(root)
    live = snap.get("live") or {}
    portfolio = snap.get("portfolio") or {}
    shadow = snap.get("shadow") or {}

    eq_f = _f(live.get("equity_usdt"))
    prev_live = _f(seen.get("equity_usdt"))
    eq_delta = _bank_delta(eq_f, prev_live, start_eq=_f(live.get("start_equity_usdt")))

    port_eq = _f(portfolio.get("equity_usdt"))
    port_delta = _bank_delta(
        port_eq,
        _f(seen.get("equity_portfolio_usdt")),
        start_eq=_f(portfolio.get("start_equity_usdt")),
    )
    sh_eq = _f(shadow.get("equity_usdt"))
    sh_delta = _bank_delta(
        sh_eq,
        _f(seen.get("equity_shadow_usdt")),
        start_eq=_f(shadow.get("start_equity_usdt")),
    )

    rows = [t for t in load_paper_trades(root) if t.get("live")]
    closed = [t for t in rows if (t.get("exit_ts") or 0) >= since_ms]
    filled = [t for t in closed if not str(t.get("exit_reason") or "").startswith("cancel")]
    cancelled = [t for t in closed if str(t.get("exit_reason") or "").startswith("cancel")]

    by_exit: Counter[str] = Counter(str(t.get("exit_reason") or "?") for t in filled)
    edges = [float(t["edge"]) for t in filled if isinstance(t.get("edge"), (int, float))]
    pnls = [float(t["pnl_usdt"]) for t in filled if isinstance(t.get("pnl_usdt"), (int, float))]
    wins = sum(1 for e in edges if e > 0)

    opens = [o for o in load_open_positions(root) if not o.get("shadow")]
    buy_n = sum(1 for o in opens if str(o.get("action") or "").upper() == "BUY")
    sell_n = sum(1 for o in opens if str(o.get("action") or "").upper() == "SELL")

    # Portfolio agent closed trades in window (assistant book).
    port_closed = 0
    port_pnl = None
    try:
        from eurika.ml.assistant_paper import assistant_trades_path

        tpath = assistant_trades_path(root)
        if tpath.is_file():
            pnls_p: list[float] = []
            for line in tpath.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                ts = int(row.get("ts") or row.get("exit_ts") or 0)
                if ts < since_ms:
                    continue
                port_closed += 1
                if isinstance(row.get("pnl_usdt"), (int, float)):
                    pnls_p.append(float(row["pnl_usdt"]))
            if pnls_p:
                port_pnl = sum(pnls_p)
    except Exception:
        pass

    out: dict[str, Any] = {
        "ok": True,
        "since_ms": since_ms,
        "since_kind": since_kind,
        "since_ago": _fmt_ago(since_ms, now),
        "since_at": _tf(since_ms),
        "now_ms": now,
        "equity_usdt": eq_f,
        "equity_delta_usdt": eq_delta,
        "banks": {
            "live": {
                "label": "Live/MLP exam",
                "equity_usdt": eq_f,
                "delta_usdt": eq_delta,
                "margin_used_usdt": live.get("margin_used_usdt"),
                "max_margin_usdt": live.get("max_margin_usdt"),
            },
            "portfolio": {
                "label": "Portfolio/holistic",
                "equity_usdt": port_eq,
                "delta_usdt": port_delta,
                "cash_free_usdt": portfolio.get("cash_free_usdt"),
                "earn_principal_usdt": portfolio.get("earn_principal_usdt"),
                "closed": port_closed,
                "sum_pnl_usdt": port_pnl,
            },
            "shadow": {
                "label": "LLM shadow",
                "equity_usdt": sh_eq,
                "delta_usdt": sh_delta,
                "margin_used_usdt": shadow.get("margin_used_usdt"),
                "max_margin_usdt": shadow.get("max_margin_usdt"),
                "opens": shadow.get("opens"),
                "pending_n": shadow.get("pending_n"),
            },
        },
        "filled": len(filled),
        "cancelled": len(cancelled),
        "wins": wins,
        "sum_edge": sum(edges) if edges else None,
        "sum_pnl_usdt": sum(pnls) if pnls else None,
        "by_exit": dict(by_exit),
        "opens": len(opens),
        "opens_buy": buy_n,
        "opens_sell": sell_n,
        "margin_used_usdt": live.get("margin_used_usdt"),
        "max_margin_usdt": live.get("max_margin_usdt"),
    }
    if mark_seen:
        mark_session_seen(root, equity_usdt=eq_f, banks=snap)
        out["marked_seen"] = True
    return out


def _fmt_bank_line(row: Mapping[str, Any] | None, *, extra: str = "") -> str:
    if not isinstance(row, dict):
        return "n/a"
    eq = row.get("equity_usdt")
    dlt = row.get("delta_usdt")
    label = str(row.get("label") or "?")
    if not isinstance(eq, (int, float)):
        return f"{label}: n/a"
    dlt_s = f"{float(dlt):+.2f}$" if isinstance(dlt, (int, float)) else "n/a"
    bits = [f"{label}: equity={float(eq):.2f} · Δ={dlt_s}"]
    if extra:
        bits.append(extra)
    return " · ".join(bits)


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

    banks = st.get("banks") if isinstance(st.get("banks"), dict) else {}
    live_b = banks.get("live") if isinstance(banks.get("live"), dict) else {
        "label": "Live/MLP exam",
        "equity_usdt": st.get("equity_usdt"),
        "delta_usdt": st.get("equity_delta_usdt"),
        "margin_used_usdt": st.get("margin_used_usdt"),
        "max_margin_usdt": st.get("max_margin_usdt"),
    }
    port_b = banks.get("portfolio") if isinstance(banks.get("portfolio"), dict) else {}
    sh_b = banks.get("shadow") if isinstance(banks.get("shadow"), dict) else {}

    lines.append("  банки (3 отдельных, не смешивать):")
    live_extra = ""
    if isinstance(live_b.get("margin_used_usdt"), (int, float)) and isinstance(
        live_b.get("max_margin_usdt"), (int, float)
    ):
        live_extra = (
            f"маржа {float(live_b['margin_used_usdt']):.0f}/"
            f"{float(live_b['max_margin_usdt']):.0f}"
        )
    lines.append(f"    {_fmt_bank_line(live_b, extra=live_extra)}")

    port_extra_bits: list[str] = []
    if isinstance(port_b.get("cash_free_usdt"), (int, float)):
        port_extra_bits.append(f"cash={float(port_b['cash_free_usdt']):.0f}")
    if isinstance(port_b.get("earn_principal_usdt"), (int, float)):
        port_extra_bits.append(f"earn={float(port_b['earn_principal_usdt']):.0f}")
    if int(port_b.get("closed") or 0) > 0:
        sp = port_b.get("sum_pnl_usdt")
        pnl_s = f"{float(sp):+.2f}$" if isinstance(sp, (int, float)) else "n/a"
        port_extra_bits.append(f"закрыто={int(port_b['closed'])} PnL={pnl_s}")
    lines.append(f"    {_fmt_bank_line(port_b, extra=' · '.join(port_extra_bits))}")

    sh_extra_bits: list[str] = []
    if isinstance(sh_b.get("opens"), int):
        sh_extra_bits.append(f"opens={sh_b['opens']}")
    if isinstance(sh_b.get("pending_n"), int) and int(sh_b["pending_n"]) > 0:
        sh_extra_bits.append(f"pending={sh_b['pending_n']}")
    if isinstance(sh_b.get("margin_used_usdt"), (int, float)) and isinstance(
        sh_b.get("max_margin_usdt"), (int, float)
    ):
        sh_extra_bits.append(
            f"маржа {float(sh_b['margin_used_usdt']):.0f}/"
            f"{float(sh_b['max_margin_usdt']):.0f}"
        )
    lines.append(f"    {_fmt_bank_line(sh_b, extra=' · '.join(sh_extra_bits))}")

    filled = int(st.get("filled") or 0)
    canc = int(st.get("cancelled") or 0)
    wins = int(st.get("wins") or 0)
    se = st.get("sum_edge")
    sp = st.get("sum_pnl_usdt")
    edge_s = f"{float(se):+.2%}" if isinstance(se, (int, float)) else "n/a"
    pnl_s = f"{float(sp):+.2f}$" if isinstance(sp, (int, float)) else "n/a"
    lines.append(
        f"  Live закрыто: fill={filled} (wins={wins}/{filled or 0}) cancel={canc} · "
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
        lines.append("  Live выходы: " + ", ".join(bits))

    opens = int(st.get("opens") or 0)
    lines.append(
        f"  Live открыто: {opens} (BUY={st.get('opens_buy', 0)} SELL={st.get('opens_sell', 0)}) · "
        f"маржа {float(st.get('margin_used_usdt') or 0):.0f}/"
        f"{float(st.get('max_margin_usdt') or 0):.0f}"
    )

    # One-line verdict — Live exam still drives the headline.
    dlt = st.get("equity_delta_usdt")
    sl_n = int(by_exit.get("sl") or 0)
    hz_n = int(by_exit.get("horizon") or 0)
    ts_n = int(by_exit.get("time_stop") or 0)
    model_n = int(by_exit.get("model") or 0)
    if filled == 0:
        verdict = "Live: сделок не было — тихий период или Live был выкл"
    elif isinstance(dlt, (int, float)) and dlt <= -1.0:
        verdict = "Live банк просел — смотри SL/horizon vs model в «выходы»"
    elif isinstance(dlt, (int, float)) and dlt >= 1.0:
        verdict = "Live банк вырос — model/trail отрабатывают"
    elif sl_n >= max(3, model_n):
        verdict = "SL давит — карусель/вола; cooldown после SL должен резать reopen"
    elif hz_n > ts_n + model_n and hz_n >= 3:
        verdict = "много горизонта — time-stop ещё мало или MFE не вооружался"
    else:
        verdict = "смешанный период — смотри три банка и Live выходы"
    lines.append(f"  вывод: {verdict}")
    return "\n".join(lines)
