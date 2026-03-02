"""Notes tab: personal notes with persistence across sessions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_notes_tab(main: MainWindow) -> None:
    """Build Notes tab: text area + Save button."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(6, 6, 6, 6)
    main.notes_text = QTextEdit()
    main.notes_text.setPlaceholderText("Заметки для текущей сессии. Сохраняются в .eurika/notes.txt проекта.")
    main.notes_text.setAcceptRichText(False)
    layout.addWidget(main.notes_text, 1)
    btn_row = QHBoxLayout()
    main.notes_save_btn = QPushButton("Save")
    main.notes_save_btn.setToolTip("Сохранить заметки для следующей сессии")
    btn_row.addWidget(main.notes_save_btn)
    btn_row.addStretch()
    layout.addLayout(btn_row)
    main.tabs.addTab(tab, "Notes")
