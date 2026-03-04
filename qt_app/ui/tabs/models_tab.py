"""Models tab: Ollama server control, chat model settings. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qt_app.ui.styles import (
    BTN_SMALL_WIDTH,
    COMBO_MAX_WIDTH,
    get_secondary_hint,
    INPUT_MAX_WIDTH,
    SPIN_MAX_WIDTH,
    TAB_MARGINS,
)

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_models_tab(main: MainWindow) -> None:
    """Build Models tab: Ollama server, installed/available models, chat settings."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*TAB_MARGINS)
    layout.setSpacing(8)
    ollama_box = QGroupBox("Ollama server")
    ollama_layout = QFormLayout(ollama_box)
    main.ollama_vulkan_check = QCheckBox("Use Vulkan (AMD GPU)")
    main.ollama_vulkan_check.setChecked(True)
    main.ollama_vulkan_check.setToolTip("OLLAMA_VULKAN=1 — Vulkan/RADV backend для AMD RX 6xxx/7xxx")
    ollama_layout.addRow("OLLAMA_VULKAN", main.ollama_vulkan_check)
    main.ollama_hsa_edit = QLineEdit("10.3.0")
    main.ollama_hsa_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_rocr_edit = QLineEdit("")
    main.ollama_rocr_edit.setPlaceholderText("0 или пусто")
    main.ollama_rocr_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_hip_edit = QLineEdit("")
    main.ollama_hip_edit.setPlaceholderText("0 или пусто")
    main.ollama_hip_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    ollama_layout.addRow("HSA_OVERRIDE_GFX_VERSION", main.ollama_hsa_edit)
    ollama_layout.addRow("ROCR_VISIBLE_DEVICES", main.ollama_rocr_edit)
    ollama_layout.addRow("HIP_VISIBLE_DEVICES", main.ollama_hip_edit)
    ollama_row = QHBoxLayout()
    main.ollama_start_btn = QPushButton("Start Ollama")
    main.ollama_stop_btn = QPushButton("Stop Ollama")
    main.ollama_stop_btn.setEnabled(False)
    main.ollama_status = QLabel("Ollama: stopped")
    ollama_row.addWidget(main.ollama_start_btn)
    ollama_row.addWidget(main.ollama_stop_btn)
    ollama_row.addWidget(main.ollama_status, 1)
    ollama_layout.addRow("Control", ollama_row)
    main.ollama_health = QLabel("API: unknown")
    ollama_layout.addRow("Health", main.ollama_health)
    main.ollama_installed_combo = QComboBox()
    main.ollama_installed_combo.setEditable(False)
    main.ollama_installed_combo.addItem("(no local models)")
    main.ollama_installed_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    refresh_models_row = QHBoxLayout()
    main.ollama_refresh_models_btn = QPushButton("Refresh installed")
    main.ollama_refresh_models_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    refresh_models_row.addWidget(main.ollama_installed_combo, 1)
    refresh_models_row.addWidget(main.ollama_refresh_models_btn)
    ollama_layout.addRow("Installed", refresh_models_row)
    main.ollama_available_combo = QComboBox()
    main.ollama_available_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    install_row = QHBoxLayout()
    main.ollama_custom_model_edit = QLineEdit()
    main.ollama_custom_model_edit.setPlaceholderText("custom model (e.g. deepseek-r1:14b)")
    main.ollama_custom_model_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_install_btn = QPushButton("Install selected")
    main.ollama_install_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    install_row.addWidget(main.ollama_custom_model_edit)
    install_row.addWidget(main.ollama_available_combo, 1)
    install_row.addWidget(main.ollama_install_btn)
    ollama_layout.addRow("Available", install_row)
    main.ollama_install_status = QLabel("Install: idle")
    ollama_layout.addRow("Install status", main.ollama_install_status)
    main.ollama_pull_progress = QProgressBar()
    main.ollama_pull_progress.setRange(0, 100)
    main.ollama_pull_progress.setValue(0)
    main.ollama_pull_progress.setFormat("%p%")
    main.ollama_pull_progress_label = QLabel("")
    main.ollama_pull_progress_label.setStyleSheet(get_secondary_hint())
    pull_progress_row = QWidget()
    pull_progress_layout = QHBoxLayout(pull_progress_row)
    pull_progress_layout.setContentsMargins(0, 0, 0, 0)
    pull_progress_layout.addWidget(main.ollama_pull_progress, 1)
    pull_progress_layout.addWidget(main.ollama_pull_progress_label)
    main.ollama_pull_progress_row = pull_progress_row
    main.ollama_pull_progress_row.setVisible(False)
    ollama_layout.addRow("Pull progress", main.ollama_pull_progress_row)
    main.ollama_output = QTextEdit()
    main.ollama_output.setReadOnly(True)
    main.ollama_output.setPlaceholderText("`ollama serve` output will appear here.")
    main.ollama_output.setMinimumHeight(80)
    ollama_layout.addRow("Output", main.ollama_output)
    layout.addWidget(ollama_box)
    controls = QGroupBox("Chat model settings")
    controls_layout = QFormLayout(controls)
    main.chat_provider_combo = QComboBox()
    main.chat_provider_combo.addItems(["auto", "openai", "ollama"])
    main.chat_provider_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    controls_layout.addRow("Provider", main.chat_provider_combo)
    main.chat_openai_model = QLineEdit()
    main.chat_openai_model.setPlaceholderText("e.g. gpt-4o-mini or mistralai/...")
    main.chat_openai_model.setMaximumWidth(INPUT_MAX_WIDTH)
    controls_layout.addRow("OpenAI/OpenRouter model", main.chat_openai_model)
    main.chat_ollama_model = QLineEdit()
    main.chat_ollama_model.setPlaceholderText("e.g. qwen2.5-coder:7b")
    main.chat_ollama_model.setMaximumWidth(INPUT_MAX_WIDTH)
    controls_layout.addRow("Ollama model", main.chat_ollama_model)
    main.chat_timeout_spin = QSpinBox()
    main.chat_timeout_spin.setRange(0, 9999)
    main.chat_timeout_spin.setSpecialValueText("∞ (unlimited)")
    main.chat_timeout_spin.setValue(30)
    main.chat_timeout_spin.setMaximumWidth(SPIN_MAX_WIDTH)
    controls_layout.addRow("Timeout sec", main.chat_timeout_spin)
    layout.addWidget(controls)
    main.models_tab_index = main.tabs.addTab(tab, "Models")
