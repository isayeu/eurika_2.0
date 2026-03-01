"""Approvals tab: Load plan, approve/reject per row, apply-approved. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_approve_tab(main: MainWindow) -> None:
    """Build Approvals tab: team-mode flow, approvals table, diff preview."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    hint = QLabel(
        "1. Run fix with --team-mode (Commands tab) → 2. Load plan → 3. Approve/reject per row → 4. Save → 5. Run apply-approved"
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: gray; font-size: 11px;")
    layout.addWidget(hint)
    top = QHBoxLayout()
    main.run_team_mode_btn = QPushButton("Run fix (team-mode)")
    main.run_team_mode_btn.setToolTip("Run eurika fix . --team-mode to create pending plan")
    main.load_pending_btn = QPushButton("Load pending plan")
    main.save_approvals_btn = QPushButton("Save approve/reject")
    main.apply_approved_btn = QPushButton("Run apply-approved")
    top.addWidget(main.run_team_mode_btn)
    top.addWidget(main.load_pending_btn)
    top.addWidget(main.save_approvals_btn)
    top.addWidget(main.apply_approved_btn)
    top.addStretch(1)
    layout.addLayout(top)
    main.approvals_table = QTableWidget(0, 5)
    main.approvals_table.setHorizontalHeaderLabels(["#", "Target", "Kind", "Risk", "Decision"])
    header = main.approvals_table.horizontalHeader()
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
    layout.addWidget(main.approvals_table, 1)
    diff_label = QLabel("Diff preview (select a row):")
    diff_label.setStyleSheet("color: gray; font-size: 11px;")
    layout.addWidget(diff_label)
    main.approvals_diff_text = QPlainTextEdit()
    main.approvals_diff_text.setReadOnly(True)
    main.approvals_diff_text.setPlaceholderText("Select an operation row to see the diff.")
    main.approvals_diff_text.setMinimumHeight(120)
    main.approvals_diff_text.setFont(main.approvals_diff_text.font())
    try:
        from PySide6.QtGui import QFont

        mono = QFont("Monospace", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        main.approvals_diff_text.setFont(mono)
    except Exception:
        pass
    layout.addWidget(main.approvals_diff_text, 1)
    main.tabs.addTab(tab, "Approvals")
