"""Qt hook for opt-in holistic portfolio agent on the Market tab.

Paper-only: trade + earn share one cash pool. Timer runs while the checkbox is on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, QTimer, Signal

if TYPE_CHECKING:
    from ..main_window import MainWindow

_POLL_MS = 60_000


class MarketPortfolioWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, project_root: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._root = project_root

    def run(self) -> None:
        try:
            from eurika.ml.portfolio_agent import run_portfolio_cycle

            self.finished_ok.emit(run_portfolio_cycle(self._root))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def sync_timer(main: MainWindow) -> None:
    enabled = bool(
        getattr(main, "market_portfolio_check", None)
        and main.market_portfolio_check.isChecked()
    )
    timer = getattr(main, "_market_portfolio_timer", None)
    if not enabled:
        if timer is not None and timer.isActive():
            timer.stop()
        return
    if timer is None:
        timer = QTimer(main)
        timer.timeout.connect(lambda: maybe_run(main))
        main._market_portfolio_timer = timer
    if not timer.isActive():
        timer.start(_POLL_MS)
    maybe_run(main)


def shutdown(main: MainWindow) -> None:
    timer = getattr(main, "_market_portfolio_timer", None)
    if timer is not None and timer.isActive():
        timer.stop()


def _focus_market_feed(main: MainWindow) -> None:
    from .chat_handlers import focus_market_mode

    focus_market_mode(main)


def _set_portfolio_btn_busy(main: MainWindow, busy: bool) -> None:
    btn = getattr(main, "market_portfolio_once_btn", None)
    if btn is not None:
        btn.setEnabled(not busy)


def run_once(main: MainWindow, *, force: bool = True) -> None:
    """Manual one-shot from Market button (ignores due stamp when force)."""
    from . import market_handlers as mh

    _focus_market_feed(main)
    if getattr(main, "_is_closing", False):
        return
    if getattr(main, "_market_portfolio_worker", None) is not None:
        mh.append_market_message(
            main,
            "Portfolio агент: цикл уже выполняется — дождитесь завершения",
            kind="portfolio_agent",
            persist=False,
        )
        return
    root = mh._project_root(main)
    if not root:
        mh.append_market_message(
            main,
            "Portfolio агент: не задан корень Market — откройте проект Eurika",
            is_error=True,
            kind="portfolio_agent",
            persist=False,
        )
        return
    from eurika.agent.cursor_judge import cursor_key_status

    if not cursor_key_status(root).get("api_key_set"):
        mh.append_market_message(
            main,
            "Portfolio агент: нет CURSOR_API_KEY — цикл пропущен",
            kind="portfolio_agent",
            persist=False,
        )
        return
    if not force:
        from eurika.ml.portfolio_agent import is_due

        if not is_due(root):
            return
    mh.append_market_message(
        main,
        "Portfolio агент: запуск цикла (futures paper, LLM)…",
        kind="portfolio_agent",
        persist=False,
    )
    mh.update_market_status_label(main, "portfolio…")
    _start_worker(main, root)


def maybe_run(main: MainWindow) -> None:
    if getattr(main, "_is_closing", False):
        return
    if not (
        hasattr(main, "market_portfolio_check") and main.market_portfolio_check.isChecked()
    ):
        return
    if getattr(main, "_market_portfolio_worker", None) is not None:
        return
    from . import market_handlers as mh

    root = mh._project_root(main)
    if not root:
        return
    from eurika.ml.portfolio_agent import is_due

    if not is_due(root):
        return
    from eurika.agent.cursor_judge import cursor_key_status

    if not cursor_key_status(root).get("api_key_set"):
        if not getattr(main, "_market_portfolio_warned_no_key", False):
            main._market_portfolio_warned_no_key = True
            mh.append_market_message(
                main,
                "Portfolio агент: нет CURSOR_API_KEY — цикл пропущен",
                kind="info",
            )
        return
    _start_worker(main, root)


def _start_worker(main: MainWindow, root: str) -> None:
    from . import market_handlers as mh

    _set_portfolio_btn_busy(main, True)
    worker = MarketPortfolioWorker(root, parent=main)
    main._market_portfolio_worker = worker

    def _on_ok(result: dict[str, Any]) -> None:
        if getattr(main, "_is_closing", False):
            return
        digest = str(result.get("digest") or "").strip()
        if not digest:
            try:
                from eurika.ml.portfolio_agent import format_portfolio_digest

                digest = format_portfolio_digest(
                    mh._project_root(main) or "",
                    cycle=result,
                )
            except Exception:
                body = str(result.get("body") or "").strip()
                head = body.split("\n")[0][:200] if body else "цикл завершён"
                digest = (
                    f"Portfolio агент: {head} "
                    f"[eq={result.get('holistic_equity_usdt')} act={result.get('actions_n')} "
                    f"ok={result.get('ok')}]"
                )
        mh.append_market_message(
            main,
            digest,
            is_error=not bool(result.get("ok")),
            kind="portfolio_agent",
            persist=False,
        )

    def _on_fail(err: str) -> None:
        if getattr(main, "_is_closing", False):
            return
        mh.append_market_message(
            main,
            f"Portfolio агент: {err}",
            is_error=True,
            kind="portfolio_agent",
            persist=False,
        )

    def _on_finished() -> None:
        _set_portfolio_btn_busy(main, False)
        if not getattr(main, "_is_closing", False):
            mh.update_market_status_label(main)
        if getattr(main, "_market_portfolio_worker", None) is worker:
            main._market_portfolio_worker = None
        worker.deleteLater()

    worker.finished_ok.connect(_on_ok)
    worker.failed.connect(_on_fail)
    worker.finished.connect(_on_finished)
    worker.start()
