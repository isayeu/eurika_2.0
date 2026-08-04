"""Chat → Market (live paper) handlers. No live Binance orders."""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QListWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow

_DEFAULT_SYMBOL = "BTCUSDT"


def _market_mode_from_ui(main: MainWindow) -> str:
    """Return spot|futures|both from Market combo."""
    if not hasattr(main, "market_kind_combo"):
        return "spot"
    text = (main.market_kind_combo.currentText() or "Spot").strip().lower()
    if text.startswith("fut"):
        return "futures"
    if text.startswith("both") or text.startswith("оба"):
        return "both"
    return "spot"


def _market_mode_label(mode: str) -> str:
    m = (mode or "spot").lower()
    if m == "futures":
        return "futures"
    if m == "both":
        return "spot+fut"
    return "spot"


def _list_symbols(widget: QListWidget | None) -> list[str]:
    if widget is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for i in range(widget.count()):
        item = widget.item(i)
        if item is None:
            continue
        u = (item.text() or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _set_list_symbols(widget: QListWidget | None, symbols: list[str]) -> None:
    if widget is None:
        return
    widget.blockSignals(True)
    widget.clear()
    for sym in symbols:
        widget.addItem(sym)
    widget.blockSignals(False)


def spot_symbols_from_ui(main: MainWindow) -> list[str]:
    return _list_symbols(getattr(main, "market_spot_list", None))


def futures_symbols_from_ui(main: MainWindow) -> list[str]:
    return _list_symbols(getattr(main, "market_futures_list", None))


def _project_root(main: MainWindow) -> str:
    if hasattr(main, "root_edit"):
        return main.root_edit.text().strip()
    return ""


class MarketTickWorker(QThread):
    """Run live paper tick off the UI thread."""

    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, project_root: str, opts: dict[str, Any], parent: Any = None) -> None:
        super().__init__(parent)
        self._root = project_root
        self._opts = opts

    def run(self) -> None:
        try:
            from eurika.ml.live_paper import run_live_universe_tick
            from eurika.ml.market_store import parse_markets
            from eurika.ml.universe import normalize_symbol_list
            from eurika.utils.env import load_project_dotenv

            load_project_dotenv(self._root)
            opts = dict(self._opts)
            market_mode = str(opts.pop("market_mode", None) or "spot")
            markets = parse_markets(market_mode)
            fallback = str(opts.pop("fallback_symbol", None) or _DEFAULT_SYMBOL)

            spot_raw = list(opts.pop("spot_symbols", None) or [])
            fut_raw = list(opts.pop("futures_symbols", None) or [])
            opts.pop("symbol", None)
            opts.pop("universe_from_balances", None)

            spot_syms = normalize_symbol_list(spot_raw, fallback=fallback)
            fut_syms = normalize_symbol_list(fut_raw, fallback=fallback)

            # Only pass lists needed for active markets; empty → fallback already applied.
            symbols = spot_syms if "spot" in markets else []
            futures_symbols = fut_syms if "futures" in markets else []
            if "spot" in markets and not symbols:
                symbols = [fallback]
            if "futures" in markets and not futures_symbols:
                futures_symbols = [fallback]
            # Universe tick always needs a spot list arg; for futures-only use fut list as placeholder
            # for the symbols= arg (jobs built from markets + futures_symbols).
            if "spot" not in markets:
                symbols = futures_symbols or [fallback]

            uni_meta: dict[str, Any] = {
                "ok": True,
                "symbols": list(spot_syms) if "spot" in markets else [],
                "futures_symbols": list(futures_symbols) if "futures" in markets else [],
                "source": "lists",
                "fallback_used": False,
                "count": (len(spot_syms) if "spot" in markets else 0)
                + (len(futures_symbols) if "futures" in markets else 0),
                "error": None,
            }

            result = run_live_universe_tick(
                self._root,
                symbols=symbols,
                markets=markets,
                futures_symbols=futures_symbols if "futures" in markets else None,
                **opts,
            )
            result["universe"] = uni_meta
            result["markets"] = list(markets)
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# Kind badge + body tint for Market transcript (light/dark-ish readable).
_KIND_META: dict[str, tuple[str, str]] = {
    "error": ("ошибка", "#b91c1c"),
    "outcome": ("итог", "#0f766e"),
    "paper": ("сделка", "#1d4ed8"),
    "explore": ("исследование", "#a16207"),
    "analysis": ("анализ", "#0f766e"),
    "learn": ("обучение", "#7c3aed"),
    "wait": ("горизонт", "#64748b"),
    "hold": ("ожидание", "#64748b"),
    "skip": ("пропуск", "#94a3b8"),
    "sync": ("синхронизация", "#475569"),
    "info": ("инфо", "#334155"),
}

_BODY_HIGHLIGHTS: tuple[tuple[str, str], ...] = (
    ("неудача", "#b91c1c"),
    ("удача", "#15803d"),
    ("убыток", "#b91c1c"),
    ("прибыль", "#15803d"),
    ("ПРОДАЖА", "#b91c1c"),
    ("ПОКУПКА", "#15803d"),
    ("ДЕРЖАТЬ", "#64748b"),
    ("горизонт импульса", "#a16207"),
)


def _highlight_market_body(escaped: str) -> str:
    """Wrap known tokens in colored spans (input already HTML-escaped)."""
    out = escaped
    for token, color in _BODY_HIGHLIGHTS:
        if token not in out:
            continue
        out = out.replace(
            token,
            f'<b><span style="color:{color}">{token}</span></b>',
        )
    # Soft-emphasize burst/break numbers in analysis lines.
    out = re.sub(
        r"(burst=)([+\-]?\d+\.?\d*)",
        r'\1<b><span style="color:#a16207">\2</span></b>',
        out,
    )
    out = re.sub(
        r"(break=)([+\-]?\d+\.?\d*)",
        r'\1<b><span style="color:#c2410c">\2</span></b>',
        out,
    )
    return out


def _format_market_line(
    text: str,
    *,
    is_error: bool = False,
    kind: str | None = None,
) -> str:
    """Rich HTML line: colored kind badge + highlighted body."""
    k = (kind or ("error" if is_error else "info")).strip().lower()
    if is_error:
        k = "error"
    badge_ru, color = _KIND_META.get(k, ("инфо", "#334155"))
    # Outcome: green vs red from message text.
    if k == "outcome":
        if "неудача" in text:
            color = "#b91c1c"
        elif "удача" in text:
            color = "#15803d"

    # Avoid double prefix when text already starts with "анализ: …" from format_market_event.
    body = text
    prefix = f"{badge_ru}: "
    if body.startswith(prefix):
        body = body[len(prefix) :]
    elif k == "error" and body.startswith("ошибка: "):
        body = body[len("ошибка: ") :]

    escaped = html.escape(body).replace("\n", "<br>")
    colored_body = _highlight_market_body(escaped)
    badge = f'<b><span style="color:{color}">{html.escape(badge_ru)}</span></b>'
    return f"{badge}: {colored_body}"


def append_market_message(
    main: MainWindow,
    text: str,
    *,
    is_error: bool = False,
    kind: str | None = None,
    persist: bool = True,
    reason: str | None = None,
    bar_ts: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    extras: dict | None = None,
) -> None:
    kind_eff = (kind or ("error" if is_error else "info")).strip() or "info"
    root = _project_root(main)
    if persist and root:
        try:
            from eurika.ml.market_journal import append_market_journal

            append_market_journal(
                root,
                text,
                kind=kind_eff,
                reason=reason,
                bar_ts=bar_ts,
                symbol=symbol,
                market=market,
                extras=extras,
            )
        except Exception:
            pass
    view = getattr(main, "market_transcript", None)
    if view is None:
        view = getattr(main, "chat_transcript", None)
    if view is None:
        return
    view.append(_format_market_line(text, is_error=is_error, kind=kind))
    bar = view.verticalScrollBar()
    if bar:
        bar.setValue(bar.maximum())


def show_session_digest(main: MainWindow, *, mark_seen: bool = True) -> None:
    """«Пока тебя не было» — в ленту Market (без засорения journal).

    Once per app process/root. Skips empty «just opened» re-runs after mark_seen.
    """
    root = _project_root(main)
    if not root:
        return
    root_key = str(root)
    shown: set[str] = getattr(main, "_session_digest_shown_roots", None) or set()
    if root_key in shown:
        return
    try:
        from eurika.ml.session_digest import (
            build_session_digest,
            format_session_digest,
            mark_session_seen,
        )

        # Compute first; only stamp seen after a meaningful show.
        data = build_session_digest(root, mark_seen=False)
        ago_ms = int(data.get("now_ms") or 0) - int(data.get("since_ms") or 0)
        trivial = (
            data.get("since_kind") == "last_seen"
            and ago_ms < 120_000
            and int(data.get("filled") or 0) == 0
            and int(data.get("cancelled") or 0) == 0
        )
        if trivial:
            # Prefs/Live re-entry within 2 min — don't spam empty digest.
            return
        text = format_session_digest(data)
    except Exception as exc:
        append_market_message(main, f"digest: {exc}", is_error=True, persist=False)
        return
    shown = set(shown)
    shown.add(root_key)
    main._session_digest_shown_roots = shown
    for line in text.splitlines():
        append_market_message(main, line, kind="info", persist=False)
    if mark_seen:
        try:
            mark_session_seen(root, equity_usdt=data.get("equity_usdt"))
        except Exception:
            pass
    update_market_status_label(main)


def clear_market_log(main: MainWindow) -> None:
    if hasattr(main, "market_transcript") and main.market_transcript is not None:
        main.market_transcript.clear()
    # File journal is append-only; this info line marks a UI clear.
    append_market_message(main, "журнал очищен", kind="info")


def update_market_status_label(main: MainWindow, extra: str = "") -> None:
    if not hasattr(main, "market_status_label"):
        return
    live = bool(getattr(main, "market_live_check", None) and main.market_live_check.isChecked())
    candle = "15m"
    horizon = 2
    if hasattr(main, "market_candle_combo"):
        candle = main.market_candle_combo.currentText().strip() or "15m"
    if hasattr(main, "market_horizon_spin"):
        horizon = int(main.market_horizon_spin.value())
    mode = "LIVE бумага" if live else "выкл"
    explore = bool(getattr(main, "market_explore_check", None) and main.market_explore_check.isChecked())
    cap = int(main.market_explore_cap_spin.value()) if hasattr(main, "market_explore_cap_spin") else 80
    mkt = _market_mode_label(_market_mode_from_ui(main))
    spot_n = len(spot_symbols_from_ui(main))
    fut_n = len(futures_symbols_from_ui(main))
    scope = f"spot={spot_n} fut={fut_n}"
    explore_bits = "исслед.выкл"
    if explore:
        root = _project_root(main)
        live_n: int | None = None
        if root:
            try:
                from eurika.ml.live_paper import count_live_labels, resolve_explore_enabled

                gate = resolve_explore_enabled(root, explore=True, explore_live_cap=cap)
                live_n = gate.get("live")
                total_n = gate.get("total_live")
                if gate.get("reason") == "cap":
                    explore_bits = f"исслед.off({live_n}≥{cap})"
                elif cap <= 0:
                    explore_bits = f"исслед.вкл(live={live_n},∞)"
                else:
                    explore_bits = f"исслед.вкл(live={live_n}/{cap}"
                    if total_n is not None and int(total_n) != int(live_n or 0):
                        explore_bits += f", всего={total_n}"
                    explore_bits += ")"
            except Exception:
                explore_bits = f"исслед.вкл(до {cap})" if cap > 0 else "исслед.вкл"
        else:
            explore_bits = f"исслед.вкл(до {cap})" if cap > 0 else "исслед.вкл"
    pnl_bits = ""
    bank_text = "equity=— · маржа — · Δ=—"
    root_pnl = _project_root(main)
    if root_pnl:
        try:
            from eurika.ml.learning_status import market_learning_status

            pnl_st = market_learning_status(root_pnl)
            pnl = (pnl_st.get("pnl") or {}).get("session") or {}
            live_p = (pnl_st.get("pnl") or {}).get("live") or {}
            bank = pnl_st.get("portfolio") or {}
            se = pnl.get("sum_edge")
            eq = bank.get("equity_usdt")
            bits = []
            if isinstance(eq, (int, float)):
                bits.append(f"банк={float(eq):.2f}USDT")
            if isinstance(se, (int, float)):
                bits.append(f"edge сессия={float(se):+.2%} (n={pnl.get('n', 0)})")
            usd = bank.get("session_pnl_usdt")
            if isinstance(usd, (int, float)):
                bits.append(f"Δ={float(usd):+.2f}$")
            if bits:
                pnl_bits = " · " + " · ".join(bits)
            elif live:
                pnl_bits = " · PnL сессия=n/a"

            eq_s = f"{float(eq):.2f}" if isinstance(eq, (int, float)) else "—"
            used = bank.get("margin_used_usdt")
            mx = bank.get("max_margin_usdt")
            if isinstance(used, (int, float)) and isinstance(mx, (int, float)):
                marg_s = f"{float(used):.1f}/{float(mx):.1f}"
            else:
                marg_s = "—"
            dlt = bank.get("session_pnl_usdt")
            dlt_s = f"{float(dlt):+.2f}$" if isinstance(dlt, (int, float)) else "—"
            live_usd = live_p.get("sum_pnl_usdt")
            live_s = f"{float(live_usd):+.2f}$" if isinstance(live_usd, (int, float)) else "—"
            bank_text = f"equity={eq_s} USDT · маржа {marg_s} · Δ={dlt_s} · live PnL$={live_s}"
        except Exception:
            pass
    if hasattr(main, "market_bank_label"):
        main.market_bank_label.setText(bank_text)
    parts = [
        f"{mode} · {mkt} · {scope} {candle} · гор.{horizon} · {explore_bits}{pnl_bits} · без ордеров"
    ]
    if extra:
        parts.append(extra)
    status = " · ".join(parts)
    main.market_status_label.setText(status)
    if hasattr(main, "chat_mode_status_label"):
        short = f"{mode} · {mkt} · {candle}"
        if bank_text.startswith("equity=") and "equity=—" not in bank_text.split(" · ", 1)[0]:
            eq_bit = bank_text.split(" · ", 1)[0]
            short = f"{short} · {eq_bit}"
        elif "банк=" in pnl_bits:
            # fallback from pnl_bits fragment
            for bit in pnl_bits.split(" · "):
                if bit.startswith("банк="):
                    short = f"{short} · {bit}"
                    break
        if extra:
            short = f"{short} · {extra}"
        main.chat_mode_status_label.setText(short)


def drop_market_orphans(main: MainWindow) -> None:
    """Hard-drop open paper outside current Spot/Futures lists."""
    root = _project_root(main)
    if not root:
        append_market_message(main, "сначала укажите корень проекта", is_error=True)
        return
    try:
        from eurika.ml.live_paper import drop_orphan_opens

        out = drop_orphan_opens(
            root,
            spot_symbols=spot_symbols_from_ui(main),
            futures_symbols=futures_symbols_from_ui(main),
            markets=_market_mode_from_ui(main),
        )
        dropped = out.get("dropped_positions") or []
        if not dropped:
            append_market_message(main, "сирот нет — все opens в текущих списках")
        else:
            bits = [
                f"{d.get('symbol')}[{'fut' if d.get('market') == 'futures' else 'spot'}]"
                for d in dropped
            ]
            append_market_message(
                main,
                f"сброшено сирот: {out.get('dropped')} ({', '.join(bits)}); "
                f"осталось opens={out.get('kept')}",
            )
        update_market_status_label(main)
        try:
            from . import ml_handlers

            ml_handlers.refresh_market_learning(main, append_log=False)
        except Exception:
            pass
    except Exception as exc:
        append_market_message(main, f"сброс сирот: {exc}", is_error=True)

def _persist_ticker_lists(main: MainWindow) -> None:
    root = _project_root(main)
    if not root:
        return
    from eurika.ml.universe import save_ticker_lists

    save_ticker_lists(
        root,
        spot=spot_symbols_from_ui(main),
        futures=futures_symbols_from_ui(main),
    )


def save_market_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    if hasattr(main, "market_live_check"):
        data["market_live_paper"] = bool(main.market_live_check.isChecked())
    if hasattr(main, "market_auto_check"):
        data["market_auto_tick"] = bool(main.market_auto_check.isChecked())
    if hasattr(main, "market_interval_spin"):
        data["market_auto_sec"] = int(main.market_interval_spin.value())
    if hasattr(main, "market_kind_combo"):
        data["market_kind"] = _market_mode_from_ui(main)
    data["market_spot_symbols"] = spot_symbols_from_ui(main)
    data["market_futures_symbols"] = futures_symbols_from_ui(main)
    # Drop legacy keys so old checkbox/symbol do not resurrect.
    data.pop("market_universe_balances", None)
    data.pop("market_symbol", None)
    if hasattr(main, "market_micro_train_check"):
        data["market_micro_train"] = bool(main.market_micro_train_check.isChecked())
    if hasattr(main, "market_explore_check"):
        data["market_explore"] = bool(main.market_explore_check.isChecked())
    if hasattr(main, "market_explore_cap_spin"):
        data["market_explore_live_cap"] = int(main.market_explore_cap_spin.value())
    if hasattr(main, "market_candle_combo"):
        data["market_candle"] = main.market_candle_combo.currentText().strip() or "15m"
    if hasattr(main, "market_horizon_spin"):
        data["market_horizon"] = int(main.market_horizon_spin.value())
    if hasattr(main, "market_exec_1m_check"):
        data["market_exec_1m"] = bool(main.market_exec_1m_check.isChecked())
    if hasattr(main, "market_tp_spin"):
        data["market_tp_pct"] = float(main.market_tp_spin.value())
    if hasattr(main, "market_sl_spin"):
        data["market_sl_pct"] = float(main.market_sl_spin.value())
    if hasattr(main, "market_trail_spin"):
        data["market_trail_pct"] = float(main.market_trail_spin.value())
    main._settings.save(data)
    _persist_ticker_lists(main)


def load_market_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    root = _project_root(main)
    spot: list[str] = []
    fut: list[str] = []
    if root:
        from eurika.ml.universe import load_ticker_lists

        disk = load_ticker_lists(root)
        spot = list(disk.get("spot") or [])
        fut = list(disk.get("futures") or [])
    if not spot:
        spot = [str(s).strip().upper() for s in (data.get("market_spot_symbols") or []) if str(s).strip()]
    if not fut:
        fut = [str(s).strip().upper() for s in (data.get("market_futures_symbols") or []) if str(s).strip()]
    # Migrate legacy single symbol
    if not spot:
        legacy = str(data.get("market_symbol") or "").strip().upper()
        if legacy:
            spot = [legacy]
    if not spot:
        spot = [_DEFAULT_SYMBOL]

    _set_list_symbols(getattr(main, "market_spot_list", None), spot)
    _set_list_symbols(getattr(main, "market_futures_list", None), fut)

    if hasattr(main, "market_kind_combo"):
        kind = str(data.get("market_kind") or "spot").strip().lower()
        label = "Spot"
        if kind in ("futures", "fut"):
            label = "Futures"
        elif kind in ("both", "all"):
            label = "Both"
        idx = main.market_kind_combo.findText(label)
        main.market_kind_combo.blockSignals(True)
        main.market_kind_combo.setCurrentIndex(idx if idx >= 0 else 0)
        main.market_kind_combo.blockSignals(False)
    if hasattr(main, "market_candle_combo"):
        candle = str(data.get("market_candle") or "15m")
        idx = main.market_candle_combo.findText(candle)
        main.market_candle_combo.blockSignals(True)
        main.market_candle_combo.setCurrentIndex(idx if idx >= 0 else 0)
        main.market_candle_combo.blockSignals(False)
    if hasattr(main, "market_horizon_spin"):
        main.market_horizon_spin.blockSignals(True)
        main.market_horizon_spin.setValue(int(data.get("market_horizon") or 2))
        main.market_horizon_spin.blockSignals(False)
    if hasattr(main, "market_exec_1m_check"):
        main.market_exec_1m_check.blockSignals(True)
        main.market_exec_1m_check.setChecked(bool(data.get("market_exec_1m", True)))
        main.market_exec_1m_check.blockSignals(False)
    if hasattr(main, "market_tp_spin"):
        main.market_tp_spin.blockSignals(True)
        main.market_tp_spin.setValue(float(data.get("market_tp_pct", 1.0)))
        main.market_tp_spin.blockSignals(False)
    if hasattr(main, "market_sl_spin"):
        main.market_sl_spin.blockSignals(True)
        main.market_sl_spin.setValue(float(data.get("market_sl_pct", 1.0)))
        main.market_sl_spin.blockSignals(False)
    if hasattr(main, "market_trail_spin"):
        main.market_trail_spin.blockSignals(True)
        main.market_trail_spin.setValue(float(data.get("market_trail_pct", 0.8)))
        main.market_trail_spin.blockSignals(False)
    if hasattr(main, "market_interval_spin"):
        sec = int(data.get("market_auto_sec") or 60)
        main.market_interval_spin.setValue(max(15, min(3600, sec)))
    if hasattr(main, "market_micro_train_check"):
        main.market_micro_train_check.blockSignals(True)
        main.market_micro_train_check.setChecked(bool(data.get("market_micro_train", True)))
        main.market_micro_train_check.blockSignals(False)
    if hasattr(main, "market_explore_check"):
        main.market_explore_check.blockSignals(True)
        main.market_explore_check.setChecked(bool(data.get("market_explore", True)))
        main.market_explore_check.blockSignals(False)
    if hasattr(main, "market_explore_cap_spin"):
        main.market_explore_cap_spin.blockSignals(True)
        main.market_explore_cap_spin.setValue(int(data.get("market_explore_live_cap", 80)))
        main.market_explore_cap_spin.blockSignals(False)
    if hasattr(main, "market_auto_check"):
        main.market_auto_check.blockSignals(True)
        main.market_auto_check.setChecked(bool(data.get("market_auto_tick", False)))
        main.market_auto_check.blockSignals(False)
    if hasattr(main, "market_live_check"):
        main.market_live_check.blockSignals(True)
        main.market_live_check.setChecked(bool(data.get("market_live_paper", False)))
        main.market_live_check.blockSignals(False)
    update_market_status_label(main)
    _sync_timer(main)
    # Defer digest until transcript widget is ready / prefs applied (once).
    if getattr(main, "_session_digest_scheduled", False):
        return
    main._session_digest_scheduled = True
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(600, lambda: show_session_digest(main, mark_seen=True))
    except Exception:
        show_session_digest(main, mark_seen=True)


def on_market_live_toggled(main: MainWindow, checked: bool) -> None:
    save_market_preferences(main)
    update_market_status_label(main)
    if checked:
        root = _project_root(main)
        if root:
            try:
                from eurika.ml.learning_status import mark_live_session_start

                mark_live_session_start(root)
            except Exception:
                pass
        if hasattr(main, "chat_inner_tabs") and hasattr(main, "chat_market_subtab_index"):
            main.chat_inner_tabs.setCurrentIndex(main.chat_market_subtab_index)
        append_market_message(
            main,
            "Live paper включён — тикеры Spot/Futures из списков; "
            "исследование при HOLD копит метки (без ордеров); PnL-сессия с этого момента",
            kind="info",
        )
        run_market_tick(main)
    else:
        append_market_message(main, "Live paper выключен", kind="info")
        _stop_timer(main)
    _sync_timer(main)


def on_market_auto_toggled(main: MainWindow, _checked: bool = False) -> None:
    save_market_preferences(main)
    _sync_timer(main)


def on_market_prefs_changed(main: MainWindow) -> None:
    save_market_preferences(main)
    update_market_status_label(main)
    _sync_timer(main)


def reset_explore_counter(main: MainWindow) -> None:
    """Reset explore session counter (baseline); keep paper history and weights."""
    root = _project_root(main)
    if not root:
        append_market_message(main, "сначала укажите корень проекта", is_error=True)
        return
    try:
        from eurika.ml.live_paper import reset_explore_counter as _reset

        out = _reset(root)
    except Exception as exc:
        append_market_message(main, f"сброс счётчика не удался: {exc}", is_error=True)
        return
    append_market_message(
        main,
        (
            f"счётчик исследования сброшен: сессия=0 "
            f"(baseline={out.get('baseline')}, всего live={out.get('total_live')}) — "
            f"история paper не тронута"
        ),
        kind="info",
    )
    update_market_status_label(main)


def add_spot_symbol(main: MainWindow) -> None:
    edit = getattr(main, "market_spot_edit", None)
    raw = (edit.text() if edit is not None else "").strip().upper()
    if not raw:
        append_market_message(main, "укажите spot-символ", is_error=True)
        return
    if not raw.isalnum():
        append_market_message(main, f"некорректный символ: {raw}", is_error=True)
        return
    current = spot_symbols_from_ui(main)
    if raw in current:
        append_market_message(main, f"spot уже есть: {raw}")
        return
    # Soft probe — allow add even if network fails
    note = ""
    try:
        from eurika.utils.env import load_project_dotenv
        from eurika.ml.universe import default_ticker_probe

        root = _project_root(main)
        if root:
            load_project_dotenv(root)
        if not default_ticker_probe(raw):
            note = " (тикер на spot не подтверждён — добавлен всё равно)"
    except Exception:
        note = " (probe недоступен)"
    current.append(raw)
    _set_list_symbols(getattr(main, "market_spot_list", None), current)
    if edit is not None:
        edit.clear()
    on_market_prefs_changed(main)
    append_market_message(main, f"spot +: {raw}{note}")


def remove_spot_symbol(main: MainWindow) -> None:
    lst = getattr(main, "market_spot_list", None)
    if lst is None or lst.currentRow() < 0:
        append_market_message(main, "выберите spot-тикер для удаления", is_error=True)
        return
    item = lst.currentItem()
    sym = (item.text() if item else "").strip().upper()
    current = [s for s in spot_symbols_from_ui(main) if s != sym]
    _set_list_symbols(lst, current)
    on_market_prefs_changed(main)
    append_market_message(main, f"spot −: {sym or '?'}")


def add_futures_symbol(main: MainWindow) -> None:
    edit = getattr(main, "market_futures_edit", None)
    raw = (edit.text() if edit is not None else "").strip().upper()
    if not raw:
        append_market_message(main, "укажите futures-символ", is_error=True)
        return
    if not raw.isalnum():
        append_market_message(main, f"некорректный символ: {raw}", is_error=True)
        return
    current = futures_symbols_from_ui(main)
    if raw in current:
        append_market_message(main, f"futures уже есть: {raw}")
        return
    try:
        from eurika.utils.env import load_project_dotenv
        from eurika.ml.universe import default_futures_ticker_probe

        root = _project_root(main)
        if root:
            load_project_dotenv(root)
        if not default_futures_ticker_probe(raw):
            append_market_message(
                main,
                f"futures {raw}: нет на fapi (или сеть недоступна) — не добавлен",
                is_error=True,
            )
            return
    except Exception as exc:
        append_market_message(main, f"futures probe: {exc}", is_error=True)
        return
    current.append(raw)
    _set_list_symbols(getattr(main, "market_futures_list", None), current)
    if edit is not None:
        edit.clear()
    on_market_prefs_changed(main)
    append_market_message(main, f"futures +: {raw}")


def remove_futures_symbol(main: MainWindow) -> None:
    lst = getattr(main, "market_futures_list", None)
    if lst is None or lst.currentRow() < 0:
        append_market_message(main, "выберите futures-тикер для удаления", is_error=True)
        return
    item = lst.currentItem()
    sym = (item.text() if item else "").strip().upper()
    current = [s for s in futures_symbols_from_ui(main) if s != sym]
    _set_list_symbols(lst, current)
    on_market_prefs_changed(main)
    append_market_message(main, f"futures −: {sym or '?'}")


def fill_spot_from_balances(main: MainWindow) -> None:
    root = _project_root(main)
    if not root:
        append_market_message(main, "сначала укажите корень проекта", is_error=True)
        return
    try:
        from eurika.utils.env import load_project_dotenv
        from eurika.ml.universe import symbols_from_balances

        load_project_dotenv(root)
        uni = symbols_from_balances(fallback=_DEFAULT_SYMBOL, project_root=root)
        symbols = list(uni.get("symbols") or [_DEFAULT_SYMBOL])
        _set_list_symbols(getattr(main, "market_spot_list", None), symbols)
        on_market_prefs_changed(main)
        src = uni.get("source") or "balances"
        msg = f"spot заполнен из {src}: {', '.join(symbols)} ({len(symbols)})"
        if uni.get("error") or uni.get("stale"):
            msg += f" — {uni.get('error') or 'stale'}"
        append_market_message(main, msg, is_error=bool(uni.get("error") and uni.get("source") == "fallback"))
    except Exception as exc:
        append_market_message(main, f"заполнение spot: {exc}", is_error=True)


def _stop_timer(main: MainWindow) -> None:
    timer = getattr(main, "_market_timer", None)
    if timer is not None:
        timer.stop()


def _sync_timer(main: MainWindow) -> None:
    live = bool(getattr(main, "market_live_check", None) and main.market_live_check.isChecked())
    auto = bool(getattr(main, "market_auto_check", None) and main.market_auto_check.isChecked())
    if not hasattr(main, "_market_timer") or main._market_timer is None:
        main._market_timer = QTimer(main)
        main._market_timer.timeout.connect(lambda: run_market_tick(main, from_timer=True))
    if live and auto:
        sec = int(main.market_interval_spin.value()) if hasattr(main, "market_interval_spin") else 60
        main._market_timer.start(max(15, sec) * 1000)
    else:
        main._market_timer.stop()


def run_market_tick(main: MainWindow, *, from_timer: bool = False) -> None:
    """Manual or auto tick."""
    if getattr(main, "_is_closing", False):
        return
    if getattr(main, "_market_tick_busy", False):
        return
    if from_timer and not (hasattr(main, "market_live_check") and main.market_live_check.isChecked()):
        return
    root = _project_root(main)
    if not root:
        append_market_message(main, "сначала укажите корень проекта", is_error=True)
        return

    candle = "15m"
    if hasattr(main, "market_candle_combo"):
        candle = main.market_candle_combo.currentText().strip() or "15m"
    horizon = 2
    if hasattr(main, "market_horizon_spin"):
        horizon = int(main.market_horizon_spin.value())

    spot = spot_symbols_from_ui(main)
    fut = futures_symbols_from_ui(main)
    mode = _market_mode_from_ui(main)
    if mode in ("spot", "both") and not spot:
        append_market_message(main, "spot-список пуст — добавьте тикер или «Заполнить spot»", is_error=True)
        return
    if mode in ("futures", "both") and not fut:
        append_market_message(main, "futures-список пуст — добавьте тикер (+)", is_error=True)
        return

    exec_1m = bool(getattr(main, "market_exec_1m_check", None) and main.market_exec_1m_check.isChecked())
    # UI spins are percent (0.3 = 0.3%); live_paper expects fraction (0.003).
    tp_pct = 0.0
    sl_pct = 0.0
    trail_pct = 0.0
    if exec_1m:
        if hasattr(main, "market_tp_spin"):
            tp_pct = max(0.0, float(main.market_tp_spin.value()) / 100.0)
        if hasattr(main, "market_sl_spin"):
            sl_pct = max(0.0, float(main.market_sl_spin.value()) / 100.0)
        if hasattr(main, "market_trail_spin"):
            trail_pct = max(0.0, float(main.market_trail_spin.value()) / 100.0)
    opts: dict[str, Any] = {
        "interval": candle,
        "horizon": horizon,
        "micro_train": bool(getattr(main, "market_micro_train_check", None) and main.market_micro_train_check.isChecked()),
        "explore": bool(getattr(main, "market_explore_check", None) and main.market_explore_check.isChecked()),
        "explore_when_idle": True,
        "explore_live_cap": (
            int(main.market_explore_cap_spin.value())
            if hasattr(main, "market_explore_cap_spin")
            else 80
        ),
        "sync_limit": 100,
        "max_keep": 120,
        "market_mode": mode,
        "spot_symbols": spot,
        "futures_symbols": fut,
        "fallback_symbol": (spot[0] if spot else (fut[0] if fut else _DEFAULT_SYMBOL)),
        "exec_interval": "1m" if exec_1m else "",
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "trail_pct": trail_pct,
    }
    main._market_tick_busy = True
    if hasattr(main, "market_tick_btn"):
        main.market_tick_btn.setEnabled(False)
    update_market_status_label(main, "тик…")

    worker = MarketTickWorker(root, opts, parent=main)
    main._market_tick_worker = worker

    def _on_ok(result: dict[str, Any]) -> None:
        from eurika.ml.live_paper import action_ru, format_market_event

        if getattr(main, "_is_closing", False):
            return
        main._market_tick_busy = False
        if hasattr(main, "market_tick_btn"):
            main.market_tick_btn.setEnabled(True)
        for ev in result.get("events") or []:
            ek = str(ev.get("kind") or "info")
            from eurika.ml.market_journal import journal_fields_from_event

            fields = journal_fields_from_event(ev if isinstance(ev, dict) else {})
            append_market_message(
                main,
                format_market_event(ev),
                is_error=(ek == "error"),
                kind=ek,
                reason=fields.pop("reason", None),
                bar_ts=fields.pop("bar_ts", None),
                symbol=fields.pop("symbol", None),
                market=fields.pop("market", None),
                extras=fields or None,
            )
        sug = result.get("suggestion") or {}
        uni = result.get("universe") or {}
        uni_bits = ""
        spot_u = uni.get("symbols") or []
        fut_u = uni.get("futures_symbols") or []
        if spot_u or fut_u:
            parts = []
            if spot_u:
                parts.append("s=" + ",".join(spot_u[:3]) + ("…" if len(spot_u) > 3 else ""))
            if fut_u:
                parts.append("f=" + ",".join(fut_u[:3]) + ("…" if len(fut_u) > 3 else ""))
            uni_bits = " ".join(parts) + " "
        mk = "+".join(result.get("markets") or [])
        if mk:
            uni_bits = f"{mk} {uni_bits}"
        orphans = result.get("orphans") or []
        orphan_bits = f" сироты={len(orphans)}" if orphans else ""
        extra = (
            f"{uni_bits}открыто={result.get('opens')} закрыто={result.get('resolved')}"
            f"{orphan_bits} "
            f"далее={action_ru(str(sug.get('action') or 'HOLD'))}"
            f"@{sug.get('entry')}"
        )
        update_market_status_label(main, extra)
        try:
            from . import ml_handlers

            ml_handlers.refresh_market_learning(main, append_log=False)
        except Exception:
            pass
        if not result.get("ok") and result.get("error"):
            append_market_message(main, str(result.get("error")), is_error=True)

    def _on_fail(err: str) -> None:
        if getattr(main, "_is_closing", False):
            return
        main._market_tick_busy = False
        if hasattr(main, "market_tick_btn"):
            main.market_tick_btn.setEnabled(True)
        update_market_status_label(main, "ошибка")
        append_market_message(main, err, is_error=True)

    def _on_thread_finished() -> None:
        if getattr(main, "_market_tick_worker", None) is worker:
            main._market_tick_worker = None
        if not getattr(main, "_is_closing", False):
            main._market_tick_busy = False
            if hasattr(main, "market_tick_btn"):
                main.market_tick_btn.setEnabled(True)
        worker.deleteLater()

    worker.finished_ok.connect(_on_ok)
    worker.failed.connect(_on_fail)
    worker.finished.connect(_on_thread_finished)
    worker.start()
