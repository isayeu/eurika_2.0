"""Typed widget attributes for Models tab (LLM + ML), assigned in models_tab.build_*."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QWidget,
)


class ModelsTabAttrs:
    """Class-level declarations so basedpyright accepts dynamic MainWindow wiring."""

    models_inner_tabs: QTabWidget
    models_tab_index: int
    models_llm_subtab_index: int
    models_ml_subtab_index: int

    ollama_cuda_check: QCheckBox
    ollama_cuda_devices_edit: QLineEdit
    ollama_vulkan_check: QCheckBox
    ollama_vk_devices_edit: QLineEdit
    ollama_hsa_edit: QLineEdit
    ollama_rocr_edit: QLineEdit
    ollama_hip_edit: QLineEdit
    ollama_gpu_hint: QLabel
    ollama_start_btn: QPushButton
    ollama_stop_btn: QPushButton
    ollama_status: QLabel
    ollama_health: QLabel
    ollama_installed_combo: QComboBox
    ollama_refresh_models_btn: QPushButton
    ollama_available_combo: QComboBox
    ollama_custom_model_edit: QLineEdit
    ollama_install_btn: QPushButton
    ollama_install_status: QLabel
    ollama_pull_progress: QProgressBar
    ollama_pull_progress_label: QLabel
    ollama_pull_progress_row: QWidget
    ollama_output: QTextEdit

    chat_provider_combo: QComboBox
    chat_api_preset_combo: QComboBox
    openai_api_status: QLabel
    chat_openai_model: QLineEdit
    chat_ollama_model: QComboBox
    chat_ollama_refresh_btn: QPushButton
    chat_timeout_spin: QSpinBox

    ml_policy_hint: QLabel
    ml_torch_available: QLabel
    ml_torch_version: QLabel
    ml_torch_cuda: QLabel
    ml_torch_resolved: QLabel
    ml_torch_smoke: QLabel
    ml_torch_device_combo: QComboBox
    ml_torch_refresh_btn: QPushButton
    ml_torch_smoke_btn: QPushButton
    ml_torch_output: QTextEdit
    ml_market_hint: QLabel
    ml_market_trades: QLabel
    ml_market_accuracy: QLabel
    ml_market_live: QLabel
    ml_market_pnl: QLabel
    ml_market_opens: QLabel
    ml_market_model: QLabel
    ml_market_candles: QLabel
    ml_market_refresh_btn: QPushButton
