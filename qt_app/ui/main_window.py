"""Main window for Eurika Qt thin-shell UI."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter
from qt_app.services.command_service import CommandService
from qt_app.services.settings_service import SettingsService
from eurika.utils.env import load_project_dotenv
from qt_app.ui.styles import (
    CONTENT_MARGINS,
    get_hint_label_stylesheet,
    get_hint_stylesheet,
    get_secondary_hint,
    get_status_style,
    is_dark_theme,
    set_theme_dark,
)
from qt_app.ui.theme import apply_app_theme
from .handlers import (
    approve_handlers,
    chat_handlers,
    command_handlers,
    dashboard_handlers,
    market_handlers,
    ml_handlers,
    notes_handlers,
    ollama_handlers,
)
from .main_window_helpers import ChatWorker, default_start_directory
from .main_window_chat_attrs import ChatTabAttrs, TerminalTabAttrs
from .main_window_models_attrs import ModelsTabAttrs
from .main_window_shell_attrs import (
    ApproveTabAttrs,
    CommandsTabAttrs,
    DashboardTabAttrs,
    GraphTabAttrs,
    NotesTabAttrs,
)
from .tabs import approve_tab, chat_tab, commands_tab, dashboard_tab, graph_tab, help_tab, models_tab, notes_tab, terminal_tab

class MainWindow(
    ModelsTabAttrs,
    ChatTabAttrs,
    TerminalTabAttrs,
    CommandsTabAttrs,
    ApproveTabAttrs,
    GraphTabAttrs,
    NotesTabAttrs,
    DashboardTabAttrs,
    QMainWindow,
):
    """Desktop-first shell for running core Eurika workflows."""

    tabs: QTabWidget
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Eurika Qt')
        self.resize(1100, 760)
        self._settings = SettingsService()
        saved_root = self._settings.get_project_root()
        self._first_run_prompt_pending = not bool(saved_root and saved_root.strip())
        initial_root = '' if self._first_run_prompt_pending else (saved_root or '').strip() or '.'
        self._api = EurikaApiAdapter(initial_root)
        self._command_service = CommandService(self)
        self._pending_operations: list[dict[str, Any]] = []
        self._chat_history: list[dict[str, str]] = []
        self._chat_worker: ChatWorker | None = None
        self._chat_cancelled = False
        self._pending_plan_token = ''
        self._pending_plan_fallback_active = False
        self._pending_diff_gate_fp = ''
        self._pending_diff_seen_fp = ''
        self._is_closing = False
        self._ollama_process = QProcess(self)
        self._ollama_task_process = QProcess(self)
        self._ollama_task_mode = ''
        self._ollama_task_stdout = ''
        self._ollama_task_model = ''
        self._saved_available_model = ''
        self._last_models_error = ''
        self._ollama_health_timer = QTimer(self)
        ollama_handlers.wire_ollama_process(self)
        ollama_handlers.wire_ollama_task_process(self)
        self._build_ui()
        self._wire_events()
        self._set_project_root(initial_root)
        ollama_handlers.setup_ollama_health_timer(self)

    def _build_ui(self) -> None:
        menubar = QMenuBar(self)
        view_menu = QMenu("View", self)
        self._dark_theme_action = view_menu.addAction("Dark theme")
        self._dark_theme_action.setCheckable(True)
        self._dark_theme_action.setChecked(is_dark_theme())
        self._dark_theme_action.triggered.connect(self._on_toggle_dark_theme)
        menubar.addMenu(view_menu)
        self.setMenuBar(menubar)
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(*CONTENT_MARGINS)
        root_layout.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(QLabel("Project root:"))
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Select project root (pyproject.toml or self_map.json)")
        top_row.addWidget(self.root_edit, 1)
        self.browse_btn = QPushButton("Browse")
        top_row.addWidget(self.browse_btn)
        root_layout.addLayout(top_row)
        self._first_run_hint = QFrame()
        self._first_run_hint.setFrameShape(QFrame.Shape.StyledPanel)
        self._first_run_hint.setStyleSheet(get_hint_stylesheet())
        hint_layout = QHBoxLayout(self._first_run_hint)
        hint_layout.setContentsMargins(12, 10, 12, 10)
        self._first_run_hint_label = QLabel(
            "Выберите проект — Browse или путь к корню Python-проекта. "
            "Без проекта команды scan/doctor/fix недоступны."
        )
        self._first_run_hint_label.setWordWrap(True)
        self._first_run_hint_label.setStyleSheet(get_hint_label_stylesheet())
        hint_layout.addWidget(self._first_run_hint_label)
        root_layout.addWidget(self._first_run_hint)
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, 1)
        # Chat-first: агент в центре; остальные вкладки — вторичные панели.
        chat_tab.build_chat_tab(self)
        terminal_tab.build_terminal_tab(self)
        models_tab.build_models_tab(self)
        approve_tab.build_approve_tab(self)
        commands_tab.build_commands_tab(self)
        dashboard_tab.build_dashboard_tab(self)
        graph_tab.build_graph_tab(self)
        notes_tab.build_notes_tab(self)
        help_tab.build_help_tab(self)
        if hasattr(self, "chat_tab_index"):
            self.tabs.setCurrentIndex(self.chat_tab_index)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(get_status_style())
        root_layout.addWidget(self.status_label)

    def _on_toggle_dark_theme(self, checked: bool) -> None:
        self._settings.set_theme("dark" if checked else "light")
        set_theme_dark(checked)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_app_theme(app, checked)
        self._refresh_theme_styles()

    def _refresh_theme_styles(self) -> None:
        """Re-apply theme-dependent styles to custom widgets."""
        self._first_run_hint.setStyleSheet(get_hint_stylesheet())
        self._first_run_hint_label.setStyleSheet(get_hint_label_stylesheet())
        self.status_label.setStyleSheet(get_status_style())
        if hasattr(self, "approve_hint"):
            self.approve_hint.setStyleSheet(get_secondary_hint())
        if hasattr(self, "approve_diff_label"):
            self.approve_diff_label.setStyleSheet(get_secondary_hint())
        if hasattr(self, "graph_hint"):
            self.graph_hint.setStyleSheet(get_secondary_hint())
        if hasattr(self, "ollama_pull_progress_label"):
            self.ollama_pull_progress_label.setStyleSheet(get_secondary_hint())
        if hasattr(self, "ml_policy_hint"):
            self.ml_policy_hint.setStyleSheet(get_secondary_hint())
        if hasattr(self, "ollama_gpu_hint"):
            self.ollama_gpu_hint.setStyleSheet(get_secondary_hint())

    def _on_tab_changed(self, index: int) -> None:
        """Lazy-load Graph WebEngine when user first opens Graph tab."""
        if index == self.graph_tab_index:
            graph_tab.ensure_graph_widget(self)
            graph_tab.refresh_graph(self)

    def _wire_events(self) -> None:
        self.browse_btn.clicked.connect(self._select_root)
        self.root_edit.editingFinished.connect(self._on_root_edited)
        if getattr(self, "module_browse_btn", None):
            self.module_browse_btn.clicked.connect(lambda: command_handlers.select_module(self))
        self.command_combo.currentIndexChanged.connect(self._sync_preview)
        self.module_edit.textChanged.connect(self._sync_preview)
        self.window_spin.valueChanged.connect(self._sync_preview)
        self.dry_run_check.toggled.connect(self._sync_preview)
        self.no_llm_check.toggled.connect(self._sync_preview)
        self.no_clean_imports_check.toggled.connect(self._sync_preview)
        self.no_code_smells_check.toggled.connect(self._sync_preview)
        self.use_llm_extract_check.toggled.connect(self._sync_preview)
        self.allow_low_risk_campaign_check.toggled.connect(self._sync_preview)
        self.team_mode_check.toggled.connect(self._sync_preview)
        if getattr(self, "runtime_mode_combo", None):
            self.runtime_mode_combo.currentIndexChanged.connect(self._sync_preview)
        if getattr(self, "learn_light_check", None):
            self.learn_light_check.toggled.connect(self._sync_preview)
            self.learn_scan_check.toggled.connect(self._sync_preview)
            self.learn_build_patterns_check.toggled.connect(self._sync_preview)
            self.learn_limit_spin.valueChanged.connect(self._sync_preview)
        self.run_btn.clicked.connect(lambda: command_handlers.run_command(self))
        self.stop_btn.clicked.connect(self._command_service.stop)
        self.ruff_btn.clicked.connect(lambda: command_handlers.run_ruff(self))
        self.mypy_btn.clicked.connect(lambda: command_handlers.run_mypy(self))
        self.release_check_btn.clicked.connect(lambda: command_handlers.run_release_check(self))
        self.refresh_dashboard_btn.clicked.connect(lambda: dashboard_handlers.refresh_dashboard(self))
        self.run_scan_dashboard_btn.clicked.connect(lambda: dashboard_handlers.run_scan_from_dashboard(self))
        self.dashboard_firewall_detail_btn.clicked.connect(lambda: dashboard_handlers.show_firewall_violations_detail(self))
        self.refresh_graph_btn.clicked.connect(lambda: graph_tab.refresh_graph(self))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.run_team_mode_btn.clicked.connect(lambda: command_handlers.run_fix_team_mode(self))
        self.load_pending_btn.clicked.connect(lambda: approve_handlers.load_pending_plan(self))
        self.save_approvals_btn.clicked.connect(lambda: approve_handlers.save_approvals(self))
        self.apply_approved_btn.clicked.connect(lambda: command_handlers.run_apply_approved(self))
        self.apply_from_report_btn.clicked.connect(lambda: command_handlers.run_apply_from_report(self))
        self.approvals_table.itemSelectionChanged.connect(lambda: approve_handlers.on_approval_row_selected(self))
        self.approvals_table.cellClicked.connect(lambda r, c: approve_handlers.on_approval_row_selected(self))
        self.chat_send_btn.clicked.connect(lambda: chat_handlers.send_chat_message(self))
        self.chat_cancel_btn.clicked.connect(lambda: chat_handlers.cancel_chat_request(self))
        self.chat_input.submit_requested.connect(lambda: chat_handlers.send_chat_message(self))
        if hasattr(self, "chat_mode_agent_btn"):
            self.chat_mode_agent_btn.clicked.connect(lambda: chat_handlers.focus_agent_mode(self))
            self.chat_mode_market_btn.clicked.connect(lambda: chat_handlers.focus_market_mode(self))
            self.chat_mode_learn_btn.clicked.connect(lambda: chat_handlers.focus_learn_mode(self))
        if hasattr(self, "chat_focus_terminal_btn"):
            self.chat_focus_terminal_btn.clicked.connect(
                lambda: chat_handlers.focus_terminal_mode(self)
            )
            self.chat_focus_approvals_btn.clicked.connect(
                lambda: chat_handlers.focus_approvals_mode(self)
            )
        self.chat_clear_btn.clicked.connect(lambda: chat_handlers.clear_chat_session(self))
        self.chat_apply_btn.clicked.connect(lambda: chat_handlers.apply_pending_chat_plan(self))
        self.chat_reject_btn.clicked.connect(lambda: chat_handlers.reject_pending_chat_plan(self))
        self.chat_diff_btn.clicked.connect(lambda: chat_handlers.preview_pending_chat_plan(self))
        self.chat_feedback_helpful_btn.clicked.connect(lambda: chat_handlers.submit_chat_feedback(self, helpful=True))
        self.chat_feedback_not_btn.clicked.connect(lambda: chat_handlers.submit_chat_feedback(self, helpful=False))
        self.market_live_check.toggled.connect(lambda c: market_handlers.on_market_live_toggled(self, c))
        self.market_auto_check.toggled.connect(lambda c: market_handlers.on_market_auto_toggled(self, c))
        self.market_micro_train_check.toggled.connect(lambda _c: market_handlers.on_market_prefs_changed(self))
        self.market_explore_check.toggled.connect(lambda _c: market_handlers.on_market_prefs_changed(self))
        self.market_explore_cap_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_explore_reset_btn.clicked.connect(lambda: market_handlers.reset_explore_counter(self))
        self.market_kind_combo.currentTextChanged.connect(lambda _t: market_handlers.on_market_prefs_changed(self))
        self.market_spot_add_btn.clicked.connect(lambda: market_handlers.add_spot_symbol(self))
        self.market_spot_del_btn.clicked.connect(lambda: market_handlers.remove_spot_symbol(self))
        self.market_spot_fill_btn.clicked.connect(lambda: market_handlers.fill_spot_from_balances(self))
        self.market_spot_edit.returnPressed.connect(lambda: market_handlers.add_spot_symbol(self))
        self.market_futures_add_btn.clicked.connect(lambda: market_handlers.add_futures_symbol(self))
        self.market_futures_del_btn.clicked.connect(lambda: market_handlers.remove_futures_symbol(self))
        self.market_futures_edit.returnPressed.connect(lambda: market_handlers.add_futures_symbol(self))
        self.market_candle_combo.currentTextChanged.connect(lambda _t: market_handlers.on_market_prefs_changed(self))
        self.market_horizon_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_exec_1m_check.toggled.connect(lambda _c: market_handlers.on_market_prefs_changed(self))
        self.market_tp_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_sl_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_trail_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_interval_spin.valueChanged.connect(lambda _v: market_handlers.on_market_prefs_changed(self))
        self.market_tick_btn.clicked.connect(lambda: market_handlers.run_market_tick(self))
        self.market_drop_orphans_btn.clicked.connect(lambda: market_handlers.drop_market_orphans(self))
        self.market_clear_btn.clicked.connect(lambda: market_handlers.clear_market_log(self))
        self.notes_save_btn.clicked.connect(lambda: notes_handlers.save_notes(self))
        self.ollama_start_btn.clicked.connect(lambda: ollama_handlers.start_ollama_server(self))
        self.ollama_stop_btn.clicked.connect(lambda: ollama_handlers.stop_ollama_server(self))
        self.ollama_cuda_check.toggled.connect(lambda c: ollama_handlers.on_ollama_cuda_toggled(self, c))
        self.ollama_vulkan_check.toggled.connect(lambda c: ollama_handlers.on_ollama_vulkan_toggled(self, c))
        self.ollama_refresh_models_btn.clicked.connect(lambda: ollama_handlers.refresh_ollama_models(self, user_initiated=True))
        self.chat_ollama_refresh_btn.clicked.connect(lambda: ollama_handlers.refresh_ollama_models(self, user_initiated=True))
        if hasattr(self, "chat_api_preset_combo"):
            self.chat_api_preset_combo.currentIndexChanged.connect(
                lambda *_: chat_handlers.on_chat_api_preset_changed(self)
            )
        self.ollama_install_btn.clicked.connect(lambda: ollama_handlers.install_selected_ollama_model(self))
        self.ollama_installed_combo.currentTextChanged.connect(lambda v: ollama_handlers.sync_chat_model_from_installed(self, v))
        self.ml_torch_refresh_btn.clicked.connect(
            lambda: ml_handlers.refresh_ml_status(self, run_smoke=True, append_log=True)
        )
        self.ml_torch_smoke_btn.clicked.connect(
            lambda: ml_handlers.refresh_ml_status(self, run_smoke=True, append_log=True)
        )
        self.ml_market_refresh_btn.clicked.connect(
            lambda: ml_handlers.refresh_market_learning(self, append_log=True)
        )
        self.ml_torch_device_combo.currentTextChanged.connect(lambda t: ml_handlers.on_ml_device_changed(self, t))
        self._command_service.command_started.connect(lambda c: command_handlers.on_command_started(self, c))
        self._command_service.output_line.connect(lambda line: command_handlers.append_stdout(self, line))
        self._command_service.error_line.connect(lambda line: command_handlers.append_stderr(self, line))
        self._command_service.command_finished.connect(lambda c: command_handlers.on_command_finished(self, c))
        self._command_service.state_changed.connect(lambda s: command_handlers.on_state_changed(self, s))
        self._sync_preview()
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._first_run_prompt_pending:
            self._first_run_prompt_pending = False
            QTimer.singleShot(150, self._prompt_project_root_if_empty)
        QTimer.singleShot(400, self._check_ollama_on_startup)

    def _check_ollama_on_startup(self) -> None:
        """If Ollama not running, auto-start it in background (stay on Chat)."""
        if self._is_closing:
            return
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        if not self._api.is_ollama_healthy():
            # Chat-first: do not steal focus to Models; start Ollama quietly.
            if hasattr(self, "status_label"):
                self.status_label.setText("Ollama не запущен — стартую в фоне…")
            ollama_handlers.start_ollama_server(self)

    def _prompt_project_root_if_empty(self) -> None:
        """First-run UX (B.12): when project root is empty, open folder picker and show hint."""
        if self._is_closing:
            return
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        if not self.root_edit.text().strip():
            selected = QFileDialog.getExistingDirectory(
                self, 'Выберите корень проекта', default_start_directory()
            )
            if selected:
                self._set_project_root(selected)

    def _set_project_root(self, value: str) -> None:
        self.root_edit.setText(value)
        self._api.set_project_root(value)
        self._settings.set_project_root(value)
        load_project_dotenv(value or ".")
        self._refresh_openai_api_status()
        is_empty = not (value or '').strip()
        self._first_run_hint.setVisible(is_empty)
        root_resolved = str(Path(value or '.').resolve()) if value else ''
        if hasattr(self, '_terminal_cwd'):
            self._terminal_cwd = root_resolved
        chat_handlers.load_chat_preferences(self)
        market_handlers.load_market_preferences(self)
        chat_handlers.refresh_chat_goal_view(self)
        dashboard_handlers.refresh_dashboard(self)
        notes_handlers.load_notes(self)
        if self.tabs.currentIndex() == self.graph_tab_index:
            graph_tab.refresh_graph(self)
        self._sync_preview()
        if self._command_service.state == "idle":
            command_handlers.on_state_changed(self, "idle")

    def _refresh_openai_api_status(self) -> None:
        if not hasattr(self, "openai_api_status"):
            return
        from eurika.utils.llm_presets import detect_llm_api_preset, get_llm_api_preset

        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        base = (os.environ.get("OPENAI_BASE_URL") or "").strip()
        model = (os.environ.get("OPENAI_MODEL") or "").strip() or "—"
        ui_model = ""
        if hasattr(self, "chat_openai_model"):
            ui_model = self.chat_openai_model.text().strip()
        if ui_model:
            model = ui_model
        preset_id = ""
        if hasattr(self, "chat_api_preset_combo"):
            preset_id = str(self.chat_api_preset_combo.currentData() or "")
        if not preset_id:
            preset_id = detect_llm_api_preset(base)
        preset = get_llm_api_preset(preset_id)
        if preset is not None:
            base = preset.base_url
            if model in {"—", ""}:
                model = preset.default_model
        if not base:
            base = "https://api.openai.com/v1"
        if key:
            label = preset.label if preset else "OpenAI-compatible"
            self.openai_api_status.setText(f"API: configured · {label} ({model})")
            tip = f"OPENAI_BASE_URL={base}"
            if preset and preset.key_hint:
                tip += f"\nkey: {preset.key_hint}"
            self.openai_api_status.setToolTip(tip)
        else:
            hint = "add OPENAI_API_KEY to .env"
            if preset and preset.key_hint:
                hint = f"{hint} ({preset.key_hint})"
            self.openai_api_status.setText(f"API: not set — {hint}")
            self.openai_api_status.setToolTip(
                "Ключ в .env как OPENAI_API_KEY; preset задаёт только BASE_URL/модель. "
                "см. docs/CHAT.md § Free / cloud LLM presets"
            )

    def _select_root(self) -> None:
        start = (self.root_edit.text() or '').strip()
        if not start or not Path(start).exists():
            start = default_start_directory()
        selected = QFileDialog.getExistingDirectory(self, 'Select project root', start)
        if selected:
            self._set_project_root(selected)

    def _on_root_edited(self) -> None:
        self._set_project_root(self.root_edit.text().strip())

    def _get_current_command(self) -> str:
        """CLI command (not display text)."""
        data = getattr(self.command_combo, "currentData", lambda: None)()
        return data if data else self.command_combo.currentText()

    def _get_runtime_mode(self) -> str:
        """Runtime mode value (assist/hybrid/auto)."""
        data = getattr(self.runtime_mode_combo, "currentData", lambda: None)()
        return data if data else (self.runtime_mode_combo.currentText() or "assist").lower()

    def _sync_preview(self) -> None:
        cmd = self._get_current_command()
        root = self.root_edit.text().strip() or '.'
        if cmd == 'cycle':
            extra = []
            if self.dry_run_check.isChecked():
                extra.append('--dry-run')
            if self.no_llm_check.isChecked():
                extra.append('--no-llm')
            rm_val = self._get_runtime_mode() if getattr(self, "runtime_mode_combo", None) else "assist"
            if rm_val and rm_val != "assist":
                extra.append(f"--runtime-mode {rm_val}")
            extra_str = " " + " ".join(extra) if extra else ""
            self.preview_label.setText(
                f"scan → doctor → report-snapshot → fix{extra_str} → learning-kpi → whitelist-draft"
            )
            self.module_edit.setEnabled(False)
            return
        parts = [f'eurika {cmd}']
        if cmd == 'explain':
            mod = self.module_edit.text().strip() or '<module>'
            parts.append(mod)
        parts.append(root)
        if cmd in {'report-snapshot', 'learning-kpi'}:
            self.preview_label.setText(' '.join(parts))
            self.module_edit.setEnabled(False)
            return
        if cmd in {'whitelist-draft', 'campaign-undo'}:
            self.preview_label.setText(' '.join(parts))
            self.module_edit.setEnabled(False)
            return
        if cmd == 'learn-github':
            if getattr(self, 'learn_light_check', None) and self.learn_light_check.isChecked():
                parts.append('--light')
            if getattr(self, 'learn_scan_check', None) and self.learn_scan_check.isChecked():
                parts.append('--scan')
            if getattr(self, 'learn_build_patterns_check', None) and self.learn_build_patterns_check.isChecked():
                parts.append('--build-patterns')
            lim = getattr(self, 'learn_limit_spin', None)
            if lim and lim.value() > 0:
                parts.extend(['--limit-repos', str(lim.value())])
            self.preview_label.setText(' '.join(parts))
            self.module_edit.setEnabled(False)
            return
        if cmd in {'clean-imports', 'self-check'}:
            self.preview_label.setText(' '.join(parts))
            self.module_edit.setEnabled(False)
            return
        if cmd in {'doctor', 'fix', 'cycle', 'explain'}:
            parts.extend(['--window', str(self.window_spin.value())])
        if self.dry_run_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--dry-run')
        if self.no_llm_check.isChecked() and cmd in {'doctor', 'cycle'}:
            parts.append('--no-llm')
        if self.no_clean_imports_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--no-clean-imports')
        if self.no_code_smells_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--no-code-smells')
        if self.allow_low_risk_campaign_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--allow-low-risk-campaign')
        if self.team_mode_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--team-mode')
        rm_val = self._get_runtime_mode() if getattr(self, "runtime_mode_combo", None) else "assist"
        if rm_val and rm_val not in ("", "assist") and cmd in {"fix", "cycle"}:
            parts.extend(["--runtime-mode", rm_val])
        if getattr(self, 'use_llm_extract_check', None) and self.use_llm_extract_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('[LLM extract]')
        self.preview_label.setText(' '.join(parts))
        self.module_edit.setEnabled(cmd == 'explain')
        self._sync_learn_visibility()

    def _sync_learn_visibility(self) -> None:
        """Show/hide learn-github options based on command."""
        cmd = self._get_current_command()
        show_learn = cmd == "learn-github"
        learn_grp = getattr(self, "learn_group", None)
        if learn_grp is not None:
            learn_grp.setVisible(show_learn)

    def _resolve_ollama_model_for_command(self) -> str:
        """Model for doctor/fix/cycle: prefer Installed combo (Models tab), else Chat model settings."""
        installed = (self.ollama_installed_combo.currentText() or '').strip()
        if installed and (not installed.startswith('(')):
            return installed
        return (self.chat_ollama_model.currentText() or '').strip()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure background workers/processes are terminated before window closes."""
        self._is_closing = True
        if self._ollama_health_timer.isActive():
            self._ollama_health_timer.stop()
        timer = getattr(self, "_market_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        # MarketTickWorker is a QThread child of MainWindow — must finish before destroy
        # or Qt aborts: "QThread: Destroyed while thread is still running".
        market_worker = getattr(self, "_market_tick_worker", None)
        if market_worker is not None:
            try:
                if market_worker.isRunning():
                    market_worker.requestInterruption()
                    if not market_worker.wait(8000):
                        market_worker.terminate()
                        market_worker.wait(1500)
            except RuntimeError:
                pass
            self._market_tick_worker = None
            self._market_tick_busy = False
        self._command_service.shutdown(timeout_ms=1200)
        if self._terminal_process is not None:
            ollama_handlers.shutdown_qprocess(self._terminal_process)
        ollama_handlers.shutdown_qprocess(self._ollama_task_process)
        ollama_handlers.shutdown_qprocess(self._ollama_process)
        if self._chat_worker is not None and self._chat_worker.isRunning():
            self._chat_worker.requestInterruption()
            self._chat_worker.wait(1500)
        self._chat_worker = None
        if self._graph_web_view is not None:
            try:
                self._graph_web_view.setHtml('<!DOCTYPE html><html><body></body></html>', 'about:blank')
            except Exception:
                pass
        super().closeEvent(event)