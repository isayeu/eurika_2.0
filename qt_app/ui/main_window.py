"""Main window for Eurika Qt thin-shell UI."""
from __future__ import annotations
import json
import re
from typing import Any
from PySide6.QtCore import QProcess, QProcessEnvironment, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QProgressBar, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter
from qt_app.services.command_service import CommandService
from qt_app.services.settings_service import SettingsService
_ANSI_STRIP_RE = re.compile('\\x1b\\[[0-?]*[ -/]*[@-~]|\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)|\\x1b[PX^_][^\\x1b]*\\x1b\\\\', re.DOTALL)
_OLLAMA_PULL_PCT_RE = re.compile('(\\d+)\\s*%')
_OLLAMA_PULL_MB_GB_RE = re.compile('(\\d+)\\s*MB\\s*/\\s*([\\d.]+)\\s*GB')
_TUI_COMMANDS = frozenset(('htop', 'top', 'vim', 'vi', 'nano', 'less', 'more', 'watch', 'mc'))

def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for display in plain text widget."""
    return _ANSI_STRIP_RE.sub('', text)

def _parse_ollama_pull_progress(line: str) -> tuple[int, str] | None:
    """Extract progress (0-100) and status text from ollama pull stderr line."""
    pct = None
    m = _OLLAMA_PULL_PCT_RE.search(line)
    if m:
        pct = min(100, max(0, int(m.group(1))))
    m_mb_gb = _OLLAMA_PULL_MB_GB_RE.search(line)
    if pct is None and m_mb_gb:
        mb, gb = (float(m_mb_gb.group(1)), float(m_mb_gb.group(2)))
        if gb > 0:
            pct = min(100, int(100 * mb / (gb * 1024)))
    if pct is None:
        return None
    parts = []
    if m_mb_gb:
        parts.append(f'{m_mb_gb.group(1)} MB / {m_mb_gb.group(2)} GB')
    if (sp := re.search('([\\d.]+)\\s*MB/s', line)):
        parts.append(f'{sp.group(1)} MB/s')
    if (eta := re.search('(\\d+m\\d+s|\\d+m|\\d+s)', line)):
        parts.append(eta.group(1))
    label = ' • '.join(parts) if parts else f'{pct}%'
    return (pct, label)

def _is_tui_command(cmd: str) -> bool:
    """Check if command is a known TUI program (requires real PTY)."""
    first = (cmd.strip().split() or [''])[0].lower()
    name = first.split('/')[-1] if first else ''
    return name in _TUI_COMMANDS

class ChatWorker(QThread):
    """Background worker for chat requests to avoid UI freeze."""
    finished_payload = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, api: EurikaApiAdapter, message: str, history: list[dict[str, str]], provider: str, openai_model: str, ollama_model: str, timeout_sec: int) -> None:
        super().__init__()
        self._api = api
        self._message = message
        self._history = history
        self._provider = provider
        self._openai_model = openai_model
        self._ollama_model = ollama_model
        self._timeout_sec = timeout_sec

    def run(self) -> None:
        try:
            result = self._api.chat_send(message=self._message, history=self._history, provider=self._provider, openai_model=self._openai_model, ollama_model=self._ollama_model, timeout_sec=self._timeout_sec)
            self.finished_payload.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

class MainWindow(QMainWindow):
    """Desktop-first shell for running core Eurika workflows."""
    AVAILABLE_OLLAMA_MODELS = ['qwen2.5-coder:7b', 'qwen2.5-coder:14b', 'llama3.1:8b', 'llama3.2:3b', 'mistral:7b', 'phi4:latest', 'deepseek-r1:8b', 'deepseek-r1:14b', 'gemma2:9b', 'codellama:13b']

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Eurika Qt')
        self.resize(1100, 760)
        self._settings = SettingsService()
        initial_root = self._settings.get_project_root() or '.'
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
        self._wire_ollama_process()
        self._wire_ollama_task_process()
        self._build_ui()
        self._wire_events()
        self._set_project_root(initial_root)
        self._setup_ollama_health_timer()

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
        self._build_commands_tab()
        self._build_dashboard_tab()
        self._build_approve_tab()
        self._build_models_tab()
        self._build_chat_tab()
        self.status_label = QLabel('Idle')
        root_layout.addWidget(self.status_label)

    def _build_commands_tab(self) -> None:
        self.commands_tab = tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QGroupBox('Core Command Panel')
        controls_layout = QFormLayout(controls)
        self.command_combo = QComboBox()
        self.command_combo.addItems(['scan', 'doctor', 'fix', 'cycle', 'explain'])
        controls_layout.addRow('Command', self.command_combo)
        self.module_edit = QLineEdit()
        self.module_edit.setPlaceholderText('Required for explain: eurika/api/serve.py')
        controls_layout.addRow('Module', self.module_edit)
        self.window_spin = QSpinBox()
        self.window_spin.setRange(1, 100)
        self.window_spin.setValue(5)
        controls_layout.addRow('Window', self.window_spin)
        options_row = QHBoxLayout()
        self.dry_run_check = QCheckBox('--dry-run')
        self.no_llm_check = QCheckBox('--no-llm')
        self.no_clean_imports_check = QCheckBox('--no-clean-imports')
        self.team_mode_check = QCheckBox('--team-mode')
        self.team_mode_check.setToolTip('Propose only: save plan to .eurika/pending_plan.json, then use Approvals tab')
        options_row.addWidget(self.dry_run_check)
        options_row.addWidget(self.no_llm_check)
        options_row.addWidget(self.no_clean_imports_check)
        options_row.addWidget(self.team_mode_check)
        options_row.addStretch(1)
        controls_layout.addRow('Options', options_row)
        action_row = QHBoxLayout()
        self.preview_label = QLabel('eurika scan .')
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        action_row.addWidget(self.preview_label, 1)
        self.run_btn = QPushButton('Run')
        self.stop_btn = QPushButton('Stop')
        self.stop_btn.setEnabled(False)
        action_row.addWidget(self.run_btn)
        action_row.addWidget(self.stop_btn)
        controls_layout.addRow('Execute', action_row)
        layout.addWidget(controls)
        terminal_box = QGroupBox('Live output')
        terminal_layout = QVBoxLayout(terminal_box)
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        terminal_layout.addWidget(self.terminal)
        layout.addWidget(terminal_box, 1)
        self.tabs.addTab(tab, 'Commands')

    def _build_dashboard_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        refresh_row = QHBoxLayout()
        self.refresh_dashboard_btn = QPushButton('Refresh dashboard')
        refresh_row.addWidget(self.refresh_dashboard_btn)
        refresh_row.addStretch(1)
        layout.addLayout(refresh_row)
        metrics = QGroupBox('Summary')
        grid = QGridLayout(metrics)
        self.dashboard_modules = QLabel('-')
        self.dashboard_deps = QLabel('-')
        self.dashboard_cycles = QLabel('-')
        self.dashboard_risk = QLabel('-')
        self.dashboard_maturity = QLabel('-')
        self.dashboard_trends = QLabel('-')
        grid.addWidget(QLabel('Modules'), 0, 0)
        grid.addWidget(self.dashboard_modules, 0, 1)
        grid.addWidget(QLabel('Dependencies'), 1, 0)
        grid.addWidget(self.dashboard_deps, 1, 1)
        grid.addWidget(QLabel('Cycles'), 2, 0)
        grid.addWidget(self.dashboard_cycles, 2, 1)
        grid.addWidget(QLabel('Risk score'), 3, 0)
        grid.addWidget(self.dashboard_risk, 3, 1)
        grid.addWidget(QLabel('Maturity'), 4, 0)
        grid.addWidget(self.dashboard_maturity, 4, 1)
        grid.addWidget(QLabel('Trends'), 5, 0)
        grid.addWidget(self.dashboard_trends, 5, 1)
        layout.addWidget(metrics)
        risks_group = QGroupBox('Top risks')
        risks_layout = QVBoxLayout(risks_group)
        self.dashboard_risks_text = QTextEdit()
        self.dashboard_risks_text.setReadOnly(True)
        self.dashboard_risks_text.setMaximumHeight(100)
        self.dashboard_risks_text.setPlaceholderText('Run scan to see risks')
        risks_layout.addWidget(self.dashboard_risks_text)
        layout.addWidget(risks_group)
        self_guard_group = QGroupBox('SELF-GUARD (R5)')
        self_guard_layout = QVBoxLayout(self_guard_group)
        self.dashboard_self_guard_text = QTextEdit()
        self.dashboard_self_guard_text.setReadOnly(True)
        self.dashboard_self_guard_text.setMaximumHeight(80)
        self.dashboard_self_guard_text.setPlaceholderText('Run scan to see SELF-GUARD status')
        self_guard_layout.addWidget(self.dashboard_self_guard_text)
        layout.addWidget(self_guard_group)
        risk_pred_group = QGroupBox('Risk prediction (R5)')
        risk_pred_layout = QVBoxLayout(risk_pred_group)
        self.dashboard_risk_pred_text = QTextEdit()
        self.dashboard_risk_pred_text.setReadOnly(True)
        self.dashboard_risk_pred_text.setMaximumHeight(70)
        self.dashboard_risk_pred_text.setPlaceholderText('Run scan to see top modules by regression risk')
        risk_pred_layout.addWidget(self.dashboard_risk_pred_text)
        layout.addWidget(risk_pred_group)
        ops_group = QGroupBox('Operational metrics')
        ops_layout = QFormLayout(ops_group)
        self.dashboard_apply_rate = QLabel('-')
        self.dashboard_rollback_rate = QLabel('-')
        self.dashboard_median_verify = QLabel('-')
        ops_layout.addRow('Apply rate', self.dashboard_apply_rate)
        ops_layout.addRow('Rollback rate', self.dashboard_rollback_rate)
        ops_layout.addRow('Median verify (ms)', self.dashboard_median_verify)
        layout.addWidget(ops_group)
        learning = QGroupBox('Learning insights')
        learning_layout = QVBoxLayout(learning)
        self.learning_widget_text = QTextEdit()
        self.learning_widget_text.setReadOnly(True)
        self.learning_widget_text.setPlaceholderText('Learning stats will appear after fix/cycle runs (verify_success by smell|action|target).')
        learning_layout.addWidget(self.learning_widget_text)
        layout.addWidget(learning)
        self.tabs.addTab(tab, 'Dashboard')

    def _build_approve_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel('1. Run fix with --team-mode (Commands tab) → 2. Load plan → 3. Approve/reject per row → 4. Save → 5. Run apply-approved')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: gray; font-size: 11px;')
        layout.addWidget(hint)
        top = QHBoxLayout()
        self.run_team_mode_btn = QPushButton('Run fix (team-mode)')
        self.run_team_mode_btn.setToolTip('Run eurika fix . --team-mode to create pending plan')
        self.load_pending_btn = QPushButton('Load pending plan')
        self.save_approvals_btn = QPushButton('Save approve/reject')
        self.apply_approved_btn = QPushButton('Run apply-approved')
        top.addWidget(self.run_team_mode_btn)
        top.addWidget(self.load_pending_btn)
        top.addWidget(self.save_approvals_btn)
        top.addWidget(self.apply_approved_btn)
        top.addStretch(1)
        layout.addLayout(top)
        self.approvals_table = QTableWidget(0, 5)
        self.approvals_table.setHorizontalHeaderLabels(['#', 'Target', 'Kind', 'Risk', 'Decision'])
        header = self.approvals_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.approvals_table, 1)
        self.tabs.addTab(tab, 'Approvals')

    def _build_models_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        ollama_box = QGroupBox('Ollama server')
        ollama_layout = QFormLayout(ollama_box)
        self.ollama_hsa_edit = QLineEdit('10.3.0')
        self.ollama_rocr_edit = QLineEdit('0')
        self.ollama_hip_edit = QLineEdit('0')
        ollama_layout.addRow('HSA_OVERRIDE_GFX_VERSION', self.ollama_hsa_edit)
        ollama_layout.addRow('ROCR_VISIBLE_DEVICES', self.ollama_rocr_edit)
        ollama_layout.addRow('HIP_VISIBLE_DEVICES', self.ollama_hip_edit)
        ollama_row = QHBoxLayout()
        self.ollama_start_btn = QPushButton('Start Ollama')
        self.ollama_stop_btn = QPushButton('Stop Ollama')
        self.ollama_stop_btn.setEnabled(False)
        self.ollama_status = QLabel('Ollama: stopped')
        ollama_row.addWidget(self.ollama_start_btn)
        ollama_row.addWidget(self.ollama_stop_btn)
        ollama_row.addWidget(self.ollama_status, 1)
        ollama_layout.addRow('Control', ollama_row)
        self.ollama_health = QLabel('API: unknown')
        ollama_layout.addRow('Health', self.ollama_health)
        self.ollama_installed_combo = QComboBox()
        self.ollama_installed_combo.setEditable(False)
        self.ollama_installed_combo.addItem('(no local models)')
        refresh_models_row = QHBoxLayout()
        self.ollama_refresh_models_btn = QPushButton('Refresh installed')
        refresh_models_row.addWidget(self.ollama_installed_combo, 1)
        refresh_models_row.addWidget(self.ollama_refresh_models_btn)
        ollama_layout.addRow('Installed', refresh_models_row)
        self.ollama_available_combo = QComboBox()
        install_row = QHBoxLayout()
        self.ollama_search_edit = QLineEdit('qwen')
        self.ollama_search_refresh_btn = QPushButton('Filter catalog')
        self.ollama_custom_model_edit = QLineEdit()
        self.ollama_custom_model_edit.setPlaceholderText('custom model (e.g. deepseek-r1:14b)')
        self.ollama_install_btn = QPushButton('Install selected')
        install_row.addWidget(self.ollama_search_edit)
        install_row.addWidget(self.ollama_search_refresh_btn)
        install_row.addWidget(self.ollama_custom_model_edit)
        install_row.addWidget(self.ollama_available_combo, 1)
        install_row.addWidget(self.ollama_install_btn)
        ollama_layout.addRow('Available', install_row)
        self.ollama_install_status = QLabel('Install: idle')
        ollama_layout.addRow('Install status', self.ollama_install_status)
        self.ollama_pull_progress = QProgressBar()
        self.ollama_pull_progress.setRange(0, 100)
        self.ollama_pull_progress.setValue(0)
        self.ollama_pull_progress.setFormat('%p%')
        self.ollama_pull_progress_label = QLabel('')
        self.ollama_pull_progress_label.setStyleSheet('color: gray; font-size: 11px;')
        pull_progress_row = QWidget()
        pull_progress_layout = QHBoxLayout(pull_progress_row)
        pull_progress_layout.setContentsMargins(0, 0, 0, 0)
        pull_progress_layout.addWidget(self.ollama_pull_progress, 1)
        pull_progress_layout.addWidget(self.ollama_pull_progress_label)
        self.ollama_pull_progress_row = pull_progress_row
        self.ollama_pull_progress_row.setVisible(False)
        ollama_layout.addRow('Pull progress', self.ollama_pull_progress_row)
        self.ollama_output = QTextEdit()
        self.ollama_output.setReadOnly(True)
        self.ollama_output.setPlaceholderText('`ollama serve` output will appear here.')
        self.ollama_output.setMinimumHeight(80)
        ollama_layout.addRow('Output', self.ollama_output)
        layout.addWidget(ollama_box)
        controls = QGroupBox('Chat model settings')
        controls_layout = QFormLayout(controls)
        self.chat_provider_combo = QComboBox()
        self.chat_provider_combo.addItems(['auto', 'openai', 'ollama'])
        controls_layout.addRow('Provider', self.chat_provider_combo)
        self.chat_openai_model = QLineEdit()
        self.chat_openai_model.setPlaceholderText('e.g. gpt-4o-mini or mistralai/...')
        controls_layout.addRow('OpenAI/OpenRouter model', self.chat_openai_model)
        self.chat_ollama_model = QLineEdit()
        self.chat_ollama_model.setPlaceholderText('e.g. qwen2.5-coder:7b')
        controls_layout.addRow('Ollama model', self.chat_ollama_model)
        self.chat_timeout_spin = QSpinBox()
        self.chat_timeout_spin.setRange(0, 9999)
        self.chat_timeout_spin.setSpecialValueText('∞ (unlimited)')
        self.chat_timeout_spin.setValue(30)
        controls_layout.addRow('Timeout sec', self.chat_timeout_spin)
        layout.addWidget(controls)
        self.tabs.addTab(tab, 'Models')

    def _build_chat_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        history_box = QGroupBox('Session chat history')
        history_layout = QVBoxLayout(history_box)
        self.chat_goal_view = QTextEdit()
        self.chat_goal_view.setReadOnly(True)
        self.chat_goal_view.setMinimumHeight(70)
        self.chat_goal_view.setPlaceholderText('Interpreted goal/confidence will appear here after chat requests.')
        history_layout.addWidget(self.chat_goal_view)
        self.chat_transcript = QTextEdit()
        self.chat_transcript.setReadOnly(True)
        history_layout.addWidget(self.chat_transcript)
        layout.addWidget(history_box, 1)
        compose_box = QGroupBox('Send message')
        compose_layout = QVBoxLayout(compose_box)
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText('Ask Eurika about architecture or request refactor guidance...')
        self.chat_input.setMinimumHeight(80)
        compose_layout.addWidget(self.chat_input)
        self.chat_pending_label = QLabel('Pending plan: none')
        self.chat_pending_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        compose_layout.addWidget(self.chat_pending_label)
        buttons = QHBoxLayout()
        self.chat_send_btn = QPushButton('Send')
        self.chat_clear_btn = QPushButton('Clear session')
        self.chat_apply_btn = QPushButton('Apply')
        self.chat_reject_btn = QPushButton('Reject')
        self.chat_apply_btn.setEnabled(False)
        self.chat_reject_btn.setEnabled(False)
        buttons.addWidget(self.chat_send_btn)
        buttons.addWidget(self.chat_clear_btn)
        buttons.addWidget(self.chat_apply_btn)
        buttons.addWidget(self.chat_reject_btn)
        buttons.addStretch(1)
        compose_layout.addLayout(buttons)
        io_split = QSplitter(Qt.Vertical)
        io_split.addWidget(history_box)
        io_split.addWidget(compose_box)
        io_split.setChildrenCollapsible(False)
        io_split.setStretchFactor(0, 3)
        io_split.setStretchFactor(1, 2)
        layout.addWidget(io_split, 1)
        self.tabs.addTab(tab, 'Chat')
        self._build_terminal_tab()

    def _build_terminal_tab(self) -> None:
        """Terminal tab with minimal shell emulator: input + output."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        emulator_box = QGroupBox('Terminal')
        emulator_box.setStyleSheet('QGroupBox { color: #0f0; }')
        emulator_layout = QVBoxLayout(emulator_box)
        terminal_style = 'background-color: #000; color: #0f0; font-family: monospace;'
        self.terminal_emulator_output = QTextEdit()
        self.terminal_emulator_output.setReadOnly(True)
        self.terminal_emulator_output.setStyleSheet(terminal_style)
        self.terminal_emulator_output.setPlaceholderText('Output of shell commands. Cwd = project root.')
        emulator_layout.addWidget(self.terminal_emulator_output, 1)
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel('$'))
        self.terminal_emulator_input = QLineEdit()
        self.terminal_emulator_input.setStyleSheet(terminal_style)
        self.terminal_emulator_input.setPlaceholderText('Enter command and press Return (e.g. ls, pwd, eurika scan .)')
        self.terminal_emulator_input.returnPressed.connect(self._run_terminal_emulator_command)
        input_row.addWidget(self.terminal_emulator_input, 1)
        self.terminal_emulator_btn = QPushButton('Run')
        self.terminal_emulator_btn.clicked.connect(self._run_terminal_emulator_command)
        input_row.addWidget(self.terminal_emulator_btn)
        self.terminal_emulator_stop_btn = QPushButton('Stop')
        self.terminal_emulator_stop_btn.setEnabled(False)
        self.terminal_emulator_stop_btn.clicked.connect(self._stop_terminal_emulator)
        input_row.addWidget(self.terminal_emulator_stop_btn)
        emulator_layout.addLayout(input_row)
        layout.addWidget(emulator_box, 1)
        self.tabs.addTab(tab, 'Terminal')
        self._terminal_process: QProcess | None = None

    def _run_terminal_emulator_command(self) -> None:
        cmd = (self.terminal_emulator_input.text() or '').strip()
        if not cmd:
            return
        if _is_tui_command(cmd):
            self.terminal_emulator_output.append(f'$ {cmd}\n[Note] TUI programs (htop, vim, nano, less, etc.) need a real terminal.\nUse: ls, pwd, eurika scan ., or run htop in an external terminal.')
            self.terminal_emulator_input.clear()
            return
        cwd = self.root_edit.text().strip() or '.'
        self.terminal_emulator_output.append(f'$ {cmd}')
        self.terminal_emulator_input.clear()
        self.terminal_emulator_input.setEnabled(False)
        self.terminal_emulator_btn.setEnabled(False)
        self.terminal_emulator_stop_btn.setEnabled(True)
        self._terminal_process = QProcess(self)
        self._terminal_process.setWorkingDirectory(cwd)
        self._terminal_process.readyReadStandardOutput.connect(self._on_terminal_emulator_stdout)
        self._terminal_process.readyReadStandardError.connect(self._on_terminal_emulator_stderr)
        self._terminal_process.finished.connect(self._on_terminal_emulator_finished)
        self._terminal_process.start('bash', ['-c', cmd])

    def _on_terminal_emulator_stdout(self) -> None:
        if self._terminal_process:
            data = self._terminal_process.readAllStandardOutput().data().decode('utf-8', errors='replace')
            self.terminal_emulator_output.append(_strip_ansi(data).rstrip('\n'))

    def _on_terminal_emulator_stderr(self) -> None:
        if self._terminal_process:
            data = self._terminal_process.readAllStandardError().data().decode('utf-8', errors='replace')
            self.terminal_emulator_output.append(f'[stderr] {_strip_ansi(data).rstrip()}')

    def _on_terminal_emulator_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._terminal_process = None
        self.terminal_emulator_output.append(f'[done] exit_code={exit_code}')
        self.terminal_emulator_input.setEnabled(True)
        self.terminal_emulator_btn.setEnabled(True)
        self.terminal_emulator_stop_btn.setEnabled(False)

    def _stop_terminal_emulator(self) -> None:
        proc = self._terminal_process
        if proc is None or proc.state() == QProcess.NotRunning:
            return
        proc.terminate()
        if not proc.waitForFinished(3000):
            proc.kill()
            proc.waitForFinished(1000)

    def _wire_events(self) -> None:
        self.browse_btn.clicked.connect(self._select_root)
        self.root_edit.editingFinished.connect(self._on_root_edited)
        self.command_combo.currentTextChanged.connect(self._sync_preview)
        self.module_edit.textChanged.connect(self._sync_preview)
        self.window_spin.valueChanged.connect(self._sync_preview)
        self.dry_run_check.toggled.connect(self._sync_preview)
        self.no_llm_check.toggled.connect(self._sync_preview)
        self.no_clean_imports_check.toggled.connect(self._sync_preview)
        self.team_mode_check.toggled.connect(self._sync_preview)
        self.run_btn.clicked.connect(self._run_command)
        self.stop_btn.clicked.connect(self._command_service.stop)
        self.refresh_dashboard_btn.clicked.connect(self._refresh_dashboard)
        self.run_team_mode_btn.clicked.connect(self._run_fix_team_mode)
        self.load_pending_btn.clicked.connect(self._load_pending_plan)
        self.save_approvals_btn.clicked.connect(self._save_approvals)
        self.apply_approved_btn.clicked.connect(self._run_apply_approved)
        self.chat_send_btn.clicked.connect(self._send_chat_message)
        self.chat_clear_btn.clicked.connect(self._clear_chat_session)
        self.chat_apply_btn.clicked.connect(self._apply_pending_chat_plan)
        self.chat_reject_btn.clicked.connect(self._reject_pending_chat_plan)
        self.ollama_start_btn.clicked.connect(self._start_ollama_server)
        self.ollama_stop_btn.clicked.connect(self._stop_ollama_server)
        self.ollama_refresh_models_btn.clicked.connect(lambda: self._refresh_ollama_models(user_initiated=True))
        self.ollama_install_btn.clicked.connect(self._install_selected_ollama_model)
        self.ollama_installed_combo.currentTextChanged.connect(self._sync_chat_model_from_installed)
        self.ollama_search_refresh_btn.clicked.connect(self._refresh_ollama_catalog)
        self._command_service.command_started.connect(self._on_command_started)
        self._command_service.output_line.connect(self._append_stdout)
        self._command_service.error_line.connect(self._append_stderr)
        self._command_service.command_finished.connect(self._on_command_finished)
        self._command_service.state_changed.connect(self._on_state_changed)

    def _set_project_root(self, value: str) -> None:
        self.root_edit.setText(value)
        self._api.set_project_root(value)
        self._settings.set_project_root(value)
        self._load_chat_preferences()
        self._refresh_chat_goal_view()
        self._refresh_dashboard()
        self._sync_preview()

    def _select_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, 'Select project root', self.root_edit.text() or '.')
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
        if cmd in {'doctor', 'fix', 'cycle', 'explain'}:
            parts.extend(['--window', str(self.window_spin.value())])
        if self.dry_run_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--dry-run')
        if self.no_llm_check.isChecked() and cmd in {'doctor', 'cycle'}:
            parts.append('--no-llm')
        if self.no_clean_imports_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--no-clean-imports')
        if self.team_mode_check.isChecked() and cmd in {'fix', 'cycle'}:
            parts.append('--team-mode')
        self.preview_label.setText(' '.join(parts))
        self.module_edit.setEnabled(cmd == 'explain')

    def _resolve_ollama_model_for_command(self) -> str:
        """Model for doctor/fix/cycle: prefer Installed combo (Models tab), else Chat model settings."""
        installed = (self.ollama_installed_combo.currentText() or "").strip()
        if installed and not installed.startswith("("):
            return installed
        return (self.chat_ollama_model.text() or "").strip()

    def _run_command(self) -> None:
        ollama_model = self._resolve_ollama_model_for_command()
        self._command_service.start(
            command=self.command_combo.currentText(),
            project_root=self.root_edit.text().strip(),
            module=self.module_edit.text().strip(),
            window=self.window_spin.value(),
            dry_run=self.dry_run_check.isChecked(),
            no_llm=self.no_llm_check.isChecked(),
            no_clean_imports=self.no_clean_imports_check.isChecked(),
            team_mode=self.team_mode_check.isChecked(),
            ollama_model=ollama_model,
        )

    def _run_fix_team_mode(self) -> None:
        """Run eurika fix . --team-mode from Approvals tab."""
        root = self.root_edit.text().strip()
        if not root:
            QMessageBox.warning(self, 'Project root required', 'Set Project root before running fix.')
            return
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.commands_tab))
        ollama_model = self._resolve_ollama_model_for_command()
        self._command_service.start(
            command='fix',
            project_root=root,
            module='',
            window=self.window_spin.value(),
            dry_run=False,
            no_llm=False,
            no_clean_imports=self.no_clean_imports_check.isChecked(),
            team_mode=True,
            ollama_model=ollama_model,
        )

    def _run_apply_approved(self) -> None:
        root = self.root_edit.text().strip()
        if not root:
            QMessageBox.warning(self, 'Project root required', 'Set Project root before running apply-approved.')
            return
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.commands_tab))
        self._command_service.run_apply_approved(project_root=root)

    def _on_command_started(self, command_line: str) -> None:
        self.terminal.append(f'$ {command_line}')

    def _append_stdout(self, line: str) -> None:
        self.terminal.append(line)

    def _append_stderr(self, line: str) -> None:
        self.terminal.append(f'[stderr] {line}')

    def _on_command_finished(self, exit_code: int) -> None:
        self.terminal.append(f'[done] exit_code={exit_code}')
        self._refresh_dashboard()

    def _on_state_changed(self, state: str) -> None:
        self.status_label.setText(f'State: {state}')
        running = state in {'running', 'stopping'}
        self.stop_btn.setEnabled(running)
        self.run_btn.setEnabled(not running)

    def _refresh_dashboard(self) -> None:
        summary = self._api.get_summary()
        history = self._api.get_history(window=self.window_spin.value())
        if summary.get('error'):
            self.dashboard_modules.setText('-')
            self.dashboard_deps.setText('-')
            self.dashboard_cycles.setText('-')
            self.dashboard_risk.setText('-')
            self.dashboard_maturity.setText(summary.get('error', '-'))
            self.dashboard_trends.setText('-')
            self.dashboard_risks_text.setPlainText('')
            guard = self._api.get_self_guard()
            if guard.get('pass'):
                self.dashboard_self_guard_text.setPlainText('PASS')
            else:
                parts = []
                if guard.get('must_split_count', 0) > 0:
                    parts.append(f"{guard['must_split_count']} must-split")
                if guard.get('complexity_budget_alarms'):
                    parts.extend(guard['complexity_budget_alarms'])
                self.dashboard_self_guard_text.setPlainText('; '.join(parts) if parts else 'Scan required')
            self.dashboard_risk_pred_text.setPlainText('')
            self.dashboard_apply_rate.setText('-')
            self.dashboard_rollback_rate.setText('-')
            self.dashboard_median_verify.setText('-')
            self.learning_widget_text.setPlainText('Run eurika scan . first, then fix/cycle for learning data.')
            return
        system = summary.get('system', {})
        self.dashboard_modules.setText(str(system.get('modules', '-')))
        self.dashboard_deps.setText(str(system.get('dependencies', '-')))
        self.dashboard_cycles.setText(str(system.get('cycles', '-')))
        self.dashboard_maturity.setText(str(summary.get('maturity', '-')))
        self.dashboard_risk.setText(str(system.get('risk_score', '-')))
        trends = history.get('trends', {}) if isinstance(history, dict) else {}
        trend_parts = [f"complexity={trends.get('complexity', '-')}", f"smells={trends.get('smells', '-')}", f"centralization={trends.get('centralization', '-')}"]
        self.dashboard_trends.setText(', '.join(trend_parts))
        risks = summary.get('risks') or []
        if isinstance(risks, list) and risks:
            risk_lines = [str(r)[:120] for r in risks[:8]]
            self.dashboard_risks_text.setPlainText('\n'.join(risk_lines))
        else:
            self.dashboard_risks_text.setPlainText('')
        guard = self._api.get_self_guard()
        if guard.get('pass'):
            self.dashboard_self_guard_text.setPlainText('PASS (0 violations, 0 alarms)')
        else:
            lines = []
            if guard.get('must_split_count', 0) > 0:
                lines.append(f"Violations: {guard['must_split_count']} must-split")
            if guard.get('forbidden_count', 0) > 0:
                lines.append(f"{guard['forbidden_count']} forbidden imports")
            if guard.get('layer_viol_count', 0) > 0:
                lines.append(f"{guard['layer_viol_count']} layer violations")
            if guard.get('subsystem_bypass_count', 0) > 0:
                lines.append(f"{guard['subsystem_bypass_count']} subsystem bypass")
            if guard.get('trend_alarms'):
                lines.append('Trend alarms: ' + '; '.join(guard['trend_alarms']))
            if guard.get('complexity_budget_alarms'):
                lines.append('Complexity budget: ' + '; '.join(guard['complexity_budget_alarms']))
            self.dashboard_self_guard_text.setPlainText('\n'.join(lines) if lines else '-')
        rp = self._api.get_risk_prediction(top_n=5)
        preds = rp.get('predictions') or []
        if preds:
            rp_lines = [f"{p.get('module', '?')}: {p.get('score', 0)} ({', '.join(p.get('reasons', [])[:3])})" for p in preds]
            self.dashboard_risk_pred_text.setPlainText('\n'.join(rp_lines))
        else:
            self.dashboard_risk_pred_text.setPlainText('')
        metrics = self._api.get_operational_metrics(window=10)
        if isinstance(metrics, dict) and not metrics.get('error'):
            self.dashboard_apply_rate.setText(str(metrics.get('apply_rate', '-')))
            self.dashboard_rollback_rate.setText(str(metrics.get('rollback_rate', '-')))
            med = metrics.get('median_verify_time_ms')  # from operational_metrics
            self.dashboard_median_verify.setText(str(med) if med is not None else '-')
        else:
            self.dashboard_apply_rate.setText('-')
            self.dashboard_rollback_rate.setText('-')
            self.dashboard_median_verify.setText('-')
        learning = self._api.get_learning_insights(top_n=5)
        worked = learning.get('what_worked') or []
        recs = learning.get('recommendations') or {}
        white = recs.get('whitelist_candidates') or []
        deny = recs.get('policy_deny_candidates') or []
        chat_white = recs.get('chat_whitelist_hints') or []
        chat_review = recs.get('chat_policy_review_hints') or []
        lines: list[str] = []
        if worked:
            lines.append('What worked (top targets):')
            for item in worked:
                lines.append(f"- {item.get('target_file')} | {item.get('smell_type')}|{item.get('action_kind')} rate={item.get('verify_success_rate')} total={item.get('total')}")
        if white:
            lines.append('')
            lines.append('Whitelist suggestions:')
            for item in white:
                lines.append(f"- {item.get('target_file')} | {item.get('action_kind')} (rate={item.get('verify_success_rate')}, total={item.get('total')})")
        if deny:
            lines.append('')
            lines.append('Policy deny/review suggestions:')
            for item in deny:
                lines.append(f"- {item.get('target_file')} | {item.get('action_kind')} (rate={item.get('verify_success_rate')}, total={item.get('total')})")
        if chat_white:
            lines.append('')
            lines.append('Chat-driven whitelist hints (review only):')
            for item in chat_white:
                lines.append(f"- intent={item.get('intent')} target={item.get('target')} (success_rate={item.get('success_rate')}, total={item.get('total')})")
        if chat_review:
            lines.append('')
            lines.append('Chat-driven policy review hints:')
            for item in chat_review:
                lines.append(f"- intent={item.get('intent')} target={item.get('target')} (success_rate={item.get('success_rate')}, fail={item.get('fail')}, total={item.get('total')})")
        if not lines:
            lines.append('No learning data yet. Run eurika fix/cycle to collect outcomes.')
        self.learning_widget_text.setPlainText('\n'.join(lines))

    def _load_pending_plan(self) -> None:
        payload = self._api.get_pending_plan()
        if payload.get('error'):
            QMessageBox.warning(self, 'Pending plan', payload.get('error', 'Unknown error'))
            return
        operations = payload.get('operations') or []
        if not isinstance(operations, list):
            QMessageBox.warning(self, 'Pending plan', 'Invalid operations payload')
            return
        self._pending_operations = [op for op in operations if isinstance(op, dict)]
        self._render_approvals_table()

    def _render_approvals_table(self) -> None:
        self.approvals_table.setRowCount(len(self._pending_operations))
        for index, op in enumerate(self._pending_operations):
            expl = op.get('explainability') or {}
            risk = str(expl.get('risk') or op.get('risk') or '')
            self.approvals_table.setItem(index, 0, QTableWidgetItem(str(index + 1)))
            self.approvals_table.setItem(index, 1, QTableWidgetItem(str(op.get('target_file', ''))))
            self.approvals_table.setItem(index, 2, QTableWidgetItem(str(op.get('kind', ''))))
            self.approvals_table.setItem(index, 3, QTableWidgetItem(risk))
            combo = QComboBox()
            combo.addItems(['pending', 'approve', 'reject'])
            current = str(op.get('team_decision', 'pending')).lower()
            combo.setCurrentText(current if current in {'pending', 'approve', 'reject'} else 'pending')
            self.approvals_table.setCellWidget(index, 4, combo)

    def _save_approvals(self) -> None:
        if not self._pending_operations:
            QMessageBox.information(self, 'Approvals', 'No pending operations loaded.')
            return
        payload_ops: list[dict[str, Any]] = []
        for index, op in enumerate(self._pending_operations):
            decision_widget = self.approvals_table.cellWidget(index, 4)
            decision = 'pending'
            if isinstance(decision_widget, QComboBox):
                decision = decision_widget.currentText()
            payload_ops.append({'index': index + 1, 'team_decision': decision, 'approved_by': 'qt-user', 'target_file': op.get('target_file'), 'kind': op.get('kind')})
        result = self._api.save_approvals(payload_ops)
        if result.get('error'):
            QMessageBox.warning(self, 'Approvals', result.get('error', 'Failed to save approvals'))
            return
        QMessageBox.information(self, 'Approvals', json.dumps(result, ensure_ascii=True, indent=2))

    def _load_chat_preferences(self) -> None:
        data = self._settings.load()
        provider = str(data.get('chat_provider', 'auto'))
        if provider not in {'auto', 'openai', 'ollama'}:
            provider = 'auto'
        self.chat_provider_combo.setCurrentText(provider)
        self.chat_openai_model.setText(str(data.get('chat_openai_model', '')))
        self.chat_ollama_model.setText(str(data.get('chat_ollama_model', '')))
        timeout_val = data.get('chat_timeout_sec', 30)
        try:
            timeout = int(timeout_val)
        except (TypeError, ValueError):
            timeout = 30
        self.chat_timeout_spin.setValue(min(9999, max(0, timeout)))
        self.ollama_hsa_edit.setText(str(data.get('ollama_hsa_override_gfx', '10.3.0')))
        self.ollama_rocr_edit.setText(str(data.get('ollama_rocr_visible_devices', '0')))
        self.ollama_hip_edit.setText(str(data.get('ollama_hip_visible_devices', '0')))
        self.ollama_search_edit.setText(str(data.get('ollama_search_query', 'qwen')))
        self.ollama_custom_model_edit.setText(str(data.get('ollama_custom_model', '')))
        saved_available = str(data.get('ollama_available_model', '')).strip()
        self._saved_available_model = saved_available

    def _refresh_chat_goal_view(self) -> None:
        state = self._api.get_chat_dialog_state()
        goal = state.get('active_goal') if isinstance(state, dict) else {}
        pending = state.get('pending_clarification') if isinstance(state, dict) else {}
        pending_plan = state.get('pending_plan') if isinstance(state, dict) else {}
        last_execution = state.get('last_execution') if isinstance(state, dict) else {}
        lines: list[str] = []
        if isinstance(goal, dict) and goal:
            lines.append('Current interpreted goal:')
            intent = goal.get('intent', '-')
            target = goal.get('target', '')
            source = goal.get('source', '-')
            confidence = goal.get('confidence')
            risk_level = goal.get('risk_level')
            if target:
                lines.append(f'- intent={intent}, target={target}, source={source}')
            else:
                lines.append(f'- intent={intent}, source={source}')
            if confidence is not None:
                lines.append(f'- confidence={confidence}')
            if risk_level:
                lines.append(f'- risk={risk_level}')
            plan_steps = goal.get('plan_steps') or []
            if isinstance(plan_steps, list) and plan_steps:
                lines.append('- plan:')
                for step in plan_steps[:5]:
                    lines.append(f'  - {step}')
        if isinstance(pending, dict) and pending:
            original = str(pending.get('original', '')).strip()
            lines.append('')
            lines.append('Pending clarification:')
            lines.append(f"- {(original[:180] if original else '(awaiting details)')}")
        if isinstance(pending_plan, dict) and pending_plan:
            self._pending_plan_token = str(pending_plan.get('token') or '')
            lines.append('')
            lines.append('Awaiting confirmation:')
            lines.append(f"- intent={pending_plan.get('intent', '-')}, risk={pending_plan.get('risk_level', '-')}, token={pending_plan.get('token', '-')}")
            steps = pending_plan.get('steps') or []
            if isinstance(steps, list) and steps:
                for step in steps[:4]:
                    lines.append(f'  - {step}')
        if isinstance(last_execution, dict) and last_execution:
            lines.append('')
            lines.append('Last execution:')
            lines.append(f"- ok={last_execution.get('ok')}, verification_ok={last_execution.get('verification_ok')}, summary={last_execution.get('summary', '-')}")
            changed = last_execution.get('artifacts_changed') or []
            if isinstance(changed, list) and changed:
                lines.append(f"- changed={', '.join((str(x) for x in changed[:6]))}")
        if not lines:
            lines.append('No active interpreted goal yet.')
        self.chat_goal_view.setPlainText('\n'.join(lines))
        has_pending_plan = isinstance(pending_plan, dict) and bool(pending_plan)
        has_effective_pending = has_pending_plan or self._pending_plan_fallback_active
        self.chat_apply_btn.setEnabled(has_effective_pending)
        self.chat_reject_btn.setEnabled(has_effective_pending)
        if has_pending_plan:
            pending_intent = str(pending_plan.get('intent') or '-')
            pending_target = str(pending_plan.get('target') or '').strip()
            if pending_target:
                self.chat_pending_label.setText(f'Pending plan: intent={pending_intent}, target={pending_target}')
            else:
                self.chat_pending_label.setText(f'Pending plan: intent={pending_intent}')
            steps = pending_plan.get('steps') or []
            if isinstance(steps, list) and steps:
                tooltip = 'Plan steps:\n' + '\n'.join((f'- {str(step)}' for step in steps[:6]))
                self.chat_pending_label.setToolTip(tooltip)
                self.chat_apply_btn.setToolTip(tooltip)
                self.chat_reject_btn.setToolTip(tooltip)
            else:
                self.chat_pending_label.setToolTip('')
                self.chat_apply_btn.setToolTip('')
                self.chat_reject_btn.setToolTip('')
        elif self._pending_plan_fallback_active:
            if self._pending_plan_token:
                self.chat_pending_label.setText(f'Pending plan: token={self._pending_plan_token}')
            else:
                self.chat_pending_label.setText('Pending plan: awaiting confirmation')
            self.chat_pending_label.setToolTip('Awaiting confirmation from chat response.')
            self.chat_apply_btn.setToolTip('Apply pending action')
            self.chat_reject_btn.setToolTip('Reject pending action')
        else:
            self._pending_plan_token = ''
            self.chat_pending_label.setText('Pending plan: none')
            self.chat_pending_label.setToolTip('')
            self.chat_apply_btn.setToolTip('')
            self.chat_reject_btn.setToolTip('')

    def _save_chat_preferences(self) -> None:
        data = self._settings.load()
        data['chat_provider'] = self.chat_provider_combo.currentText()
        data['chat_openai_model'] = self.chat_openai_model.text().strip()
        data['chat_ollama_model'] = self.chat_ollama_model.text().strip()
        data['chat_timeout_sec'] = self.chat_timeout_spin.value()
        data['ollama_hsa_override_gfx'] = self.ollama_hsa_edit.text().strip()
        data['ollama_rocr_visible_devices'] = self.ollama_rocr_edit.text().strip()
        data['ollama_hip_visible_devices'] = self.ollama_hip_edit.text().strip()
        data['ollama_search_query'] = self.ollama_search_edit.text().strip()
        data['ollama_custom_model'] = self.ollama_custom_model_edit.text().strip()
        data['ollama_available_model'] = self.ollama_available_combo.currentText().strip()
        self._settings.save(data)

    def _dispatch_chat_message(self, message: str) -> None:
        if not message:
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            QMessageBox.information(self, 'Chat', 'Chat request already in progress.')
            return
        self._save_chat_preferences()
        provider = self.chat_provider_combo.currentText()
        openai_model = self.chat_openai_model.text().strip()
        ollama_model = self.chat_ollama_model.text().strip()
        timeout_sec = self.chat_timeout_spin.value()
        self.chat_transcript.append(f'You: {message}')
        self._chat_history.append({'role': 'user', 'content': message})
        self.chat_input.clear()
        self.chat_send_btn.setEnabled(False)
        self.status_label.setText('State: chat-running')
        worker = ChatWorker(api=self._api, message=message, history=list(self._chat_history), provider=provider, openai_model=openai_model, ollama_model=ollama_model, timeout_sec=timeout_sec)
        self._chat_worker = worker
        worker.finished_payload.connect(self._on_chat_result)
        worker.failed.connect(self._on_chat_error)
        worker.finished.connect(self._on_chat_finished)
        worker.start()

    def _send_chat_message(self) -> None:
        message = self.chat_input.toPlainText().strip()
        self._dispatch_chat_message(message)

    def _apply_pending_chat_plan(self) -> None:
        token = self._pending_plan_token.strip()
        msg = f'применяй token:{token}' if token else 'применяй'
        self._pending_plan_fallback_active = False
        self._dispatch_chat_message(msg)

    def _reject_pending_chat_plan(self) -> None:
        self._pending_plan_fallback_active = False
        self._dispatch_chat_message('отклонить')

    def _on_chat_result(self, payload: dict[str, Any]) -> None:
        text = str(payload.get('text', '')).strip()
        err = payload.get('error')
        if err:
            self.chat_transcript.append(f'Eurika [error]: {err}')
            return
        if not text:
            self.chat_transcript.append('Eurika: (empty response)')
            self._refresh_chat_goal_view()
            return
        self.chat_transcript.append(f'Eurika: {text}')
        self._chat_history.append({'role': 'assistant', 'content': text})
        self._refresh_chat_goal_view()
        self._activate_pending_controls_from_response(text)
        QTimer.singleShot(100, self._refresh_chat_goal_view)

    def _on_chat_error(self, error: str) -> None:
        self.chat_transcript.append(f'Eurika [exception]: {error}')
        self._refresh_chat_goal_view()

    def _activate_pending_controls_from_response(self, text: str) -> None:
        """Fallback UI activation when pending plan text is returned."""
        raw = str(text or '')
        if not self._response_requests_confirmation(raw):
            self._pending_plan_fallback_active = False
            return
        token = self._extract_pending_token_from_text(raw)
        if not token:
            self._pending_plan_fallback_active = False
            return
        self._pending_plan_token = token
        self._pending_plan_fallback_active = True
        self.chat_apply_btn.setEnabled(True)
        self.chat_reject_btn.setEnabled(True)
        self.chat_pending_label.setText(f'Pending plan: token={token}')
        self.chat_transcript.append('Eurika: Доступны действия: [Apply] или [Reject] кнопками ниже.')

    @staticmethod
    def _extract_pending_token_from_text(text: str) -> str:
        m = re.search('token:([a-fA-F0-9]{8,32})', str(text or ''))
        if not m:
            return ''
        return str(m.group(1))

    @staticmethod
    def _response_requests_confirmation(text: str) -> bool:
        raw = str(text or '')
        lowered = raw.lower()
        return 'применяй token:' in lowered

    def _on_chat_finished(self) -> None:
        self.chat_send_btn.setEnabled(True)
        self.status_label.setText('State: idle')
        if self._chat_worker is not None:
            self._chat_worker.deleteLater()
            self._chat_worker = None

    def _clear_chat_session(self) -> None:
        self._chat_history.clear()
        self.chat_transcript.clear()
        self._refresh_chat_goal_view()

    def _wire_ollama_process(self) -> None:
        self._ollama_process.started.connect(self._on_ollama_started)
        self._ollama_process.readyReadStandardOutput.connect(self._on_ollama_stdout)
        self._ollama_process.readyReadStandardError.connect(self._on_ollama_stderr)
        self._ollama_process.finished.connect(self._on_ollama_finished)
        self._ollama_process.errorOccurred.connect(self._on_ollama_error)

    def _wire_ollama_task_process(self) -> None:
        self._ollama_task_process.readyReadStandardOutput.connect(self._on_ollama_task_stdout)
        self._ollama_task_process.readyReadStandardError.connect(self._on_ollama_task_stderr)
        self._ollama_task_process.finished.connect(self._on_ollama_task_finished)
        self._ollama_task_process.errorOccurred.connect(self._on_ollama_task_error)

    def _setup_ollama_health_timer(self) -> None:
        self._ollama_health_timer.setInterval(10000)
        self._ollama_health_timer.timeout.connect(self._refresh_ollama_health)
        self._ollama_health_timer.start()
        self._refresh_ollama_health()
        self._refresh_ollama_catalog()

    def _start_ollama_server(self) -> None:
        if self._ollama_process.state() != QProcess.NotRunning:
            self.ollama_status.setText('Ollama: already running')
            self._sync_ollama_buttons()
            return
        self._save_chat_preferences()
        env = QProcessEnvironment.systemEnvironment()
        env.insert('HSA_OVERRIDE_GFX_VERSION', self.ollama_hsa_edit.text().strip() or '10.3.0')
        env.insert('ROCR_VISIBLE_DEVICES', self.ollama_rocr_edit.text().strip() or '0')
        env.insert('HIP_VISIBLE_DEVICES', self.ollama_hip_edit.text().strip() or '0')
        self._ollama_process.setProcessEnvironment(env)
        self._ollama_process.setWorkingDirectory(self.root_edit.text().strip() or '.')
        self.ollama_output.append(f"$ HSA_OVERRIDE_GFX_VERSION={env.value('HSA_OVERRIDE_GFX_VERSION')} ROCR_VISIBLE_DEVICES={env.value('ROCR_VISIBLE_DEVICES')} HIP_VISIBLE_DEVICES={env.value('HIP_VISIBLE_DEVICES')} ollama serve")
        self.ollama_status.setText('Ollama: starting...')
        self._sync_ollama_buttons()
        self._ollama_process.start('ollama', ['serve'])

    def _stop_ollama_server(self) -> None:
        if self._ollama_process.state() == QProcess.NotRunning:
            self.ollama_status.setText('Ollama: stopped')
            self._sync_ollama_buttons()
            return
        self.ollama_status.setText('Ollama: stopping...')
        self._shutdown_qprocess(self._ollama_process, timeout_ms=1200)

    def _on_ollama_started(self) -> None:
        self.ollama_status.setText('Ollama: running')
        self._sync_ollama_buttons()
        self._refresh_ollama_health()

    def _on_ollama_stdout(self) -> None:
        data = bytes(self._ollama_process.readAllStandardOutput()).decode('utf-8', errors='replace')
        for line in data.splitlines():
            if line.strip():
                self.ollama_output.append(line)

    def _on_ollama_stderr(self) -> None:
        data = bytes(self._ollama_process.readAllStandardError()).decode('utf-8', errors='replace')
        for line in data.splitlines():
            if line.strip():
                self.ollama_output.append(f'[stderr] {line}')

    def _on_ollama_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.ollama_status.setText(f'Ollama: stopped (exit={exit_code})')
        self.ollama_health.setText('API: unavailable')
        self._sync_ollama_buttons()

    def _on_ollama_error(self, _error: QProcess.ProcessError) -> None:
        msg = self._ollama_process.errorString() or 'Unknown process error'
        self.ollama_output.append(f'[error] {msg}')
        self.ollama_status.setText('Ollama: error')
        self.ollama_health.setText('API: unavailable')
        self._sync_ollama_buttons()

    def _sync_ollama_buttons(self) -> None:
        running = self._ollama_process.state() != QProcess.NotRunning
        self.ollama_start_btn.setEnabled(not running)
        self.ollama_stop_btn.setEnabled(running)

    def _refresh_ollama_health(self) -> None:
        healthy = self._api.is_ollama_healthy()
        self.ollama_health.setText('API: healthy' if healthy else 'API: unavailable')
        if healthy:
            self._refresh_ollama_models()
        else:
            self._last_models_error = ''

    def _refresh_ollama_models(self, user_initiated: bool=False) -> None:
        try:
            models = self._api.list_ollama_models()
        except Exception as exc:
            self.ollama_health.setText('API: unavailable')
            err_text = str(exc)
            if user_initiated:
                self.ollama_output.append('[models] Ollama API недоступен. Нажми `Start Ollama`, затем повтори `Refresh installed`.')
                self.ollama_install_status.setText('Installed: API unavailable')
            elif err_text != self._last_models_error:
                self.ollama_install_status.setText('Installed: API unavailable')
            self._last_models_error = err_text
            return
        self._last_models_error = ''
        current = self.ollama_installed_combo.currentText()
        self.ollama_installed_combo.blockSignals(True)
        self.ollama_installed_combo.clear()
        if models:
            self.ollama_installed_combo.addItems(models)
            if current and current in models:
                self.ollama_installed_combo.setCurrentText(current)
        else:
            self.ollama_installed_combo.addItem('(no local models)')
        self.ollama_installed_combo.blockSignals(False)

    def _sync_chat_model_from_installed(self, value: str) -> None:
        text = (value or '').strip()
        if not text or text.startswith('('):
            return
        self.chat_ollama_model.setText(text)
        self._save_chat_preferences()

    def _install_selected_ollama_model(self) -> None:
        if self._ollama_task_process.state() != QProcess.NotRunning:
            self.ollama_install_status.setText('Install: busy')
            return
        self._save_chat_preferences()
        model = self._resolve_ollama_model_to_install(self.ollama_custom_model_edit.text(), self.ollama_available_combo.currentText())
        if not model:
            self.ollama_install_status.setText('Install: select or input model')
            return
        self._ollama_task_mode = 'pull'
        self._ollama_task_stdout = ''
        self._ollama_task_model = model
        self.ollama_install_status.setText(f'Install: pulling `{model}`...')
        self.ollama_output.append(f'$ ollama pull {model}')
        self.ollama_pull_progress_row.setVisible(True)
        self.ollama_pull_progress.setValue(0)
        self.ollama_pull_progress_label.setText('')
        self._ollama_task_process.start('ollama', ['pull', model])

    def _refresh_ollama_catalog(self) -> None:
        self._save_chat_preferences()
        query = self.ollama_search_edit.text().strip() or 'qwen'
        names = self._filter_available_ollama_models(query)
        current = self.ollama_available_combo.currentText()
        self.ollama_available_combo.clear()
        if names:
            self.ollama_available_combo.addItems(names)
            if current in names:
                self.ollama_available_combo.setCurrentText(current)
            if self._saved_available_model and self.ollama_available_combo.findText(self._saved_available_model) >= 0:
                self.ollama_available_combo.setCurrentText(self._saved_available_model)
                self._saved_available_model = ''
            self.ollama_install_status.setText(f'Catalog: {len(names)} models (filtered)')
            return
        self.ollama_available_combo.addItems(self.AVAILABLE_OLLAMA_MODELS)
        if self._saved_available_model and self.ollama_available_combo.findText(self._saved_available_model) >= 0:
            self.ollama_available_combo.setCurrentText(self._saved_available_model)
            self._saved_available_model = ''
        self.ollama_install_status.setText('Catalog: no matches, showing full list')

    def _on_ollama_task_stdout(self) -> None:
        chunk = bytes(self._ollama_task_process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._ollama_task_stdout += chunk
        for line in chunk.splitlines():
            clean = _strip_ansi(line).strip()
            if clean:
                self.ollama_output.append(clean)

    def _on_ollama_task_stderr(self) -> None:
        chunk = bytes(self._ollama_task_process.readAllStandardError()).decode('utf-8', errors='replace')
        self._ollama_task_stdout += chunk
        for line in chunk.splitlines():
            clean = _strip_ansi(line).strip()
            if clean:
                self.ollama_output.append(f'[stderr] {clean}')
                if self._ollama_task_mode == 'pull':
                    parsed = _parse_ollama_pull_progress(clean)
                    if parsed:
                        pct, label = parsed
                        self.ollama_pull_progress.setValue(pct)
                        self.ollama_pull_progress_label.setText(label)

    def _on_ollama_task_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.ollama_pull_progress_row.setVisible(False)
        self.ollama_pull_progress_label.setText('')
        if self._ollama_task_mode == 'pull':
            if exit_code == 0:
                self.ollama_install_status.setText('Install: done')
                self._refresh_ollama_models()
                if self._ollama_task_model:
                    self.chat_ollama_model.setText(self._ollama_task_model)
                    if self.ollama_installed_combo.findText(self._ollama_task_model) >= 0:
                        self.ollama_installed_combo.setCurrentText(self._ollama_task_model)
                    self.ollama_custom_model_edit.setText('')
                self._refresh_ollama_health()
            else:
                self.ollama_install_status.setText(f'Install: failed (exit={exit_code})')
        else:
            self.ollama_install_status.setText('Install: idle')
        self._ollama_task_mode = ''
        self._ollama_task_model = ''

    def _on_ollama_task_error(self, _error: QProcess.ProcessError) -> None:
        self.ollama_pull_progress_row.setVisible(False)
        self.ollama_pull_progress_label.setText('')
        msg = self._ollama_task_process.errorString() or 'Unknown process error'
        self.ollama_output.append(f'[install error] {msg}')
        self.ollama_install_status.setText('Install: error')
        self._ollama_task_mode = ''
        self._ollama_task_model = ''

    @staticmethod
    def _filter_available_ollama_models(query: str) -> list[str]:
        q = (query or '').strip().lower()
        if not q:
            return list(MainWindow.AVAILABLE_OLLAMA_MODELS)
        out: list[str] = []
        for model in MainWindow.AVAILABLE_OLLAMA_MODELS:
            if q in model.lower():
                out.append(model)
        return out

    @staticmethod
    def _resolve_ollama_model_to_install(custom_value: str, selected_value: str) -> str:
        custom = (custom_value or '').strip()
        if custom:
            return custom
        selected = (selected_value or '').strip()
        if not selected or selected.startswith('('):
            return ''
        return selected

    def _shutdown_qprocess(self, process: QProcess, *, timeout_ms: int=1500) -> None:
        """Gracefully stop process to avoid 'QProcess destroyed while running'."""
        if process.state() == QProcess.NotRunning:
            return
        process.terminate()
        if process.waitForFinished(timeout_ms):
            return
        process.kill()
        process.waitForFinished(timeout_ms)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure background workers/processes are terminated before window closes."""
        self._is_closing = True
        if self._ollama_health_timer.isActive():
            self._ollama_health_timer.stop()
        self._command_service.shutdown(timeout_ms=1200)
        if self._terminal_process is not None:
            self._shutdown_qprocess(self._terminal_process)
        self._shutdown_qprocess(self._ollama_task_process)
        self._shutdown_qprocess(self._ollama_process)
        if self._chat_worker is not None and self._chat_worker.isRunning():
            self._chat_worker.requestInterruption()
            self._chat_worker.wait(1500)
        self._chat_worker = None
        super().closeEvent(event)