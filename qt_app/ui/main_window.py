"""Main window for Eurika Qt thin-shell UI."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QTabWidget, QVBoxLayout, QWidget
from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter
from qt_app.services.command_service import CommandService
from qt_app.services.settings_service import SettingsService
from .handlers import approve_handlers, chat_handlers, command_handlers, dashboard_handlers, notes_handlers, ollama_handlers
from .main_window_helpers import ChatWorker, default_start_directory
from .tabs import approve_tab, chat_tab, commands_tab, dashboard_tab, graph_tab, models_tab, notes_tab, terminal_tab

class MainWindow(QMainWindow):
    """Desktop-first shell for running core Eurika workflows."""

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
        self._pending_plan_token = ''
        self._pending_plan_fallback_active = False
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
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel('Project root:'))
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText('Select project root')
        top_row.addWidget(self.root_edit, 1)
        self.browse_btn = QPushButton('Browse')
        top_row.addWidget(self.browse_btn)
        root_layout.addLayout(top_row)
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, 1)
        commands_tab.build_commands_tab(self)
        dashboard_tab.build_dashboard_tab(self)
        graph_tab.build_graph_tab(self)
        approve_tab.build_approve_tab(self)
        models_tab.build_models_tab(self)
        chat_tab.build_chat_tab(self)
        terminal_tab.build_terminal_tab(self)
        notes_tab.build_notes_tab(self)
        self.status_label = QLabel('Idle')
        root_layout.addWidget(self.status_label)

    def _on_tab_changed(self, index: int) -> None:
        """Lazy-load Graph WebEngine when user first opens Graph tab."""
        if index == self.graph_tab_index:
            graph_tab.ensure_graph_widget(self)
            graph_tab.refresh_graph(self)

    def _wire_events(self) -> None:
        self.browse_btn.clicked.connect(self._select_root)
        self.root_edit.editingFinished.connect(self._on_root_edited)
        self.command_combo.currentTextChanged.connect(self._sync_preview)
        self.module_edit.textChanged.connect(self._sync_preview)
        self.window_spin.valueChanged.connect(self._sync_preview)
        self.dry_run_check.toggled.connect(self._sync_preview)
        self.no_llm_check.toggled.connect(self._sync_preview)
        self.no_clean_imports_check.toggled.connect(self._sync_preview)
        self.no_code_smells_check.toggled.connect(self._sync_preview)
        self.allow_low_risk_campaign_check.toggled.connect(self._sync_preview)
        self.team_mode_check.toggled.connect(self._sync_preview)
        self.run_btn.clicked.connect(lambda: command_handlers.run_command(self))
        self.stop_btn.clicked.connect(self._command_service.stop)
        self.refresh_dashboard_btn.clicked.connect(lambda: dashboard_handlers.refresh_dashboard(self))
        self.run_scan_dashboard_btn.clicked.connect(lambda: dashboard_handlers.run_scan_from_dashboard(self))
        self.dashboard_firewall_detail_btn.clicked.connect(lambda: dashboard_handlers.show_firewall_violations_detail(self))
        self.refresh_graph_btn.clicked.connect(lambda: graph_tab.refresh_graph(self))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.run_team_mode_btn.clicked.connect(lambda: command_handlers.run_fix_team_mode(self))
        self.load_pending_btn.clicked.connect(lambda: approve_handlers.load_pending_plan(self))
        self.save_approvals_btn.clicked.connect(lambda: approve_handlers.save_approvals(self))
        self.apply_approved_btn.clicked.connect(lambda: command_handlers.run_apply_approved(self))
        self.approvals_table.itemSelectionChanged.connect(lambda: approve_handlers.on_approval_row_selected(self))
        self.chat_send_btn.clicked.connect(lambda: chat_handlers.send_chat_message(self))
        self.chat_clear_btn.clicked.connect(lambda: chat_handlers.clear_chat_session(self))
        self.chat_apply_btn.clicked.connect(lambda: chat_handlers.apply_pending_chat_plan(self))
        self.chat_reject_btn.clicked.connect(lambda: chat_handlers.reject_pending_chat_plan(self))
        self.chat_feedback_helpful_btn.clicked.connect(lambda: chat_handlers.submit_chat_feedback(self, helpful=True))
        self.chat_feedback_not_btn.clicked.connect(lambda: chat_handlers.submit_chat_feedback(self, helpful=False))
        self.notes_save_btn.clicked.connect(lambda: notes_handlers.save_notes(self))
        self.ollama_start_btn.clicked.connect(lambda: ollama_handlers.start_ollama_server(self))
        self.ollama_stop_btn.clicked.connect(lambda: ollama_handlers.stop_ollama_server(self))
        self.ollama_refresh_models_btn.clicked.connect(lambda: ollama_handlers.refresh_ollama_models(self, user_initiated=True))
        self.ollama_install_btn.clicked.connect(lambda: ollama_handlers.install_selected_ollama_model(self))
        self.ollama_installed_combo.currentTextChanged.connect(lambda v: ollama_handlers.sync_chat_model_from_installed(self, v))
        self.ollama_search_refresh_btn.clicked.connect(lambda: ollama_handlers.refresh_ollama_catalog(self))
        self._command_service.command_started.connect(lambda c: command_handlers.on_command_started(self, c))
        self._command_service.output_line.connect(lambda l: command_handlers.append_stdout(self, l))
        self._command_service.error_line.connect(lambda l: command_handlers.append_stderr(self, l))
        self._command_service.command_finished.connect(lambda c: command_handlers.on_command_finished(self, c))
        self._command_service.state_changed.connect(lambda s: command_handlers.on_state_changed(self, s))
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._first_run_prompt_pending:
            self._first_run_prompt_pending = False
            QTimer.singleShot(150, self._prompt_project_root_if_empty)
        QTimer.singleShot(400, self._check_ollama_on_startup)

    def _check_ollama_on_startup(self) -> None:
        """If Ollama not running, switch to Models tab and auto-start it for doctor/fix/cycle."""
        if self._is_closing:
            return
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        if not self._api.is_ollama_healthy():
            self.tabs.setCurrentIndex(self.models_tab_index)
            ollama_handlers.start_ollama_server(self)

    def _prompt_project_root_if_empty(self) -> None:
        """First-run UX: when project root is empty, prompt user to select folder."""
        if self._is_closing:
            return
        if os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
            return
        if not self.root_edit.text().strip():
            selected = QFileDialog.getExistingDirectory(self, 'Select project root', default_start_directory())
            if selected:
                self._set_project_root(selected)

    def _set_project_root(self, value: str) -> None:
        self.root_edit.setText(value)
        self._api.set_project_root(value)
        self._settings.set_project_root(value)
        root_resolved = str(Path(value or '.').resolve()) if value else ''
        if hasattr(self, '_terminal_cwd'):
            self._terminal_cwd = root_resolved
        chat_handlers.load_chat_preferences(self)
        chat_handlers.refresh_chat_goal_view(self)
        dashboard_handlers.refresh_dashboard(self)
        notes_handlers.load_notes(self)
        if self.tabs.currentIndex() == self.graph_tab_index:
            graph_tab.refresh_graph(self)
        self._sync_preview()

    def _select_root(self) -> None:
        start = (self.root_edit.text() or '').strip()
        if not start or not Path(start).exists():
            start = default_start_directory()
        selected = QFileDialog.getExistingDirectory(self, 'Select project root', start)
        if selected:
            self._set_project_root(selected)

    def _on_root_edited(self) -> None:
        value = self.root_edit.text().strip()
        if value:
            self._set_project_root(value)

    def _sync_preview(self) -> None:
        cmd = self.command_combo.currentText()
        parts = [f'eurika {cmd}']
        root = self.root_edit.text().strip() or '.'
        if cmd == 'explain':
            mod = self.module_edit.text().strip() or '<module>'
            parts.append(mod)
        parts.append(root)
        if cmd in {'report-snapshot', 'learning-kpi'}:
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
        self.preview_label.setText(' '.join(parts))
        self.module_edit.setEnabled(cmd == 'explain')

    def _resolve_ollama_model_for_command(self) -> str:
        """Model for doctor/fix/cycle: prefer Installed combo (Models tab), else Chat model settings."""
        installed = (self.ollama_installed_combo.currentText() or '').strip()
        if installed and (not installed.startswith('(')):
            return installed
        return (self.chat_ollama_model.text() or '').strip()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure background workers/processes are terminated before window closes."""
        self._is_closing = True
        if self._ollama_health_timer.isActive():
            self._ollama_health_timer.stop()
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