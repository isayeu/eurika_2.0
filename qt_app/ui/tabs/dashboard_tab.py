"""Dashboard tab: Summary, risks, self-guard, operational metrics. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qt_app.ui.scroll import VerticalScrollArea
from qt_app.ui.styles import BTN_COMPACT_WIDTH, SECTION_SPACING, TAB_MARGINS

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
    main.dashboard_energy = QLabel("-")
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
    energy_label = QLabel("Energy")
    energy_label.setToolTip("ROADMAP §5.7: E = W·MetricVector. Lower = better architecture.")
    grid.addWidget(energy_label, 6, 0)
    main.dashboard_energy.setToolTip("Lower = better. complexity, coupling, cohesion, etc.")
    grid.addWidget(main.dashboard_energy, 6, 1)
    density_label = QLabel("Density")
    density_label.setToolTip("RV2: edges/(n*(n-1)). 0=sparse, 1=dense.")
    grid.addWidget(density_label, 7, 0)
    main.dashboard_density = QLabel("-")
    main.dashboard_density.setToolTip("Dependency density (RV2)")
    grid.addWidget(main.dashboard_density, 7, 1)
    layout.addWidget(metrics)
    # ARCHITECTURE METRICS (RV1, RV2)
    arch_group = QGroupBox("ARCHITECTURE METRICS")
    arch_layout = QVBoxLayout(arch_group)
    arch_dens_row = QHBoxLayout()
    arch_dens_label = QLabel("Density")
    arch_dens_label.setToolTip("RV2: edges/(n*(n-1)). 0=sparse, 1=dense.")
    main.dashboard_arch_density = QLabel("-")
    arch_dens_row.addWidget(arch_dens_label)
    arch_dens_row.addWidget(main.dashboard_arch_density)
    arch_dens_row.addStretch()
    arch_layout.addLayout(arch_dens_row)
    main.dashboard_blast_radius_text = QTextEdit()
    main.dashboard_blast_radius_text.setReadOnly(True)
    main.dashboard_blast_radius_text.setMaximumHeight(140)
    main.dashboard_blast_radius_text.setPlaceholderText("Run scan for blast radius + fragility heatmap")
    main.dashboard_blast_radius_text.setToolTip(
        "RV1: blast_radius. RV10: 🟢🟡🔴 by br (green<10, yellow<30, red≥30), propagation_depth"
    )
    arch_layout.addWidget(main.dashboard_blast_radius_text)
    layout.addWidget(arch_group)
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
    main.dashboard_firewall_detail_btn.setMaximumWidth(BTN_COMPACT_WIDTH)
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


def _build_history_panel(main: MainWindow) -> QWidget:
    """Evolution history: trends, evolution_report."""
    w = QWidget()
    layout = QVBoxLayout(w)
    history_group = QGroupBox("Evolution")
    history_layout = QVBoxLayout(history_group)
    main.dashboard_history_text = QTextEdit()
    main.dashboard_history_text.setReadOnly(True)
    main.dashboard_history_text.setPlaceholderText("Run scan to see evolution report")
    history_layout.addWidget(main.dashboard_history_text)
    layout.addWidget(history_group)
    return w


def _build_suggest_plan_panel(main: MainWindow) -> QWidget:
    """Suggest-plan recommendations (ROADMAP §7)."""
    w = QWidget()
    layout = QVBoxLayout(w)
    plan_group = QGroupBox("Suggest plan")
    plan_layout = QVBoxLayout(plan_group)
    main.dashboard_suggest_plan_text = QTextEdit()
    main.dashboard_suggest_plan_text.setReadOnly(True)
    main.dashboard_suggest_plan_text.setPlaceholderText(
        "Run scan first. Suggest-plan uses summary, recommendations, and history."
    )
    plan_layout.addWidget(main.dashboard_suggest_plan_text)
    layout.addWidget(plan_group)
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
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(*TAB_MARGINS)
    outer.setSpacing(SECTION_SPACING)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SECTION_SPACING)
    refresh_row = QHBoxLayout()
    main.refresh_dashboard_btn = QPushButton("Обновить")
    main.run_scan_dashboard_btn = QPushButton("Run scan")
    main.run_scan_dashboard_btn.setToolTip("Switch to Commands and run eurika scan")
    refresh_row.addWidget(main.refresh_dashboard_btn)
    refresh_row.addWidget(main.run_scan_dashboard_btn)
    refresh_row.addStretch(1)
    layout.addLayout(refresh_row)
    overview = _build_overview_panel(main)
    layout.addWidget(overview)
    sub_tabs = QTabWidget()
    sub_tabs.addTab(_build_risks_panel(main), "Риски")
    sub_tabs.addTab(_build_history_panel(main), "History")
    sub_tabs.addTab(_build_suggest_plan_panel(main), "Suggest plan")
    sub_tabs.addTab(_build_learning_panel(main), "Обучение")
    layout.addWidget(sub_tabs, 1)
    outer.addWidget(VerticalScrollArea(content))
    main.tabs.addTab(tab, "Dashboard")
