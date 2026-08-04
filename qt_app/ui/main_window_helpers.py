"""Helpers and widgets for Eurika Qt main window. Reduces main_window.py size (ROADMAP 3.1-arch.3)."""
from __future__ import annotations

import os
import re
from typing import Any

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QLineEdit, QTextEdit, QWidget

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
                self,
                url: Any,
                _typ: QWebEnginePage.NavigationType,
                _is_main_frame: bool,
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
    """QLineEdit with command history (Up/Down arrows). Kept for compat/tests."""

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


class TerminalView(QTextEdit):
    """Classic terminal: type after `$ ` in the same pane; Enter runs the command."""

    PROMPT = "$ "
    command_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._history_index = -1
        self._pending_from_history: str | None = None
        self._locked = False
        self._prompt_pos: int | None = None  # index of first char of command (after PROMPT)
        self.setUndoRedoEnabled(False)
        self.ensure_prompt()

    def add_to_history(self, cmd: str) -> None:
        cmd = (cmd or "").strip()
        if not cmd:
            return
        if self._history and self._history[-1] == cmd:
            return
        self._history.append(cmd)
        if len(self._history) > 500:
            self._history.pop(0)
        self._history_index = -1

    def is_input_locked(self) -> bool:
        return self._locked

    def unlock_input(self) -> None:
        self._locked = False
        self.ensure_prompt()

    def current_command(self) -> str:
        if self._prompt_pos is None:
            return ""
        return self.toPlainText()[self._prompt_pos :]

    def move_cursor_to_prompt_end(self) -> None:
        self._move_cursor_to_end()

    def ensure_prompt(self) -> None:
        """Guarantee a trailing `$ ` prompt when idle."""
        if self._locked:
            return
        text = self.toPlainText()
        if self._prompt_pos is not None and self._prompt_pos <= len(text):
            prefix = text[: self._prompt_pos]
            if prefix.endswith(self.PROMPT):
                self._move_cursor_to_end()
                return
        if text.endswith(self.PROMPT):
            self._prompt_pos = len(text)
            self._move_cursor_to_end()
            return
        if text and not text.endswith("\n"):
            text += "\n"
        text += self.PROMPT
        self.setPlainText(text)
        self._prompt_pos = len(text)
        self._move_cursor_to_end()

    def clear_with_prompt(self) -> None:
        self._locked = False
        self._prompt_pos = None
        self.setPlainText("")
        self.ensure_prompt()

    def commit_command_line(self) -> str:
        """Finalize `$ cmd` into scrollback; return the command. Locks input."""
        cmd = self.current_command()
        text = self.toPlainText()
        if not text.endswith("\n"):
            self._insert_at_end("\n")
        self._prompt_pos = None
        self._locked = True
        self._history_index = -1
        self._pending_from_history = None
        return cmd

    def append_output(self, text: str) -> None:
        """Append scrollback text, preserving an idle prompt + partial command."""
        if not text:
            return
        partial = ""
        restore = False
        if not self._locked and self._prompt_pos is not None:
            partial = self.current_command()
            restore = True
            self._strip_prompt_tail()
        body = self.toPlainText()
        if body and not body.endswith("\n") and not text.startswith("\n"):
            self._insert_at_end("\n")
        self._insert_at_end(text)
        if restore and not self._locked:
            self._prompt_pos = None
            self.ensure_prompt()
            if partial:
                self.set_command_text(partial)

    def append(self, text: str) -> None:  # type: ignore[override]
        """QTextEdit.append compatible: new line in scrollback, prompt-safe."""
        raw = str(text) if text is not None else ""
        if raw and not raw.endswith("\n"):
            raw += "\n"
        self.append_output(raw)

    def lock_input(self) -> None:
        """Block prompt editing while a process runs."""
        if self._locked:
            return
        if self._prompt_pos is not None:
            partial = self.current_command()
            if partial.strip():
                if not self.toPlainText().endswith("\n"):
                    self._insert_at_end("\n")
            else:
                self._strip_prompt_tail()
        self._locked = True
        self._prompt_pos = None

    def set_command_text(self, cmd: str) -> None:
        if self._locked or self._prompt_pos is None:
            return
        pos = self._prompt_pos
        text = self.toPlainText()
        self.setPlainText(text[:pos] + (cmd or ""))
        self._prompt_pos = pos
        self._move_cursor_to_end()

    def _strip_prompt_tail(self) -> None:
        if self._prompt_pos is None:
            return
        text = self.toPlainText()
        cut = self._prompt_pos - len(self.PROMPT)
        if cut < 0:
            cut = 0
        self.setPlainText(text[:cut])
        self._prompt_pos = None

    def _insert_at_end(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _move_cursor_to_end(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _clamp_cursor_to_prompt(self) -> None:
        if self._prompt_pos is None:
            return
        cursor = self.textCursor()
        if cursor.position() < self._prompt_pos:
            cursor.setPosition(self._prompt_pos)
            self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._locked:
            event.accept()
            return
        if self._prompt_pos is None:
            self.ensure_prompt()
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cmd = self.current_command().strip()
            if not cmd:
                event.accept()
                return
            self.add_to_history(cmd)
            self.commit_command_line()
            self.command_submitted.emit(cmd)
            event.accept()
            return

        if key == Qt.Key.Key_Up:
            if self._history:
                if self._history_index < 0:
                    self._pending_from_history = self.current_command()
                self._history_index = min(len(self._history) - 1, self._history_index + 1)
                self.set_command_text(self._history[-(self._history_index + 1)])
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            if self._history_index <= 0:
                self._history_index = -1
                self.set_command_text(self._pending_from_history or "")
                self._pending_from_history = None
            else:
                self._history_index -= 1
                self.set_command_text(self._history[-(self._history_index + 1)])
            event.accept()
            return

        if key == Qt.Key.Key_Home and not (mods & Qt.KeyboardModifier.ControlModifier):
            cursor = self.textCursor()
            cursor.setPosition(self._prompt_pos or 0)
            self.setTextCursor(cursor)
            event.accept()
            return

        if key == Qt.Key.Key_Backspace:
            self._clamp_cursor_to_prompt()
            cursor = self.textCursor()
            if cursor.position() <= (self._prompt_pos or 0) and not cursor.hasSelection():
                event.accept()
                return
            if cursor.hasSelection() and cursor.selectionStart() < (self._prompt_pos or 0):
                event.accept()
                return

        if key == Qt.Key.Key_Left:
            self._clamp_cursor_to_prompt()
            cursor = self.textCursor()
            if cursor.position() <= (self._prompt_pos or 0):
                event.accept()
                return

        # Reset history browse on normal typing
        if key not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            self._history_index = -1
            self._pending_from_history = None

        self._clamp_cursor_to_prompt()
        # Block edits that would land before prompt via selection delete
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectionStart() < (self._prompt_pos or 0):
            event.accept()
            return
        super().keyPressEvent(event)
        # Re-sync prompt_pos if document mutated oddly
        text = self.toPlainText()
        if self._prompt_pos is not None and self._prompt_pos > len(text):
            self._prompt_pos = len(text)


class TerminalInputShim:
    """Compat API for former bottom QLineEdit — delegates to TerminalView."""

    def __init__(self, view: TerminalView) -> None:
        self._view = view

    def setFocus(self, *_args: Any, **_kwargs: Any) -> None:
        self._view.setFocus()
        self._view.move_cursor_to_prompt_end()

    def setEnabled(self, enabled: bool) -> None:
        if enabled:
            self._view.unlock_input()
        else:
            self._view.lock_input()

    def isEnabled(self) -> bool:
        return not self._view.is_input_locked()

    def text(self) -> str:
        return self._view.current_command()

    def clear(self) -> None:
        self._view.set_command_text("")

    def setText(self, text: str) -> None:
        self._view.set_command_text(text)

    def add_to_history(self, cmd: str) -> None:
        self._view.add_to_history(cmd)


class TerminalRunShim:
    """Compat for removed Run button — setEnabled mirrors input lock."""

    def __init__(self, view: TerminalView) -> None:
        self._view = view

    def setEnabled(self, enabled: bool) -> None:
        if enabled:
            self._view.unlock_input()
        else:
            self._view.lock_input()

    def isEnabled(self) -> bool:
        return not self._view.is_input_locked()

    def clicked(self) -> Any:
        """No-op signal stand-in; Run removed (Enter submits)."""
        return None


class ChatInputEdit(QTextEdit):
    """Chat compose field: Ctrl+Enter sends, Enter inserts a newline."""

    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.submit_requested.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class ChatWorker(QThread):
    """Background worker for chat requests to avoid UI freeze."""

    finished_payload = Signal(dict)
    failed = Signal(str)
    cancelled = Signal()
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
        self._cancelled = False

    def cancel(self) -> None:
        """Request cooperative cancellation (UI may return before LLM subprocess exits)."""
        self._cancelled = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._cancelled or self.isInterruptionRequested()

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
            if self._is_cancelled():
                self.cancelled.emit()
                return
            self.finished_payload.emit(result)
        except Exception as exc:
            if self._is_cancelled():
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))
