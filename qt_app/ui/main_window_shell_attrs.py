"""Typed widget attributes for Commands / Approvals / Graph / Notes / Dashboard."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CommandsTabAttrs:
    """Widgets created in commands_tab."""

    commands_tab: QWidget
    command_combo: QComboBox
    module_edit: QLineEdit
    module_browse_btn: QPushButton
    window_spin: QSpinBox
    runtime_mode_combo: QComboBox
    dry_run_check: QCheckBox
    no_llm_check: QCheckBox
    no_clean_imports_check: QCheckBox
    no_code_smells_check: QCheckBox
    use_llm_extract_check: QCheckBox
    allow_low_risk_campaign_check: QCheckBox
    team_mode_check: QCheckBox
    learn_group: QGroupBox
    learn_light_check: QCheckBox
    learn_scan_check: QCheckBox
    learn_build_patterns_check: QCheckBox
    learn_limit_label: QLabel
    learn_limit_spin: QSpinBox
    bug_hunt_group: QGroupBox
    bug_hunt_sandbox_check: QCheckBox
    bug_hunt_web_check: QCheckBox
    preview_label: QLabel
    run_btn: QPushButton
    stop_btn: QPushButton
    ruff_btn: QPushButton
    mypy_btn: QPushButton
    release_check_btn: QPushButton


class ApproveTabAttrs:
    """Widgets created in approve_tab."""

    approve_hint: QLabel
    approve_diff_label: QLabel
    run_team_mode_btn: QPushButton
    load_pending_btn: QPushButton
    save_approvals_btn: QPushButton
    apply_approved_btn: QPushButton
    apply_from_report_btn: QPushButton
    approvals_tab_index: int
    approvals_table: QTableWidget
    approvals_diff_text: QPlainTextEdit


class GraphTabAttrs:
    """Widgets created in graph_tab."""

    refresh_graph_btn: QPushButton
    graph_hint: QLabel
    graph_placeholder: QWidget
    graph_placeholder_layout: QVBoxLayout
    graph_tab_index: int
    _graph_web_view: Any | None
    _graph_table_fallback: QTextEdit | None
    _graph_webengine_available: bool | None


class NotesTabAttrs:
    """Widgets created in notes_tab."""

    notes_text: QTextEdit
    notes_save_btn: QPushButton


class DashboardTabAttrs:
    """Widgets created in dashboard_tab (subset used from main_window wiring)."""

    refresh_dashboard_btn: QPushButton
    run_scan_dashboard_btn: QPushButton
    dashboard_firewall_detail_btn: QPushButton
    learning_widget_text: QTextEdit
