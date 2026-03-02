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
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def _build_overview_panel(main: MainWindow) -> QWidget:
    """Compact overview: Summary + SELF-GUARD + Ops metrics."""
    w = QWidget()
    layout = QHBoxLayout(w)
    # Summary
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
    grid.addWidget(QLabel("Deps"), 1, 0)
    grid.addWidget(main.dashboard_deps, 1, 1)
    grid.addWidget(QLabel("Cycles"), 2, 0)
    grid.addWidget(main.dashboard_cycles, 2, 1)
    grid.addWidget(QLabel("Risk"), 3, 0)
    grid.addWidget(main.dashboard_risk, 3, 1)
    grid.addWidget(QLabel("Maturity"), 4, 0)
    grid.addWidget(main.dashboard_maturity, 4, 1)
    grid.addWidget(QLabel("Trends"), 5, 0)
    grid.addWidget(main.dashboard_trends, 5, 1)
    layout.addWidget(metrics)
    # SELF-GUARD + Ops
    right = QWidget()
    right_layout = QVBoxLayout(right)
    main.dashboard_self_guard_text = QTextEdit()
    main.dashboard_self_guard_text.setReadOnly(True)
    main.dashboard_self_guard_text.setMaximumHeight(56)
    main.dashboard_self_guard_text.setPlaceholderText("Run scan for SELF-GUARD status")
    guard_group = QGroupBox("SELF-GUARD")
    guard_layout = QVBoxLayout(guard_group)
    guard_layout.addWidget(main.dashboard_self_guard_text)
    main.dashboard_firewall_detail_btn = QPushButton("Детали firewall")
    main.dashboard_firewall_detail_btn.setToolTip("Forbidden/layer/subsystem bypass")
    guard_layout.addWidget(main.dashboard_firewall_detail_btn)
    right_layout.addWidget(guard_group)
    ops_group = QGroupBox("Ops")
    ops_layout = QFormLayout(ops_group)
    main.dashboard_apply_rate = QLabel("-")
    main.dashboard_rollback_rate = QLabel("-")
    main.dashboard_median_verify = QLabel("-")
    ops_layout.addRow("Apply rate", main.dashboard_apply_rate)
    ops_layout.addRow("Rollback", main.dashboard_rollback_rate)
    ops_layout.addRow("Verify (ms)", main.dashboard_median_verify)
    right_layout.addWidget(ops_group)
    right_layout.addStretch()
    layout.addWidget(right)
    return w


def _build_risks_panel(main: MainWindow) -> QWidget:
    """Top risks + Risk prediction."""
    w = QWidget()
    layout = QVBoxLayout(w)
    risks_group = QGroupBox("Top risks")
    risks_layout = QVBoxLayout(risks_group)
    main.dashboard_risks_text = QTextEdit()
    main.dashboard_risks_text.setReadOnly(True)
    main.dashboard_risks_text.setMaximumHeight(120)
    main.dashboard_risks_text.setPlaceholderText("Run scan to see risks")
    risks_layout.addWidget(main.dashboard_risks_text)
    layout.addWidget(risks_group)
    risk_pred_group = QGroupBox("Risk prediction")
    risk_pred_layout = QVBoxLayout(risk_pred_group)
    main.dashboard_risk_pred_text = QTextEdit()
    main.dashboard_risk_pred_text.setReadOnly(True)
    main.dashboard_risk_pred_text.setMaximumHeight(100)
    main.dashboard_risk_pred_text.setPlaceholderText("Top modules by regression risk")
    risk_pred_layout.addWidget(main.dashboard_risk_pred_text)
    layout.addWidget(risk_pred_group)
    layout.addStretch()
    return w


def _build_learning_panel(main: MainWindow) -> QWidget:
    """Learning insights."""
    w = QWidget()
    layout = QVBoxLayout(w)
    learning = QGroupBox("Learning insights")
    learning_layout = QVBoxLayout(learning)
    main.learning_widget_text = QTextEdit()
    main.learning_widget_text.setReadOnly(True)
    main.learning_widget_text.setPlaceholderText(
        "Run fix/cycle to collect verify_success by smell|action|target."
    )
    learning_layout.addWidget(main.learning_widget_text)
    layout.addWidget(learning)
    return w


def build_dashboard_tab(main: MainWindow) -> None:
    """Build Dashboard tab: overview + sub-tabs for Risks and Learning."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setSpacing(8)
    refresh_row = QHBoxLayout()
    main.refresh_dashboard_btn = QPushButton("Обновить")
    refresh_row.addWidget(main.refresh_dashboard_btn)
    refresh_row.addStretch(1)
    layout.addLayout(refresh_row)
    overview = _build_overview_panel(main)
    layout.addWidget(overview)
    sub_tabs = QTabWidget()
    sub_tabs.addTab(_build_risks_panel(main), "Риски")
    sub_tabs.addTab(_build_learning_panel(main), "Обучение")
    layout.addWidget(sub_tabs, 1)
    main.tabs.addTab(tab, "Dashboard")
