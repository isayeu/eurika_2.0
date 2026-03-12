"""Approvals tab: Load plan, approve/reject per row, apply-approved. ROADMAP 3.1-arch.3."""
from __future__ import annotations
from typing import TYPE_CHECKING
from qt_app.ui.styles import get_secondary_hint, TAB_MARGINS
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QVBoxLayout, QWidget
if TYPE_CHECKING:
    from ..main_window import MainWindow

def _copy_diff_to_clipboard(main) -> None:
    te = main.approvals_diff_text
    te.selectAll()
    text = te.toPlainText()
    if text:
        QApplication.clipboard().setText(text)

def build_approve_tab(main: MainWindow) -> None:
    """Build Approvals tab: team-mode flow, approvals table, diff preview."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*TAB_MARGINS)
    layout.setSpacing(8)
    hint = QLabel('Team-mode: Run fix --team-mode → Load plan → Approve/reject → Save → Run apply-approved. Or: Run fix --dry-run (Commands) → Run apply-from-report to apply without re-scan.')
    hint.setWordWrap(True)
    main.approve_hint = hint
    hint.setStyleSheet(get_secondary_hint())
    layout.addWidget(hint)
    top = QHBoxLayout()
    main.run_team_mode_btn = QPushButton('Run fix (team-mode)')
    main.run_team_mode_btn.setToolTip('Run eurika fix . --team-mode to create pending plan')
    main.load_pending_btn = QPushButton('Load pending plan')
    main.save_approvals_btn = QPushButton('Save approve/reject')
    main.apply_approved_btn = QPushButton('Run apply-approved')
    main.apply_from_report_btn = QPushButton('Apply from report')
    main.apply_from_report_btn.setToolTip('Apply plan from eurika_fix_report.json (after dry-run); skips re-scan/LLM')
    top.addWidget(main.run_team_mode_btn)
    top.addWidget(main.load_pending_btn)
    top.addWidget(main.save_approvals_btn)
    top.addWidget(main.apply_approved_btn)
    top.addWidget(main.apply_from_report_btn)
    top.addStretch(1)
    layout.addLayout(top)
    main.approvals_table = QTableWidget(0, 5)
    main.approvals_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    main.approvals_table.setHorizontalHeaderLabels(['#', 'Target', 'Kind', 'Risk', 'Decision'])
    header = main.approvals_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.Stretch)
    header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
    layout.addWidget(main.approvals_table, 1)
    diff_row = QHBoxLayout()
    diff_label = QLabel('Diff preview (click row or file name):')
    main.approve_diff_label = diff_label
    diff_label.setStyleSheet(get_secondary_hint())
    diff_row.addWidget(diff_label)
    diff_row.addStretch(1)
    copy_btn = QPushButton('Выделить все и скопировать')
    copy_btn.setToolTip('Select all diff text and copy to clipboard')
    copy_btn.clicked.connect(_copy_diff_to_clipboard)
    diff_row.addWidget(copy_btn)
    layout.addLayout(diff_row)
    main.approvals_diff_text = QPlainTextEdit()
    main.approvals_diff_text.setReadOnly(True)
    main.approvals_diff_text.setPlaceholderText('Click a row or file name in the table to see the diff.')
    main.approvals_diff_text.setMinimumHeight(120)
    main.approvals_diff_text.setFont(main.approvals_diff_text.font())
    try:
        from PySide6.QtGui import QFont
        mono = QFont('Monospace', 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        main.approvals_diff_text.setFont(mono)
    except Exception:
        pass
    layout.addWidget(main.approvals_diff_text, 1)
    main.tabs.addTab(tab, 'Approvals')