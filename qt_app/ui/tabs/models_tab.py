"""Models tab: LLM (Ollama) + ML (PyTorch) sub-tabs."""
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
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_models_tab(main: MainWindow) -> None:
    """Build Models tab with LLM (Ollama/chat) and ML (PyTorch) sub-tabs."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*TAB_MARGINS)
    layout.setSpacing(8)

    inner = QTabWidget()
    main.models_inner_tabs = inner
    inner.addTab(_build_llm_subtab(main), "LLM")
    inner.addTab(_build_ml_subtab(main), "ML")
    layout.addWidget(inner)

    main.models_tab_index = main.tabs.addTab(tab, "Models")
    main.models_llm_subtab_index = 0
    main.models_ml_subtab_index = 1


def _build_llm_subtab(main: MainWindow) -> QWidget:
    """Ollama server + chat provider settings (GPU via Vulkan/CUDA)."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(8)

    ollama_box = QGroupBox("Ollama server")
    ollama_layout = QFormLayout(ollama_box)
    main.ollama_cuda_check = QCheckBox("Use NVIDIA CUDA")
    main.ollama_cuda_check.setChecked(False)
    main.ollama_cuda_check.setToolTip(
        "CUDA_VISIBLE_DEVICES + OLLAMA_VULKAN=0 — ускорение на NVIDIA (GeForce/Quadro). "
        "Несовместимо с Vulkan/AMD в одном процессе."
    )
    ollama_layout.addRow("NVIDIA CUDA", main.ollama_cuda_check)
    main.ollama_cuda_devices_edit = QLineEdit("0")
    main.ollama_cuda_devices_edit.setPlaceholderText("0  или  0,1")
    main.ollama_cuda_devices_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_cuda_devices_edit.setToolTip(
        "CUDA_VISIBLE_DEVICES — индекс GPU (nvidia-smi). Пусто = все видимые CUDA-устройства."
    )
    ollama_layout.addRow("CUDA_VISIBLE_DEVICES", main.ollama_cuda_devices_edit)
    main.ollama_vulkan_check = QCheckBox("Use Vulkan (AMD GPU / NVIDIA fallback)")
    main.ollama_vulkan_check.setChecked(False)
    main.ollama_vulkan_check.setToolTip(
        "OLLAMA_VULKAN=1 — Vulkan backend (AMD RADV или NVIDIA, если CUDA недоступна). "
        "На ноутбуках Optimus укажите GGML_VK_VISIBLE_DEVICES на дискретную NVIDIA."
    )
    ollama_layout.addRow("OLLAMA_VULKAN", main.ollama_vulkan_check)
    main.ollama_vk_devices_edit = QLineEdit("")
    main.ollama_vk_devices_edit.setPlaceholderText("пусто = auto; Optimus NVIDIA часто 1")
    main.ollama_vk_devices_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_vk_devices_edit.setToolTip(
        "GGML_VK_VISIBLE_DEVICES — индекс Vulkan-устройства (vulkaninfo --summary). "
        "Intel iGPU обычно 0, NVIDIA 940MX на Optimus — 1."
    )
    ollama_layout.addRow("GGML_VK_VISIBLE_DEVICES", main.ollama_vk_devices_edit)
    main.ollama_hsa_edit = QLineEdit("")
    main.ollama_hsa_edit.setPlaceholderText("только AMD, напр. 10.3.0")
    main.ollama_hsa_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_hsa_edit.setToolTip(
        "HSA_OVERRIDE_GFX_VERSION — только для AMD ROCm/Vulkan. На NVIDIA оставьте пустым."
    )
    main.ollama_rocr_edit = QLineEdit("")
    main.ollama_rocr_edit.setPlaceholderText("только AMD")
    main.ollama_rocr_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    main.ollama_hip_edit = QLineEdit("")
    main.ollama_hip_edit.setPlaceholderText("только AMD")
    main.ollama_hip_edit.setMaximumWidth(INPUT_MAX_WIDTH)
    ollama_layout.addRow("HSA_OVERRIDE_GFX_VERSION", main.ollama_hsa_edit)
    ollama_layout.addRow("ROCR_VISIBLE_DEVICES", main.ollama_rocr_edit)
    ollama_layout.addRow("HIP_VISIBLE_DEVICES", main.ollama_hip_edit)
    main.ollama_gpu_hint = QLabel(
        "GPU: CUDA для NVIDIA, Vulkan для AMD/fallback. Оба выкл. = CPU. После смены — Stop/Start Ollama."
    )
    main.ollama_gpu_hint.setWordWrap(True)
    main.ollama_gpu_hint.setStyleSheet(get_secondary_hint())
    ollama_layout.addRow("", main.ollama_gpu_hint)
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

    controls = QGroupBox("Кто отвечает в Chat")
    controls_layout = QVBoxLayout(controls)
    source_form = QFormLayout()
    main.chat_provider_combo = QComboBox()
    main.chat_provider_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    for value, label in (
        ("auto", "Авто: облако, иначе Ollama"),
        ("openai", "Облако (Groq / OpenRouter / …)"),
        ("ollama", "Ollama — локально"),
        ("cursor", "Cursor"),
        ("codex", "Codex API"),
    ):
        main.chat_provider_combo.addItem(label, value)
    main.chat_provider_combo.setToolTip(
        "Один источник ответа. Остальные блоки ниже скрываются.\n"
        "Авто: Groq/облако если есть OPENAI_API_KEY, иначе Ollama.\n"
        "Cursor: модели аккаунта Cursor (CURSOR_API_KEY в .env)."
    )
    source_form.addRow("Источник", main.chat_provider_combo)
    main.chat_provider_hint = QLabel("")
    main.chat_provider_hint.setWordWrap(True)
    main.chat_provider_hint.setStyleSheet(get_secondary_hint())
    source_form.addRow("", main.chat_provider_hint)
    controls_layout.addLayout(source_form)

    from eurika.utils.llm_presets import list_llm_api_presets

    main.chat_cloud_box = QGroupBox("Облако")
    cloud_layout = QFormLayout(main.chat_cloud_box)
    main.chat_api_preset_combo = QComboBox()
    main.chat_api_preset_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    main.chat_api_preset_combo.addItem("(из .env)", "")
    for preset in list_llm_api_presets():
        main.chat_api_preset_combo.addItem(preset.label, preset.id)
    main.chat_api_preset_combo.setToolTip(
        "Пресет OPENAI_BASE_URL. Ключ только в .env как OPENAI_API_KEY."
    )
    cloud_layout.addRow("Сервис", main.chat_api_preset_combo)
    main.openai_api_status = QLabel("API: unknown")
    cloud_layout.addRow("Статус", main.openai_api_status)
    main.chat_openai_model = QLineEdit()
    main.chat_openai_model.setPlaceholderText("openai/gpt-oss-120b, gemini-2.0-flash, …")
    main.chat_openai_model.setMaximumWidth(INPUT_MAX_WIDTH)
    cloud_layout.addRow("Модель", main.chat_openai_model)
    controls_layout.addWidget(main.chat_cloud_box)

    main.chat_ollama_box = QGroupBox("Ollama")
    ollama_chat_layout = QFormLayout(main.chat_ollama_box)
    chat_ollama_row = QHBoxLayout()
    main.chat_ollama_model = QComboBox()
    main.chat_ollama_model.setEditable(True)
    main.chat_ollama_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    chat_ollama_edit = main.chat_ollama_model.lineEdit()
    if chat_ollama_edit is not None:
        chat_ollama_edit.setPlaceholderText("установленная модель")
    main.chat_ollama_model.addItem("(no local models)")
    main.chat_ollama_model.setMaximumWidth(COMBO_MAX_WIDTH)
    main.chat_ollama_refresh_btn = QPushButton("Refresh")
    main.chat_ollama_refresh_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    main.chat_ollama_refresh_btn.setToolTip("Список моделей с Ollama API")
    chat_ollama_row.addWidget(main.chat_ollama_model, 1)
    chat_ollama_row.addWidget(main.chat_ollama_refresh_btn)
    ollama_chat_layout.addRow("Модель", chat_ollama_row)
    controls_layout.addWidget(main.chat_ollama_box)

    main.chat_cursor_box = QGroupBox("Cursor")
    cursor_layout = QFormLayout(main.chat_cursor_box)
    main.cursor_api_status = QLabel("ключ не проверен")
    cursor_layout.addRow("Статус", main.cursor_api_status)
    cursor_row = QHBoxLayout()
    main.chat_cursor_model_combo = QComboBox()
    main.chat_cursor_model_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    main.chat_cursor_model_combo.setToolTip("Composer — конкретная модель. Auto + Router — Cursor сам выбирает.")
    main.chat_cursor_refresh_btn = QPushButton("Refresh")
    main.chat_cursor_refresh_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    main.chat_cursor_refresh_btn.setToolTip("Каталог моделей аккаунта по CURSOR_API_KEY")
    cursor_row.addWidget(main.chat_cursor_model_combo, 1)
    cursor_row.addWidget(main.chat_cursor_refresh_btn)
    cursor_layout.addRow("Модель", cursor_row)
    main.chat_cursor_router_combo = QComboBox()
    main.chat_cursor_router_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    main.chat_cursor_router_combo.addItem("—", "")
    main.chat_cursor_router_combo.addItem("Cost", "cost")
    main.chat_cursor_router_combo.addItem("Balance", "balanced")
    main.chat_cursor_router_combo.addItem("Intelligence", "intelligence")
    main.chat_cursor_router_combo.setToolTip("Только для Auto + Router. На Individual плана Router часто нет.")
    main.chat_cursor_form = cursor_layout
    cursor_layout.addRow("Режим Router", main.chat_cursor_router_combo)
    controls_layout.addWidget(main.chat_cursor_box)

    timeout_form = QFormLayout()
    main.chat_timeout_spin = QSpinBox()
    main.chat_timeout_spin.setRange(0, 9999)
    main.chat_timeout_spin.setSpecialValueText("∞ (unlimited)")
    main.chat_timeout_spin.setValue(120)
    main.chat_timeout_spin.setMaximumWidth(SPIN_MAX_WIDTH)
    main.chat_timeout_spin.setToolTip("Для Cursor лучше 180–300 с.")
    timeout_form.addRow("Timeout сек", main.chat_timeout_spin)
    controls_layout.addLayout(timeout_form)
    layout.addWidget(controls)
    layout.addStretch(1)
    return page


def _build_ml_subtab(main: MainWindow) -> QWidget:
    """PyTorch optional runtime: status, device preference, smoke log."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 8, 0, 0)
    layout.setSpacing(8)

    box = QGroupBox("PyTorch (optional ML runtime)")
    form = QFormLayout(box)

    main.ml_policy_hint = QLabel(
        "LLM и ML работают в связке, не как замена: LLM (Ollama) — generate; "
        "ML (PyTorch) — классификатор/embeddings рядом. По умолчанию ML на CPU; "
        "на старых драйверах CUDA в torch часто недоступна — это нормально."
    )
    main.ml_policy_hint.setWordWrap(True)
    main.ml_policy_hint.setStyleSheet(get_secondary_hint())
    form.addRow("", main.ml_policy_hint)

    main.ml_torch_available = QLabel("—")
    form.addRow("Available", main.ml_torch_available)
    main.ml_torch_version = QLabel("—")
    form.addRow("Version", main.ml_torch_version)
    main.ml_torch_cuda = QLabel("—")
    form.addRow("CUDA", main.ml_torch_cuda)
    main.ml_torch_resolved = QLabel("—")
    form.addRow("Resolved device", main.ml_torch_resolved)
    main.ml_torch_smoke = QLabel("—")
    form.addRow("Smoke", main.ml_torch_smoke)

    main.ml_torch_device_combo = QComboBox()
    main.ml_torch_device_combo.addItems(["cpu", "cuda", "mps"])
    main.ml_torch_device_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    main.ml_torch_device_combo.setToolTip(
        "EURIKA_TORCH_DEVICE. Default cpu. cuda/mps применяются только если доступны."
    )
    form.addRow("EURIKA_TORCH_DEVICE", main.ml_torch_device_combo)

    btn_row = QHBoxLayout()
    main.ml_torch_refresh_btn = QPushButton("Refresh status")
    main.ml_torch_refresh_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    main.ml_torch_smoke_btn = QPushButton("Run smoke")
    main.ml_torch_smoke_btn.setMaximumWidth(BTN_SMALL_WIDTH)
    btn_row.addWidget(main.ml_torch_refresh_btn)
    btn_row.addWidget(main.ml_torch_smoke_btn)
    btn_row.addStretch(1)
    form.addRow("Actions", btn_row)

    main.ml_torch_output = QTextEdit()
    main.ml_torch_output.setReadOnly(True)
    main.ml_torch_output.setPlaceholderText("PyTorch probe log…")
    main.ml_torch_output.setMinimumHeight(100)
    form.addRow("Log", main.ml_torch_output)

    layout.addWidget(box)

    learn = QGroupBox("Market learning (paper)")
    learn_form = QFormLayout(learn)
    main.ml_market_hint = QLabel(
        "Прогресс бумажного обучения по рынку (.eurika/ml/). "
        "Тики — во вкладке Chat → Market. Ордера на биржу не уходят."
    )
    main.ml_market_hint.setWordWrap(True)
    main.ml_market_hint.setStyleSheet(get_secondary_hint())
    learn_form.addRow("", main.ml_market_hint)

    main.ml_market_trades = QLabel("—")
    learn_form.addRow("Сделки", main.ml_market_trades)
    main.ml_market_accuracy = QLabel("—")
    learn_form.addRow("Accuracy paper", main.ml_market_accuracy)
    main.ml_market_live = QLabel("—")
    learn_form.addRow("Live-метки", main.ml_market_live)
    main.ml_market_pnl = QLabel("—")
    main.ml_market_pnl.setToolTip(
        "Бумажный банк (старт 1000 USDT): equity / PnL$ / Σ edge после fee "
        "(все paper / live / сессия с включения Live)"
    )
    learn_form.addRow("Банк / PnL", main.ml_market_pnl)
    main.ml_market_opens = QLabel("—")
    learn_form.addRow("Открыто", main.ml_market_opens)
    main.ml_market_model = QLabel("—")
    learn_form.addRow("Модель", main.ml_market_model)
    main.ml_market_candles = QLabel("—")
    learn_form.addRow("Свечи", main.ml_market_candles)

    learn_btn = QHBoxLayout()
    main.ml_market_refresh_btn = QPushButton("Обновить прогресс")
    main.ml_market_refresh_btn.setMaximumWidth(BTN_SMALL_WIDTH + 40)
    main.ml_market_refresh_btn.setToolTip("Перечитать .eurika/ml/ (сделки, веса, открытые paper)")
    learn_btn.addWidget(main.ml_market_refresh_btn)
    learn_btn.addStretch(1)
    learn_form.addRow("", learn_btn)

    layout.addWidget(learn)
    layout.addStretch(1)
    return page
