"""Typed widget attributes for Chat + Terminal tabs (assigned in chat_tab / terminal_tab)."""

from __future__ import annotations

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QWidget,
)

from qt_app.ui.main_window_helpers import (
    ChatInputEdit,
    HostPrivilegeBridge,
    TerminalInputShim,
    TerminalLineEdit,
    TerminalRunShim,
    TerminalView,
)


class ChatTabAttrs:
    """Attribute declarations for widgets created in chat_tab."""

    chat_tab_index: int
    chat_inner_tabs: QTabWidget
    chat_dialog_subtab_index: int
    chat_market_subtab_index: int
    chat_mode_agent_btn: QPushButton
    chat_mode_market_btn: QPushButton
    chat_mode_learn_btn: QPushButton
    chat_llm_source_label: QLabel
    chat_mode_status_label: QLabel
    chat_goal_view: QTextEdit
    chat_diff_view: QTextEdit
    chat_focus_terminal_btn: QPushButton
    chat_focus_approvals_btn: QPushButton
    chat_transcript: QTextBrowser
    _chat_history: list[dict[str, str]]
    _chat_history_root: str
    _chat_block_payloads: dict[str, str]
    _host_privilege_bridge: HostPrivilegeBridge | None
    _live_chat_seen: set[str]
    _live_chat_offset: int
    _live_activity_offset: int
    _live_activity_ids: set[str]
    _live_activity_timer: QTimer | None
    chat_input: ChatInputEdit
    chat_pending_label: QLabel
    chat_typing_label: QLabel
    chat_send_btn: QPushButton
    chat_cancel_btn: QPushButton
    chat_clear_btn: QPushButton
    chat_apply_btn: QPushButton
    chat_reject_btn: QPushButton
    chat_diff_btn: QPushButton
    chat_feedback_helpful_btn: QPushButton
    chat_feedback_not_btn: QPushButton
    market_live_check: QCheckBox
    market_auto_check: QCheckBox
    market_micro_train_check: QCheckBox
    market_llm_learn_check: QCheckBox
    idle_self_dev_check: QCheckBox
    market_llm_tf1_combo: QComboBox
    market_llm_tf2_combo: QComboBox
    market_explore_check: QCheckBox
    market_explore_cap_spin: QSpinBox
    market_explore_reset_btn: QPushButton
    market_kind_combo: QComboBox
    market_spot_list: QListWidget
    market_spot_edit: QLineEdit
    market_spot_add_btn: QPushButton
    market_spot_del_btn: QPushButton
    market_spot_fill_btn: QPushButton
    market_futures_list: QListWidget
    market_futures_edit: QLineEdit
    market_futures_add_btn: QPushButton
    market_futures_del_btn: QPushButton
    market_candle_combo: QComboBox
    market_horizon_spin: QSpinBox
    market_exec_1m_check: QCheckBox
    market_tp_spin: QDoubleSpinBox
    market_sl_spin: QDoubleSpinBox
    market_trail_spin: QDoubleSpinBox
    market_interval_spin: QSpinBox
    market_tick_btn: QPushButton
    market_drop_orphans_btn: QPushButton
    market_clear_btn: QPushButton
    market_bank_label: QLabel
    market_status_label: QLabel
    market_transcript: QTextEdit
    _market_timer: QTimer | None
    _market_tick_busy: bool
    _market_tick_worker: object | None
    _market_llm_timer: QTimer | None
    _market_llm_worker: object | None
    _market_llm_warned_no_key: bool
    _idle_self_dev_timer: QTimer | None
    _idle_self_dev_worker: object | None
    workspace_rail: QFrame
    workspace_toggle_btn: QPushButton
    workspace_tree: QTreeWidget
    workspace_splitter: QSplitter


class TerminalTabAttrs:
    """Attribute declarations for widgets created in terminal_tab."""

    terminal_tab: QWidget
    terminal_tab_index: int
    terminal_emulator_output: TerminalView
    terminal_emulator_input: TerminalInputShim | TerminalLineEdit
    terminal_emulator_btn: TerminalRunShim | QPushButton
    terminal_emulator_stop_btn: QPushButton
    terminal_emulator_clear_btn: QPushButton
    _terminal_process: QProcess | None
    _terminal_cwd: str
