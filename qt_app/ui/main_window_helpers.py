"""Helpers and widgets for Eurika Qt main window. Reduces main_window.py size (ROADMAP 3.1-arch.3)."""
from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from eurika.api.chat_host_ops import PrivilegeAction, PrivilegePrompt
from PySide6.QtCore import QMimeData, QObject, QPoint, Qt, QThread, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QImage, QKeyEvent, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTextEdit,
    QWidget,
)

_ANSI_STRIP_RE = re.compile(
    '\\x1b\\[[0-?]*[ -/]*[@-~]|\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)|'
    '\\x1b[PX^_][^\\x1b]*\\x1b\\\\',
    re.DOTALL,
)
_OLLAMA_PULL_PCT_RE = re.compile(r'(\d+)\s*%')
_OLLAMA_PULL_MB_GB_RE = re.compile(r'(\d+)\s*MB\s*/\s*([\d.]+)\s*GB')
_TUI_COMMANDS = frozenset(('htop', 'top', 'vim', 'vi', 'nano', 'less', 'more', 'watch', 'mc'))
CHAT_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})


class HostPrivilegeBridge(QObject):
    """Main-thread sudo / continue / skip prompts for the chat tool-loop."""

    @Slot(str, str, result=str)
    def ask(self, cmd: str, hint: str) -> str:
        """Return ``password\\n…``, ``continue``, or ``skip`` (BlockingQueuedConnection-safe)."""
        raw_parent = self.parent()
        parent = raw_parent if isinstance(raw_parent, QWidget) else None
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Нужны права")
        body = (hint or "").strip() or "Команде могут понадобиться права администратора."
        cmd_s = (cmd or "").strip()
        if cmd_s:
            body = f"{body}\n\n$ {cmd_s}"
        box.setText(body)
        box.setInformativeText(
            "Ввести пароль sudo, продолжить без пароля (с ограничениями) или пропустить команду?"
        )
        btn_password = box.addButton("Ввести пароль", QMessageBox.ButtonRole.AcceptRole)
        btn_continue = box.addButton("Без пароля", QMessageBox.ButtonRole.ActionRole)
        btn_skip = box.addButton("Пропустить", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_password)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_skip:
            return "skip"
        if clicked is btn_continue:
            return "continue"
        pwd, ok = QInputDialog.getText(
            parent,
            "Пароль sudo",
            f"Пароль для:\n$ {cmd_s}" if cmd_s else "Пароль sudo:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return "skip"
        return "password\n" + str(pwd)


def privilege_prompt_from_bridge(bridge: HostPrivilegeBridge) -> PrivilegePrompt:
    """Build a worker-safe privilege_prompt callable bound to ``bridge``."""

    def _prompt(cmd: str, hint: str) -> tuple[PrivilegeAction, str]:
        from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject

        # Tool-loop may run off the GUI thread — marshal the dialog.
        raw: Any = "continue"
        try:
            if QThread.currentThread() is bridge.thread():
                raw = bridge.ask(cmd, hint)
            else:
                raw = QMetaObject.invokeMethod(
                    bridge,
                    "ask",
                    Qt.ConnectionType.BlockingQueuedConnection,
                    Q_RETURN_ARG(str),
                    Q_ARG(str, cmd),
                    Q_ARG(str, hint),
                )
        except Exception:
            raw = "continue"
        text = raw if isinstance(raw, str) else "continue"
        if text.startswith("password\n"):
            return "password", text.split("\n", 1)[1]
        if text == "skip":
            return "skip", ""
        return "continue", ""

    return _prompt


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
    """Chat compose field: Ctrl+Enter sends; Up/Down browse sent prompts (like Terminal).

    Cursor-like ``@`` autocomplete: modules from self_map + smell types.
    """

    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._history_index = -1
        self._pending_from_history: str | None = None
        self._mention_catalog: list[str] = []
        self._mention_popup: QListWidget | None = None
        self._project_root: str = ""
        self.setAcceptDrops(True)
        self.textChanged.connect(self._on_text_changed_for_mentions)

    def set_project_root(self, root: str | None) -> None:
        self._project_root = str(root or "").strip()

    def _save_pasted_image(self, image: QImage) -> str | None:
        if image is None or image.isNull():
            return None
        scaled = image
        if scaled.width() > 1920:
            scaled = scaled.scaledToWidth(1920, Qt.TransformationMode.SmoothTransformation)
        root = Path(self._project_root).expanduser() if self._project_root else Path.home()
        folder = root / ".eurika" / "chat_images"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.png"
        path = folder / name
        if not scaled.save(str(path), "PNG"):
            return None
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return str(path)

    def _chat_images_root(self) -> Path:
        root = Path(self._project_root).expanduser() if self._project_root else Path.home()
        return root / ".eurika" / "chat_images"

    def _rel_chat_image_path(self, path: Path) -> str:
        root = Path(self._project_root).expanduser() if self._project_root else Path.home()
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return str(path)

    def _copy_image_file(self, src: Path) -> str | None:
        if src.suffix.lower() not in CHAT_IMAGE_EXTS or not src.is_file():
            return None
        folder = self._chat_images_root()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        dest = folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{src.suffix.lower()}"
        try:
            shutil.copy2(src, dest)
        except OSError:
            return None
        return self._rel_chat_image_path(dest)

    def _image_paths_from_mime(self, source: QMimeData | None) -> list[Path]:
        if source is None or not source.hasUrls():
            return []
        out: list[Path] = []
        for url in source.urls():
            local = url.toLocalFile()
            if not local:
                continue
            path = Path(local)
            if path.suffix.lower() in CHAT_IMAGE_EXTS and path.is_file():
                out.append(path)
        return out

    def _insert_image_file(self, path: Path) -> bool:
        rel = self._copy_image_file(path)
        if not rel:
            return False
        alt = path.stem or "image"
        self.textCursor().insertText(f"\n![{alt}]({rel})\n")
        return True

    def _insert_screenshot_markdown(self, image: QImage) -> bool:
        rel = self._save_pasted_image(image)
        if not rel:
            return False
        self.textCursor().insertText(f"\n![screenshot]({rel})\n")
        return True

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        if source is not None and (source.hasImage() or bool(self._image_paths_from_mime(source))):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        if source is not None and source.hasImage():
            raw = source.imageData()
            image: QImage | None = None
            if isinstance(raw, QImage):
                image = raw
            elif isinstance(raw, QPixmap):
                image = raw.toImage()
            if image is not None and self._insert_screenshot_markdown(image):
                return
        if source is not None:
            inserted = False
            for path in self._image_paths_from_mime(source):
                inserted = self._insert_image_file(path) or inserted
            if inserted:
                return
        super().insertFromMimeData(source)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime is not None and (mime.hasImage() or self._image_paths_from_mime(mime)):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        mime = event.mimeData()
        if mime is not None and (mime.hasImage() or self._image_paths_from_mime(mime)):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def set_mention_catalog(self, items: list[str] | None) -> None:
        self._mention_catalog = [str(x) for x in (items or []) if str(x).strip()]

    def refresh_mentions_from_root(self, root: str | None) -> None:
        from eurika.api.chat_mentions import build_mention_catalog

        self.set_mention_catalog(build_mention_catalog(root))
        self.set_project_root(root)

    def mention_popup_visible(self) -> bool:
        return bool(self._mention_popup is not None and self._mention_popup.isVisible())

    def _ensure_mention_popup(self) -> QListWidget:
        if self._mention_popup is None:
            popup = QListWidget(self)
            popup.setWindowFlags(
                Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
            )
            popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            popup.setMaximumHeight(180)
            popup.setMinimumWidth(220)
            popup.itemClicked.connect(self._on_mention_item_clicked)
            self._mention_popup = popup
        return self._mention_popup

    def _hide_mention_popup(self) -> None:
        if self._mention_popup is not None:
            self._mention_popup.hide()
            self._mention_popup.clear()

    def _on_text_changed_for_mentions(self) -> None:
        self._update_mention_popup()

    def _current_at_token(self) -> tuple[int, int, str] | None:
        from eurika.api.chat_mentions import extract_at_token

        return extract_at_token(self.toPlainText(), self.textCursor().position())

    def _update_mention_popup(self) -> None:
        from eurika.api.chat_mentions import filter_mention_candidates

        token = self._current_at_token()
        if token is None:
            self._hide_mention_popup()
            return
        _at, _end, prefix = token
        catalog = self._mention_catalog
        if not catalog:
            # Still offer smells even before root refresh.
            from eurika.api.chat_mentions import smell_mention_ids

            catalog = smell_mention_ids()
        matches = filter_mention_candidates(catalog, prefix)
        if not matches:
            self._hide_mention_popup()
            return
        popup = self._ensure_mention_popup()
        popup.clear()
        for name in matches:
            popup.addItem(QListWidgetItem(name))
        popup.setCurrentRow(0)
        # Size to content (capped).
        row_h = popup.sizeHintForRow(0) if popup.count() else 20
        popup.setFixedHeight(min(180, max(28, row_h * min(popup.count(), 8) + 8)))
        widest = max(220, popup.sizeHintForColumn(0) + 24)
        popup.setFixedWidth(min(420, widest))
        rect = self.cursorRect()
        global_pos = self.mapToGlobal(rect.bottomLeft())
        popup.move(global_pos + QPoint(0, 2))
        popup.show()

    def _insert_mention(self, name: str) -> None:
        token = self._current_at_token()
        if token is None:
            return
        at, end, _prefix = token
        cursor = self.textCursor()
        cursor.setPosition(at)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(f"@{name} ")
        self.setTextCursor(cursor)
        self._hide_mention_popup()

    def _on_mention_item_clicked(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        self._insert_mention(item.text())

    def add_to_history(self, cmd: str) -> None:
        cmd = (cmd or "").strip()
        if not cmd:
            return
        if self._history and self._history[-1] == cmd:
            self._history_index = -1
            self._pending_from_history = None
            return
        self._history.append(cmd)
        if len(self._history) > 500:
            self._history.pop(0)
        self._history_index = -1
        self._pending_from_history = None

    def history_snapshot(self) -> list[str]:
        return list(self._history)

    def set_history(self, items: list[str] | None) -> None:
        cleaned: list[str] = []
        for raw in items or []:
            s = str(raw or "").strip()
            if s:
                cleaned.append(s)
        self._history = cleaned[-500:]
        self._history_index = -1
        self._pending_from_history = None

    def _cursor_on_first_block(self) -> bool:
        return self.textCursor().blockNumber() == 0

    def _cursor_on_last_block(self) -> bool:
        return self.textCursor().blockNumber() >= max(0, self.document().blockCount() - 1)

    def _apply_history_entry(self, text: str) -> None:
        self.setPlainText(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if self.mention_popup_visible() and self._mention_popup is not None:
            if key == Qt.Key.Key_Escape:
                self._hide_mention_popup()
                event.accept()
                return
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                row = self._mention_popup.currentRow()
                count = self._mention_popup.count()
                if count <= 0:
                    self._hide_mention_popup()
                    super().keyPressEvent(event)
                    return
                if key == Qt.Key.Key_Up:
                    row = (row - 1) % count
                else:
                    row = (row + 1) % count
                self._mention_popup.setCurrentRow(row)
                event.accept()
                return
            if key == Qt.Key.Key_Tab or (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            ):
                item = self._mention_popup.currentItem()
                if item is not None:
                    self._insert_mention(item.text())
                    event.accept()
                    return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self._hide_mention_popup()
                self.submit_requested.emit()
                event.accept()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ControlModifier:
                self._hide_mention_popup()
                self.submit_requested.emit()
                event.accept()
                return
        if key == Qt.Key.Key_Up and self._cursor_on_first_block():
            if not self._history:
                super().keyPressEvent(event)
                return
            if self._history_index < 0:
                self._pending_from_history = self.toPlainText()
            self._history_index = min(len(self._history) - 1, self._history_index + 1)
            self._apply_history_entry(self._history[-(self._history_index + 1)])
            event.accept()
            return
        if key == Qt.Key.Key_Down and self._cursor_on_last_block():
            if self._history_index < 0:
                super().keyPressEvent(event)
                return
            if self._history_index <= 0:
                self._history_index = -1
                self._apply_history_entry(self._pending_from_history or "")
                self._pending_from_history = None
            else:
                self._history_index -= 1
                self._apply_history_entry(self._history[-(self._history_index + 1)])
            event.accept()
            return
        # Reset browse index when the user edits (not while only navigating).
        if key not in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                       Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_Shift, Qt.Key.Key_Control,
                       Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            if self._history_index >= 0 and key not in (
                Qt.Key.Key_Control,
                Qt.Key.Key_Shift,
                Qt.Key.Key_Alt,
            ):
                # Keep index until real text change — clear on printable / backspace.
                if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) or (
                    event.text() and event.text().isprintable()
                ):
                    self._history_index = -1
                    self._pending_from_history = None
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
        openai_base_url: str = "",
        run_command_with_result: Any = None,
        privilege_prompt: Any = None,
        cursor_model: str = "",
        cursor_optimize: str = "",
    ) -> None:
        super().__init__()
        self._api = api
        self._message = message
        self._history = history
        self._provider = provider
        self._openai_model = openai_model
        self._ollama_model = ollama_model
        self._timeout_sec = timeout_sec
        self._openai_base_url = openai_base_url
        self._cursor_model = cursor_model
        self._cursor_optimize = cursor_optimize
        self._run_command_with_result = run_command_with_result
        self._privilege_prompt = privilege_prompt
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
                openai_base_url=self._openai_base_url,
                cursor_model=self._cursor_model,
                cursor_optimize=self._cursor_optimize,
                on_system_action=_on_action,
                run_command_with_result=self._run_command_with_result,
                privilege_prompt=self._privilege_prompt,
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
