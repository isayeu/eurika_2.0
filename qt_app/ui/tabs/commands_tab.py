"""Commands tab: Core Command Panel. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qt_app.ui.scroll import VerticalScrollArea
from qt_app.ui.styles import COMBO_MAX_WIDTH, SPIN_MAX_WIDTH, TAB_MARGINS

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow

# Русские названия команд → CLI
CMD_ITEMS = [
    ("Сканирование", "scan"),
    ("Диагностика", "doctor"),
    ("Исправление", "fix"),
    ("Полный цикл", "cycle"),
    ("Объяснение", "explain"),
    ("План рефакторинга", "suggest-plan"),
    ("Снимок отчёта", "report-snapshot"),
    ("Метрики обучения", "learning-kpi"),
    ("Обучение из GitHub", "learn-github"),
    ("Очистка импортов", "clean-imports"),
    ("Самопроверка", "self-check"),
    ("Черновик whitelist", "whitelist-draft"),
    ("Отмена кампании", "campaign-undo"),
]

RUNTIME_MODES = [
    ("Ассистент", "assist"),
    ("Гибрид", "hybrid"),
    ("Авто", "auto"),
]


def build_commands_tab(main: MainWindow) -> None:
    """Build Commands tab: scan, doctor, fix, cycle, explain, options, run/stop."""
    main.commands_tab = tab = QWidget()
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    # === Команда ===
    cmd_group = QGroupBox("Команда")
    cmd_layout = QFormLayout(cmd_group)
    main.command_combo = QComboBox()
    for display, cli in CMD_ITEMS:
        main.command_combo.addItem(display, cli)
    main.command_combo.setMaximumWidth(COMBO_MAX_WIDTH + 80)
    cmd_layout.addRow("Действие", main.command_combo)

    module_row = QHBoxLayout()
    main.module_edit = QLineEdit()
    main.module_edit.setPlaceholderText("Только для «Объяснение»: eurika/api/serve.py")
    main.module_edit.setMaximumWidth(320)
    main.module_browse_btn = QPushButton("…")
    main.module_browse_btn.setFixedWidth(32)
    main.module_browse_btn.setToolTip("Выбрать модуль из проекта")
    module_row.addWidget(main.module_edit)
    module_row.addWidget(main.module_browse_btn)
    module_row.addStretch(1)
    cmd_layout.addRow("Модуль", module_row)
    layout.addWidget(cmd_group)

    # === Опции для fix/cycle/explain ===
    fix_group = QGroupBox("Опции исправления и диагностики")
    fix_layout = QFormLayout(fix_group)

    main.window_spin = QSpinBox()
    main.window_spin.setRange(1, 100)
    main.window_spin.setValue(5)
    main.window_spin.setMaximumWidth(SPIN_MAX_WIDTH)
    main.window_spin.setToolTip("Размер окна истории для doctor/fix/explain")
    fix_layout.addRow("Окно истории", main.window_spin)

    main.runtime_mode_combo = QComboBox()
    for display, val in RUNTIME_MODES:
        main.runtime_mode_combo.addItem(display, val)
    main.runtime_mode_combo.setMaximumWidth(COMBO_MAX_WIDTH)
    main.runtime_mode_combo.setToolTip(
        "Ассистент — подтверждать вручную; Гибрид — одобрять высокорисковые; Авто — whitelist bypass"
    )
    fix_layout.addRow("Режим исполнения", main.runtime_mode_combo)

    opts_label = QLabel("Дополнительно:")
    fix_layout.addRow(opts_label)
    opts_grid = QGridLayout()
    row, col = 0, 0
    opts = [
        ("dry_run_check", "Только план (без применения)", "Показать план, не применять изменения"),
        ("no_llm_check", "Без LLM", "Не вызывать Ollama/LLM для doctor/cycle"),
        ("no_clean_imports_check", "Без очистки импортов", "Исключить remove_unused_import"),
        ("no_code_smells_check", "Без code smells", "Исключить long_function, deep_nesting из плана"),
        ("use_llm_extract_check", "LLM-извлечение", "При long_function без блока — запросить код у Ollama"),
        ("allow_low_risk_campaign_check", "Низкий риск", "Разрешить низкорисковые операции через campaign skip"),
        ("team_mode_check", "Только предложить", "Сохранить план в Approvals, не применять"),
    ]
    for attr, label, tooltip in opts:
        cb = QCheckBox(label)
        cb.setToolTip(tooltip)
        setattr(main, attr, cb)
        opts_grid.addWidget(cb, row, col)
        col += 1
        if col > 2:
            col, row = 0, row + 1
    fix_layout.addRow(opts_grid)
    layout.addWidget(fix_group)

    # === Опции learn-github ===
    main.learn_group = QGroupBox("Опции обучения из GitHub")
    learn_group = main.learn_group
    learn_layout = QFormLayout(learn_group)
    main.learn_light_check = QCheckBox("Лёгкий список (starlette, httpx)")
    main.learn_light_check.setChecked(True)
    main.learn_light_check.setToolTip("Быстрый набор репозиториев")
    main.learn_scan_check = QCheckBox("Сканировать каждое репо")
    main.learn_scan_check.setChecked(True)
    main.learn_scan_check.setToolTip("Запускать eurika scan на каждом клоне")
    main.learn_build_patterns_check = QCheckBox("Собрать паттерны")
    main.learn_build_patterns_check.setChecked(True)
    main.learn_build_patterns_check.setToolTip("Создать .eurika/pattern_library.json")
    learn_row1 = QHBoxLayout()
    learn_row1.addWidget(main.learn_light_check)
    learn_row1.addWidget(main.learn_scan_check)
    learn_row1.addWidget(main.learn_build_patterns_check)
    learn_layout.addRow(learn_row1)
    main.learn_limit_label = QLabel("Лимит репозиториев:")
    main.learn_limit_spin = QSpinBox()
    main.learn_limit_spin.setRange(0, 20)
    main.learn_limit_spin.setValue(2)
    main.learn_limit_spin.setSpecialValueText("все")
    main.learn_limit_spin.setMaximumWidth(SPIN_MAX_WIDTH)
    main.learn_limit_spin.setToolTip("Использовать первые N репо (0 = все)")
    learn_limit_row = QHBoxLayout()
    learn_limit_row.addWidget(main.learn_limit_label)
    learn_limit_row.addWidget(main.learn_limit_spin)
    learn_limit_row.addStretch(1)
    learn_layout.addRow(learn_limit_row)
    main.learn_group.setVisible(False)  # показывается только для learn-github
    layout.addWidget(learn_group)

    # === Запуск ===
    run_group = QGroupBox("Запуск")
    run_layout = QFormLayout(run_group)
    action_row = QHBoxLayout()
    main.preview_label = QLabel("eurika scan .")
    main.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    main.preview_label.setWordWrap(True)
    main.preview_label.setStyleSheet("padding: 6px 8px;")
    action_row.addWidget(main.preview_label, 1)
    main.run_btn = QPushButton("Запустить")
    main.stop_btn = QPushButton("Остановить")
    main.stop_btn.setEnabled(False)
    action_row.addWidget(main.run_btn)
    action_row.addWidget(main.stop_btn)
    run_layout.addRow("Команда", action_row)
    quality_row = QHBoxLayout()
    main.ruff_btn = QPushButton("Ruff")
    main.ruff_btn.setToolTip("Проверка ruff check eurika cli")
    main.mypy_btn = QPushButton("Mypy")
    main.mypy_btn.setToolTip("Проверка типов mypy")
    main.release_check_btn = QPushButton("Release check")
    main.release_check_btn.setToolTip("Полная проверка: тесты, ruff, mypy, self-check")
    quality_row.addWidget(main.ruff_btn)
    quality_row.addWidget(main.mypy_btn)
    quality_row.addWidget(main.release_check_btn)
    quality_row.addStretch(1)
    run_layout.addRow("Проверки", quality_row)
    layout.addWidget(run_group)

    layout.addStretch(1)
    outer = QVBoxLayout(tab)
    outer.setContentsMargins(*TAB_MARGINS)
    outer.addWidget(VerticalScrollArea(content))
    main.tabs.addTab(tab, "Команды")
