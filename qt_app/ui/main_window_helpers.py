"""Helpers and widgets for Eurika Qt main window. Reduces main_window.py size (ROADMAP 3.1-arch.3)."""
from __future__ import annotations

import os
import re
from typing import Any

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget

_ANSI_STRIP_RE = re.compile(
    '\\x1b\\[[0-?]*[ -/]*[@-~]|\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)|'
    '\\x1b[PX^_][^\\x1b]*\\x1b\\\\',
    re.DOTALL,
)
_OLLAMA_PULL_PCT_RE = re.compile(r'(\d+)\s*%')
_OLLAMA_PULL_MB_GB_RE = re.compile(r'(\d+)\s*MB\s*/\s*([\d.]+)\s*GB')
_TUI_COMMANDS = frozenset(('htop', 'top', 'vim', 'vi', 'nano', 'less', 'more', 'watch', 'mc'))


def create_graph_page(view: Any, explain_callback: Any) -> Any:
    """Create QWebEnginePage that intercepts eurika:explain/ for double-click Explain."""
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage

        class GraphPage(QWebEnginePage):
            def __init__(self, parent: Any, on_explain: Any) -> None:
                super().__init__(parent)
                self._on_explain = on_explain

            def acceptNavigationRequest(
                self, url: Any, _typ: int, _is_main_frame: bool
            ) -> bool:
                u = url.url() if hasattr(url, 'url') else str(url)
                if u.startswith('eurika:explain/'):
                    from urllib.parse import unquote

                    mod = unquote(u.split('/', 1)[1] or '')
                    if mod and callable(self._on_explain):
                        self._on_explain(mod)
                    return False
                return super().acceptNavigationRequest(url, _typ, _is_main_frame)

        return GraphPage(view, explain_callback)
    except ImportError:
        return None


def default_start_directory() -> str:
    """Start directory for folder picker: home, so user can navigate anywhere."""
    return os.path.expanduser('~') or os.path.abspath('/')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for display in plain text widget."""
    return _ANSI_STRIP_RE.sub('', text)


def parse_ollama_pull_progress(line: str) -> tuple[int, str] | None:
    """Extract progress (0-100) and status text from ollama pull stderr line."""
    pct = None
    m = _OLLAMA_PULL_PCT_RE.search(line)
    if m:
        pct = min(100, max(0, int(m.group(1))))
    m_mb_gb = _OLLAMA_PULL_MB_GB_RE.search(line)
    if pct is None and m_mb_gb:
        mb, gb = (float(m_mb_gb.group(1)), float(m_mb_gb.group(2)))
        if gb > 0:
            pct = min(100, int(100 * mb / (gb * 1024)))
    if pct is None:
        return None
    parts = []
    if m_mb_gb:
        parts.append(f'{m_mb_gb.group(1)} MB / {m_mb_gb.group(2)} GB')
    if sp := re.search(r'([\d.]+)\s*MB/s', line):
        parts.append(f'{sp.group(1)} MB/s')
    if eta := re.search(r'(\d+m\d+s|\d+m|\d+s)', line):
        parts.append(eta.group(1))
    label = ' • '.join(parts) if parts else f'{pct}%'
    return (pct, label)


def is_tui_command(cmd: str) -> bool:
    """Check if command is a known TUI program (requires real PTY)."""
    first = (cmd.strip().split() or [''])[0].lower()
    name = first.split('/')[-1] if first else ''
    return name in _TUI_COMMANDS


class TerminalLineEdit(QLineEdit):
    """QLineEdit with command history (Up/Down arrows)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._history_index = -1
        self._pending_from_history: str | None = None

    def add_to_history(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return
        if self._history and self._history[-1] == cmd:
            return
        self._history.append(cmd)
        if len(self._history) > 500:
            self._history.pop(0)
        self._history_index = -1

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up:
            if not self._history:
                super().keyPressEvent(event)
                return
            if self._history_index < 0:
                self._pending_from_history = self.text()
            self._history_index = min(len(self._history) - 1, self._history_index + 1)
            self.setText(self._history[-(self._history_index + 1)])
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            if self._history_index <= 0:
                self._history_index = -1
                self.setText(self._pending_from_history or '')
                self._pending_from_history = None
                event.accept()
                return
            self._history_index -= 1
            self.setText(self._history[-(self._history_index + 1)])
            event.accept()
            return
        self._history_index = -1
        self._pending_from_history = None
        super().keyPressEvent(event)


class ChatWorker(QThread):
    """Background worker for chat requests to avoid UI freeze."""

    finished_payload = Signal(dict)
    failed = Signal(str)
    system_action_occurred = Signal(str)

    def __init__(
        self,
        *,
        api: Any,
        message: str,
        history: list[dict[str, str]],
        provider: str,
        openai_model: str,
        ollama_model: str,
        timeout_sec: int,
        run_command_with_result: Any = None,
    ) -> None:
        super().__init__()
        self._api = api
        self._message = message
        self._history = history
        self._provider = provider
        self._openai_model = openai_model
        self._ollama_model = ollama_model
        self._timeout_sec = timeout_sec
        self._run_command_with_result = run_command_with_result

    def run(self) -> None:
        def _on_action(cmd: str) -> None:
            self.system_action_occurred.emit(cmd)

        try:
            result = self._api.chat_send(
                message=self._message,
                history=self._history,
                provider=self._provider,
                openai_model=self._openai_model,
                ollama_model=self._ollama_model,
                timeout_sec=self._timeout_sec,
                on_system_action=_on_action,
                run_command_with_result=self._run_command_with_result,
            )
            self.finished_payload.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
