"""Qt opt-in idle self-dev: C.14 propose+sandbox when LLM lease is quiet.

Never applies patches on main. Yields to Market LLM / portfolio / chat workers.
Uses the coding project root (open workspace), not the Market root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread, QTimer, Signal

if TYPE_CHECKING:
    from ..main_window import MainWindow

_POLL_MS = 60_000


class IdleSelfDevWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        project_root: str,
        *,
        market_llm_enabled: bool,
        portfolio_enabled: bool,
        market_root: str = "",
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._root = project_root
        self._market_llm = market_llm_enabled
        self._portfolio = portfolio_enabled
        self._market_root = market_root

    def run(self) -> None:
        try:
            from eurika.orchestration.idle_self_dev import maybe_run

            self.finished_ok.emit(
                maybe_run(
                    self._root,
                    market_llm_enabled=self._market_llm,
                    portfolio_enabled=self._portfolio,
                    market_root=self._market_root or None,
                )
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def _coding_project_root(main: MainWindow) -> str:
    """Open coding workspace — idle self-dev must target this tree, not Market."""
    root = ""
    try:
        root = str(main._settings.get_project_root() or "").strip()
    except Exception:
        root = ""
    if not root and hasattr(main, "root_edit"):
        root = (main.root_edit.text() or "").strip()
    return root


def sync_timer(main: MainWindow) -> None:
    enabled = bool(
        getattr(main, "idle_self_dev_check", None) and main.idle_self_dev_check.isChecked()
    )
    timer = getattr(main, "_idle_self_dev_timer", None)
    if not enabled:
        if timer is not None and timer.isActive():
            timer.stop()
        return
    if timer is None:
        timer = QTimer(main)
        timer.timeout.connect(lambda: maybe_run(main))
        main._idle_self_dev_timer = timer
    if not timer.isActive():
        timer.start(_POLL_MS)
    maybe_run(main)


def shutdown(main: MainWindow) -> None:
    timer = getattr(main, "_idle_self_dev_timer", None)
    if timer is not None and timer.isActive():
        timer.stop()


def _local_busy(main: MainWindow) -> str | None:
    if getattr(main, "_is_closing", False):
        return "closing"
    chat = getattr(main, "_chat_worker", None)
    if chat is not None and hasattr(chat, "isRunning") and chat.isRunning():
        return "chat_busy"
    if getattr(main, "_market_llm_worker", None) is not None:
        return "market_llm_busy"
    if getattr(main, "_market_portfolio_worker", None) is not None:
        return "portfolio_busy"
    if getattr(main, "_idle_self_dev_worker", None) is not None:
        return "self_dev_busy"
    return None


def _echo_chat(main: MainWindow, text: str, *, is_error: bool = False) -> None:
    line = str(text or "").strip()
    if not line:
        return
    from . import chat_handlers

    chat_handlers._append_transcript(
        main,
        chat_handlers._format_chat_line(main, "assistant", line, is_error=is_error),
    )
    chat_handlers._scroll_transcript_to_bottom(main)


def maybe_run(main: MainWindow) -> None:
    if not (
        hasattr(main, "idle_self_dev_check") and main.idle_self_dev_check.isChecked()
    ):
        return
    busy = _local_busy(main)
    if busy:
        return
    from . import market_handlers as mh

    root = _coding_project_root(main)
    if not root:
        return
    market_root = mh._project_root(main)
    market_llm = bool(
        getattr(main, "market_llm_learn_check", None)
        and main.market_llm_learn_check.isChecked()
    )
    portfolio = bool(
        getattr(main, "market_portfolio_check", None)
        and main.market_portfolio_check.isChecked()
    )
    worker = IdleSelfDevWorker(
        root,
        market_llm_enabled=market_llm,
        portfolio_enabled=portfolio,
        market_root=market_root,
        parent=main,
    )
    main._idle_self_dev_worker = worker

    def _on_ok(result: dict[str, Any]) -> None:
        if getattr(main, "_is_closing", False):
            return
        if result.get("skipped"):
            return
        text = str(result.get("message") or "").strip()
        if text and hasattr(main, "status_label"):
            main.status_label.setText(text[:200])
        if int(result.get("approvalsQueued") or 0) > 0:
            from . import chat_handlers

            chat_handlers.maybe_focus_approvals_after_agent(
                main, {"approvalsQueued": result.get("approvalsQueued")}
            )
        try:
            from . import chat_pending_handlers as pending_h

            pending_h.refresh_chat_goal_view(main)
        except Exception:
            pass

    def _on_fail(err: str) -> None:
        if getattr(main, "_is_closing", False):
            return
        msg = f"саморазвитие: {err}"
        if hasattr(main, "status_label"):
            main.status_label.setText(msg[:200])
        _echo_chat(main, msg, is_error=True)

    def _on_finished() -> None:
        if getattr(main, "_idle_self_dev_worker", None) is worker:
            main._idle_self_dev_worker = None
        worker.deleteLater()

    worker.finished_ok.connect(_on_ok)
    worker.failed.connect(_on_fail)
    worker.finished.connect(_on_finished)
    worker.start()
