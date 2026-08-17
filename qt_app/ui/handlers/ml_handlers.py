"""PyTorch / ML sub-tab handlers (Models → ML)."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..main_window import MainWindow


def apply_torch_device_env(device: str) -> str:
    """Set EURIKA_TORCH_DEVICE; returns normalized value (cpu|cuda|mps)."""
    val = (device or "cpu").strip().lower()
    if val not in {"cpu", "cuda", "mps"}:
        val = "cpu"
    os.environ["EURIKA_TORCH_DEVICE"] = val
    return val


def refresh_ml_status(main: MainWindow, *, run_smoke: bool = True, append_log: bool = True) -> dict[str, Any]:
    """Probe torch and update ML sub-tab labels/log."""
    from eurika.ml.torch_runtime import format_torch_block, torch_status

    if hasattr(main, "ml_torch_device_combo"):
        apply_torch_device_env(main.ml_torch_device_combo.currentText())

    st = torch_status(run_smoke_check=run_smoke)
    _apply_status_labels(main, st)
    if append_log and hasattr(main, "ml_torch_output"):
        block = format_torch_block(st).strip()
        main.ml_torch_output.append(block)
        main.ml_torch_output.append("")
        main.ml_torch_output.append(
            "Market ML (paper): Chat → Market для тиков; блок «Market learning» ниже"
        )
        main.ml_torch_output.append("")
    refresh_market_learning(main, append_log=append_log)
    return st


def refresh_market_learning(main: MainWindow, *, append_log: bool = False) -> dict[str, Any]:
    """Update Market learning progress labels from ``.eurika/ml/``."""
    from eurika.ml.learning_status import format_market_learning_block, market_learning_status

    root = str(getattr(main, "_market_root", "") or "").strip()
    if not root:
        from eurika.ml.root import resolve_market_root

        root = str(resolve_market_root())
    try:
        st = market_learning_status(root)
    except Exception as exc:
        st = {"error": f"{type(exc).__name__}: {exc}"}
        _apply_market_learning_error(main, str(st["error"]))
        return st

    _apply_market_learning_labels(main, st)
    if append_log and hasattr(main, "ml_torch_output"):
        main.ml_torch_output.append(format_market_learning_block(st))
        main.ml_torch_output.append("")
    return st


def on_ml_device_changed(main: MainWindow, _text: str = "") -> None:
    """Persist preference and re-probe without flooding the log."""
    if hasattr(main, "ml_torch_device_combo"):
        apply_torch_device_env(main.ml_torch_device_combo.currentText())
    from . import chat_handlers

    chat_handlers.save_chat_preferences(main)
    refresh_ml_status(main, run_smoke=True, append_log=False)


def load_ml_preferences(main: MainWindow) -> None:
    """Restore EURIKA_TORCH_DEVICE from settings / env into ML combo."""
    if not hasattr(main, "ml_torch_device_combo"):
        return
    data = main._settings.load()
    saved = str(data.get("torch_device") or os.environ.get("EURIKA_TORCH_DEVICE") or "cpu").strip().lower()
    if saved not in {"cpu", "cuda", "mps"}:
        saved = "cpu"
    main.ml_torch_device_combo.blockSignals(True)
    main.ml_torch_device_combo.setCurrentText(saved)
    main.ml_torch_device_combo.blockSignals(False)
    apply_torch_device_env(saved)
    refresh_ml_status(main, run_smoke=True, append_log=False)


def _apply_status_labels(main: MainWindow, st: dict[str, Any]) -> None:
    avail = bool(st.get("available"))
    if hasattr(main, "ml_torch_available"):
        main.ml_torch_available.setText("yes" if avail else "no")
    if hasattr(main, "ml_torch_version"):
        main.ml_torch_version.setText(str(st.get("version") or "—") if avail else "—")
    if hasattr(main, "ml_torch_cuda"):
        main.ml_torch_cuda.setText("yes" if st.get("cuda") else "no")
    if hasattr(main, "ml_torch_resolved"):
        main.ml_torch_resolved.setText(str(st.get("device") or "cpu"))
    if hasattr(main, "ml_torch_smoke"):
        smoke = st.get("smoke_ok")
        if smoke is True:
            main.ml_torch_smoke.setText("ok")
        elif smoke is False:
            main.ml_torch_smoke.setText("fail")
        else:
            main.ml_torch_smoke.setText("skip" if not avail else "—")
    if not avail and hasattr(main, "ml_torch_output") and st.get("error"):
        # Keep a quiet status update; detail only if log empty.
        if not main.ml_torch_output.toPlainText().strip():
            main.ml_torch_output.setPlainText(
                f"torch not available: {st.get('error')}\n"
                'install: pip install -e ".[torch]"  # prefer CPU wheel on low VRAM'
            )


def _fmt_acc(val: Any) -> str:
    if isinstance(val, float):
        return f"{val:.3f}"
    return "n/a"


def _apply_market_learning_labels(main: MainWindow, st: dict[str, Any]) -> None:
    paper = st.get("paper") or {}
    live = st.get("live") or {}
    opens = st.get("opens") or {}
    model = st.get("model") or {}
    market = st.get("market") or {}

    if hasattr(main, "ml_market_trades"):
        main.ml_market_trades.setText(
            f"{paper.get('count', 0)} (BUY={paper.get('buys', 0)} SELL={paper.get('sells', 0)})"
        )
    if hasattr(main, "ml_market_accuracy"):
        main.ml_market_accuracy.setText(_fmt_acc(paper.get("accuracy")))
    if hasattr(main, "ml_market_live"):
        live_n = int(live.get("count") or 0)
        live_acc = live.get("accuracy")
        spot = live.get("spot") or {}
        fut = live.get("futures") or {}
        bits = f"spot={spot.get('count', 0)} fut={fut.get('count', 0)}"
        if live_n and isinstance(live_acc, float):
            main.ml_market_live.setText(f"{live_n} (acc={live_acc:.3f}; {bits})")
        else:
            main.ml_market_live.setText(f"{live_n} ({bits})")
    if hasattr(main, "ml_market_pnl"):
        pnl = st.get("pnl") or {}
        all_p = pnl.get("all") or {}
        live_p = pnl.get("live") or {}
        sess = pnl.get("session") or {}
        bank = st.get("portfolio") or {}

        def _e(v: object) -> str:
            return f"{float(v):+.3%}" if isinstance(v, (int, float)) else "n/a"

        eq = bank.get("equity_usdt")
        eq_s = f"{float(eq):.1f}" if isinstance(eq, (int, float)) else "n/a"
        usd = live_p.get("sum_pnl_usdt")
        usd_s = f"{float(usd):+.2f}" if isinstance(usd, (int, float)) else "n/a"
        main.ml_market_pnl.setText(
            f"equity={eq_s} USDT · PnL$={usd_s} · "
            f"edge всего={_e(all_p.get('sum_edge'))} · live={_e(live_p.get('sum_edge'))} · "
            f"сессия={_e(sess.get('sum_edge'))} (n={sess.get('n', 0)})"
        )
    if hasattr(main, "ml_market_opens"):
        n = int(opens.get("count") or 0)
        if n == 0:
            main.ml_market_opens.setText("0")
        else:
            bits = []
            for p in (opens.get("positions") or [])[:3]:
                mk = "fut" if (p.get("market") or "spot") == "futures" else "spot"
                bits.append(f"{p.get('symbol')}[{mk}] {p.get('action')}@{p.get('entry')}")
            extra = f" (+{n - 3})" if n > 3 else ""
            main.ml_market_opens.setText(
                f"{n} (s={opens.get('spot', 0)} f={opens.get('futures', 0)}): "
                + ", ".join(bits)
                + extra
            )
    if hasattr(main, "ml_market_model"):
        if model.get("weights_exist"):
            main.ml_market_model.setText(
                f"samples={model.get('samples')} train_acc={model.get('train_accuracy')} "
                f"device={model.get('device')}"
            )
        else:
            main.ml_market_model.setText("весов нет")
    if hasattr(main, "ml_market_candles"):
        series = market.get("series") or []
        if not series:
            main.ml_market_candles.setText("(пусто)")
        else:
            main.ml_market_candles.setText(
                ", ".join(f"{s.get('symbol')} {s.get('interval')}={s.get('count')}" for s in series[:4])
            )


def _apply_market_learning_error(main: MainWindow, err: str) -> None:
    for name in (
        "ml_market_trades",
        "ml_market_accuracy",
        "ml_market_live",
        "ml_market_pnl",
        "ml_market_opens",
        "ml_market_model",
        "ml_market_candles",
    ):
        if hasattr(main, name):
            getattr(main, name).setText("ошибка")
    if hasattr(main, "ml_market_opens"):
        main.ml_market_opens.setToolTip(err)
