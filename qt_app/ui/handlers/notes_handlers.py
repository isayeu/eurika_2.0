"""Handlers for Notes tab: load/save notes to project .eurika/notes.txt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox


def _notes_path(project_root: str) -> Path:
    """Path to notes file: project_root/.eurika/notes.txt, or ~/.eurika/notes.txt if no project."""
    root = (project_root or "").strip()
    if root:
        return Path(root).resolve() / ".eurika" / "notes.txt"
    return Path.home() / ".eurika" / "notes.txt"


def load_notes(main) -> None:
    """Load notes from file into notes_text. Call when opening Notes tab or changing project root."""
    if not hasattr(main, "notes_text"):
        return
    path = _notes_path(main.root_edit.text().strip() if main.root_edit else "")
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
        main.notes_text.setPlainText(text)
    except (OSError, UnicodeDecodeError):
        pass


def save_notes(main) -> None:
    """Save notes_text to file."""
    if not hasattr(main, "notes_text"):
        return
    path = _notes_path(main.root_edit.text().strip() if main.root_edit else "")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(main.notes_text.toPlainText(), encoding="utf-8")
        main.status_label.setText("Notes saved.")
    except OSError as e:
        QMessageBox.warning(main, "Notes", f"Could not save notes: {e}")
