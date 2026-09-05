"""Qt hook for opt-in hourly Cursor critique on the Market tab.

Does not open paper trades. Timer only runs while the checkbox is on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, QTimer, Signal

if TYPE_CHECKING:
    from ..main_window import MainWindow

_POLL_MS = 60_000


class MarketLlmLearnWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, project_root: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._root = project_root

    def run(self) -> None:
        try:
            from eurika.ml.cursor_hourly import run_hourly_critique

            self.finished_ok.emit(run_hourly_critique(self._root))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def sync_timer(main: MainWindow) -> None:
    """Start/stop the hourly poll from the Market checkbox."""
    enabled = bool(
        getattr(main, "market_llm_learn_check", None)
        and main.market_llm_learn_check.isChecked()
    )
    timer = getattr(main, "_market_llm_timer", None)
    if not enabled:
        if timer is not None and timer.isActive():
            timer.stop()
        return
    if timer is None:
        timer = QTimer(main)
        timer.timeout.connect(lambda: maybe_run(main))
        main._market_llm_timer = timer
    if not timer.isActive():
        timer.start(_POLL_MS)
    maybe_run(main)


def shutdown(main: MainWindow) -> None:
    timer = getattr(main, "_market_llm_timer", None)
    if timer is not None and timer.isActive():
        timer.stop()


def maybe_run(main: MainWindow) -> None:
    if getattr(main, "_is_closing", False):
        return
    if not (
        hasattr(main, "market_llm_learn_check") and main.market_llm_learn_check.isChecked()
    ):
        return
    if getattr(main, "_market_llm_worker", None) is not None:
        return
    from . import market_handlers as mh

    root = mh._project_root(main)
    if not root:
        return
    mh._persist_analysis_prefs(main)
    from eurika.ml.cursor_hourly import is_due

    if not is_due(root):
        return
    from eurika.agent.cursor_judge import cursor_key_status

    if not cursor_key_status(root).get("api_key_set"):
        if not getattr(main, "_market_llm_warned_no_key", False):
            main._market_llm_warned_no_key = True
            mh.append_market_message(
                main,
                "LLM обучение: нет CURSOR_API_KEY — критика часа пропущена",
                kind="info",
            )
        return
    worker = MarketLlmLearnWorker(root, parent=main)
    main._market_llm_worker = worker

    def _on_ok(result: dict[str, Any]) -> None:
        if getattr(main, "_is_closing", False):
            return
        if result.get("skipped"):
            return
        text = str(result.get("message") or result.get("error") or "").strip()
        if not text:
            return
        mh.append_market_message(
            main,
            text,
            is_error=not bool(result.get("ok")),
            kind=str(result.get("kind") or "cursor_hour"),
            persist=not bool(result.get("persisted")),
        )

    def _on_fail(err: str) -> None:
        if getattr(main, "_is_closing", False):
            return
        mh.append_market_message(main, f"LLM обучение: {err}", is_error=True)

    def _on_finished() -> None:
        if getattr(main, "_market_llm_worker", None) is worker:
            main._market_llm_worker = None
        worker.deleteLater()

    worker.finished_ok.connect(_on_ok)
    worker.failed.connect(_on_fail)
    worker.finished.connect(_on_finished)
    worker.start()
