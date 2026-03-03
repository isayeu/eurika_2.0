"""Commands tab: Core Command Panel. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
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


def build_commands_tab(main: MainWindow) -> None:
    """Build Commands tab: scan, doctor, fix, cycle, explain, options, run/stop."""
    main.commands_tab = tab = QWidget()
    layout = QVBoxLayout(tab)
    controls = QGroupBox("Core Command Panel")
    controls_layout = QFormLayout(controls)
    main.command_combo = QComboBox()
    main.command_combo.addItems([
        "scan", "doctor", "fix", "cycle", "explain", "report-snapshot", "learning-kpi",
        "learn-github", "clean-imports", "self-check", "whitelist-draft", "campaign-undo",
    ])
    controls_layout.addRow("Command", main.command_combo)
    main.module_edit = QLineEdit()
    main.module_edit.setPlaceholderText("Required for explain: eurika/api/serve.py")
    controls_layout.addRow("Module", main.module_edit)
    main.window_spin = QSpinBox()
    main.window_spin.setRange(1, 100)
    main.window_spin.setValue(5)
    controls_layout.addRow("Window", main.window_spin)
    options_row = QHBoxLayout()
    main.dry_run_check = QCheckBox("--dry-run")
    main.no_llm_check = QCheckBox("--no-llm")
    main.no_clean_imports_check = QCheckBox("--no-clean-imports")
    main.no_code_smells_check = QCheckBox("--no-code-smells")
    main.no_code_smells_check.setToolTip(
        "Exclude refactor_code_smell (long_function, deep_nesting) from plan"
    )
    main.use_llm_extract_check = QCheckBox("Use LLM extract")
    main.use_llm_extract_check.setChecked(False)
    main.use_llm_extract_check.setToolTip(
        "EURIKA_USE_LLM_EXTRACT=1: when long_function has no extract block, ask Ollama for refactored code (Phase 3)"
    )
    main.allow_low_risk_campaign_check = QCheckBox("--allow-low-risk-campaign")
    main.allow_low_risk_campaign_check.setToolTip(
        "Allow low-risk ops (e.g. remove_unused_import) through campaign skip (OPERABILITY D)"
    )
    main.team_mode_check = QCheckBox("--team-mode")
    main.team_mode_check.setToolTip(
        "Propose only: save plan to .eurika/pending_plan.json, then use Approvals tab"
    )
    main.learn_light_check = QCheckBox("--light (learn-github)")
    main.learn_light_check.setChecked(True)
    main.learn_light_check.setToolTip("Light curated list: starlette, httpx — faster")
    main.learn_scan_check = QCheckBox("--scan (learn-github)")
    main.learn_scan_check.setChecked(True)
    main.learn_scan_check.setToolTip("Run eurika scan on each cloned repo")
    main.learn_build_patterns_check = QCheckBox("--build-patterns")
    main.learn_build_patterns_check.setChecked(True)
    main.learn_build_patterns_check.setToolTip("Build pattern library → .eurika/pattern_library.json (Phase 5 OSS)")
    main.learn_limit_spin = QSpinBox()
    main.learn_limit_spin.setRange(0, 20)
    main.learn_limit_spin.setValue(2)
    main.learn_limit_spin.setSpecialValueText("all")
    main.learn_limit_spin.setToolTip("--limit-repos: use first N repos (0=all)")
    options_row.addWidget(main.dry_run_check)
    options_row.addWidget(main.no_llm_check)
    options_row.addWidget(main.no_clean_imports_check)
    options_row.addWidget(main.no_code_smells_check)
    options_row.addWidget(main.use_llm_extract_check)
    options_row.addWidget(main.allow_low_risk_campaign_check)
    options_row.addWidget(main.team_mode_check)
    main.learn_label = QLabel("| Learn:")
    main.learn_limit_label = QLabel("limit-repos:")
    options_row.addWidget(main.learn_label)
    options_row.addWidget(main.learn_light_check)
    options_row.addWidget(main.learn_scan_check)
    options_row.addWidget(main.learn_build_patterns_check)
    options_row.addWidget(main.learn_limit_label)
    options_row.addWidget(main.learn_limit_spin)
    options_row.addStretch(1)
    controls_layout.addRow("Options", options_row)
    action_row = QHBoxLayout()
    main.preview_label = QLabel("eurika scan .")
    main.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    action_row.addWidget(main.preview_label, 1)
    main.run_btn = QPushButton("Run")
    main.stop_btn = QPushButton("Stop")
    main.stop_btn.setEnabled(False)
    action_row.addWidget(main.run_btn)
    action_row.addWidget(main.stop_btn)
    controls_layout.addRow("Execute", action_row)
    quality_row = QHBoxLayout()
    main.ruff_btn = QPushButton("Ruff")
    main.ruff_btn.setToolTip("ruff check eurika cli")
    main.mypy_btn = QPushButton("Mypy")
    main.mypy_btn.setToolTip("mypy eurika cli")
    main.release_check_btn = QPushButton("Release check")
    main.release_check_btn.setToolTip("./scripts/release_check.sh — tests, ruff, mypy, self-check")
    quality_row.addWidget(main.ruff_btn)
    quality_row.addWidget(main.mypy_btn)
    quality_row.addWidget(main.release_check_btn)
    quality_row.addStretch(1)
    controls_layout.addRow("Quality", quality_row)
    layout.addWidget(controls)
    main.tabs.addTab(tab, "Commands")
