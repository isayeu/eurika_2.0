"""Chat tab: Session history, send message, apply/reject plan. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_chat_tab(main: MainWindow) -> None:
    """Build Chat tab: history, compose, apply/reject buttons."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)
    history_box = QGroupBox("Session chat history")
    history_layout = QVBoxLayout(history_box)
    main.chat_goal_view = QTextEdit()
    main.chat_goal_view.setReadOnly(True)
    main.chat_goal_view.setMinimumHeight(70)
    main.chat_goal_view.setPlaceholderText(
        "Interpreted goal/confidence will appear here after chat requests."
    )
    history_layout.addWidget(main.chat_goal_view)
    main.chat_transcript = QTextEdit()
    main.chat_transcript.setReadOnly(True)
    main.chat_transcript.setAcceptRichText(True)
    history_layout.addWidget(main.chat_transcript)
    layout.addWidget(history_box, 1)
    compose_box = QGroupBox("Send message")
    compose_layout = QVBoxLayout(compose_box)
    main.chat_input = QTextEdit()
    main.chat_input.setPlaceholderText(
        "Ask Eurika about architecture or request refactor guidance..."
    )
    main.chat_input.setMinimumHeight(80)
    compose_layout.addWidget(main.chat_input)
    main.chat_pending_label = QLabel("Pending plan: none")
    main.chat_pending_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    compose_layout.addWidget(main.chat_pending_label)
    buttons = QHBoxLayout()
    main.chat_send_btn = QPushButton("Send")
    main.chat_clear_btn = QPushButton("Clear session")
    main.chat_apply_btn = QPushButton("Apply")
    main.chat_reject_btn = QPushButton("Reject")
    main.chat_apply_btn.setEnabled(False)
    main.chat_reject_btn.setEnabled(False)
    buttons.addWidget(main.chat_send_btn)
    buttons.addWidget(main.chat_clear_btn)
    buttons.addWidget(main.chat_apply_btn)
    buttons.addWidget(main.chat_reject_btn)
    buttons.addStretch(1)
    compose_layout.addLayout(buttons)
    io_split = QSplitter(Qt.Orientation.Vertical)
    io_split.addWidget(history_box)
    io_split.addWidget(compose_box)
    io_split.setChildrenCollapsible(False)
    io_split.setStretchFactor(0, 3)
    io_split.setStretchFactor(1, 2)
    layout.addWidget(io_split, 1)
    main.tabs.addTab(tab, "Chat")
