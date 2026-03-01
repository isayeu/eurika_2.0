"""Dashboard tab: Summary, risks, self-guard, operational metrics. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_dashboard_tab(main: MainWindow) -> None:
    """Build Dashboard tab: summary, risks, self-guard, ops metrics, learning."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    refresh_row = QHBoxLayout()
    main.refresh_dashboard_btn = QPushButton("Refresh dashboard")
    refresh_row.addWidget(main.refresh_dashboard_btn)
    refresh_row.addStretch(1)
    layout.addLayout(refresh_row)
    metrics = QGroupBox("Summary")
    grid = QGridLayout(metrics)
    main.dashboard_modules = QLabel("-")
    main.dashboard_deps = QLabel("-")
    main.dashboard_cycles = QLabel("-")
    main.dashboard_risk = QLabel("-")
    main.dashboard_maturity = QLabel("-")
    main.dashboard_trends = QLabel("-")
    grid.addWidget(QLabel("Modules"), 0, 0)
    grid.addWidget(main.dashboard_modules, 0, 1)
    grid.addWidget(QLabel("Dependencies"), 1, 0)
    grid.addWidget(main.dashboard_deps, 1, 1)
    grid.addWidget(QLabel("Cycles"), 2, 0)
    grid.addWidget(main.dashboard_cycles, 2, 1)
    grid.addWidget(QLabel("Risk score"), 3, 0)
    grid.addWidget(main.dashboard_risk, 3, 1)
    grid.addWidget(QLabel("Maturity"), 4, 0)
    grid.addWidget(main.dashboard_maturity, 4, 1)
    grid.addWidget(QLabel("Trends"), 5, 0)
    grid.addWidget(main.dashboard_trends, 5, 1)
    layout.addWidget(metrics)
    risks_group = QGroupBox("Top risks")
    risks_layout = QVBoxLayout(risks_group)
    main.dashboard_risks_text = QTextEdit()
    main.dashboard_risks_text.setReadOnly(True)
    main.dashboard_risks_text.setMaximumHeight(100)
    main.dashboard_risks_text.setPlaceholderText("Run scan to see risks")
    risks_layout.addWidget(main.dashboard_risks_text)
    layout.addWidget(risks_group)
    self_guard_group = QGroupBox("SELF-GUARD (R5)")
    self_guard_layout = QVBoxLayout(self_guard_group)
    main.dashboard_self_guard_text = QTextEdit()
    main.dashboard_self_guard_text.setReadOnly(True)
    main.dashboard_self_guard_text.setMaximumHeight(80)
    main.dashboard_self_guard_text.setPlaceholderText("Run scan to see SELF-GUARD status")
    self_guard_layout.addWidget(main.dashboard_self_guard_text)
    layout.addWidget(self_guard_group)
    risk_pred_group = QGroupBox("Risk prediction (R5)")
    risk_pred_layout = QVBoxLayout(risk_pred_group)
    main.dashboard_risk_pred_text = QTextEdit()
    main.dashboard_risk_pred_text.setReadOnly(True)
    main.dashboard_risk_pred_text.setMaximumHeight(70)
    main.dashboard_risk_pred_text.setPlaceholderText(
        "Run scan to see top modules by regression risk"
    )
    risk_pred_layout.addWidget(main.dashboard_risk_pred_text)
    layout.addWidget(risk_pred_group)
    ops_group = QGroupBox("Operational metrics")
    ops_layout = QFormLayout(ops_group)
    main.dashboard_apply_rate = QLabel("-")
    main.dashboard_rollback_rate = QLabel("-")
    main.dashboard_median_verify = QLabel("-")
    ops_layout.addRow("Apply rate", main.dashboard_apply_rate)
    ops_layout.addRow("Rollback rate", main.dashboard_rollback_rate)
    ops_layout.addRow("Median verify (ms)", main.dashboard_median_verify)
    layout.addWidget(ops_group)
    learning = QGroupBox("Learning insights")
    learning_layout = QVBoxLayout(learning)
    main.learning_widget_text = QTextEdit()
    main.learning_widget_text.setReadOnly(True)
    main.learning_widget_text.setPlaceholderText(
        "Learning stats will appear after fix/cycle runs (verify_success by smell|action|target)."
    )
    learning_layout.addWidget(main.learning_widget_text)
    layout.addWidget(learning)
    main.tabs.addTab(tab, "Dashboard")
