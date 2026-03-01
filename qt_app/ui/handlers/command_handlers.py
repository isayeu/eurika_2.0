"""Command run, fix team-mode, apply-approved handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from ..main_window import MainWindow


def validate_project_root(root: str) -> tuple[bool, str]:
    if not root or not root.strip():
        return (False, "Project root is empty. Select a folder with Browse.")
    path = Path(root.strip()).resolve()
    if not path.exists():
        return (False, f"Path does not exist: {path}")
    if not path.is_dir():
        return (False, f"Project root must be a directory: {path}")
    has_pyproject = (path / "pyproject.toml").is_file()
    has_self_map = (path / "self_map.json").is_file()
    if has_pyproject or has_self_map:
        return (True, "")
    return (
        False,
        "Project root has no pyproject.toml or self_map.json. Run eurika scan first or select a Python project.",
    )


def run_command(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    ollama_model = main._resolve_ollama_model_for_command()
    main._command_service.start(
        command=main.command_combo.currentText(),
        project_root=root,
        module=main.module_edit.text().strip(),
        window=main.window_spin.value(),
        dry_run=main.dry_run_check.isChecked(),
        no_llm=main.no_llm_check.isChecked(),
        no_clean_imports=main.no_clean_imports_check.isChecked(),
        no_code_smells=main.no_code_smells_check.isChecked(),
        allow_low_risk_campaign=main.allow_low_risk_campaign_check.isChecked(),
        team_mode=main.team_mode_check.isChecked(),
        ollama_model=ollama_model,
    )


def run_fix_team_mode(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
    ollama_model = main._resolve_ollama_model_for_command()
    main._command_service.start(
        command="fix",
        project_root=root,
        module="",
        window=main.window_spin.value(),
        dry_run=False,
        no_llm=False,
        no_clean_imports=main.no_clean_imports_check.isChecked(),
        no_code_smells=main.no_code_smells_check.isChecked(),
        allow_low_risk_campaign=main.allow_low_risk_campaign_check.isChecked(),
        team_mode=True,
        ollama_model=ollama_model,
    )


def run_apply_approved(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
    main._command_service.run_apply_approved(project_root=root)


def on_command_started(main: MainWindow, command_line: str) -> None:
    main.terminal_emulator_output.append(f"$ {command_line}")
    main.tabs.setCurrentWidget(main.terminal_tab)


def append_stdout(main: MainWindow, line: str) -> None:
    main.terminal_emulator_output.append(line)


def append_stderr(main: MainWindow, line: str) -> None:
    main.terminal_emulator_output.append(f"[stderr] {line}")


def on_command_finished(main: MainWindow, exit_code: int) -> None:
    main.terminal_emulator_output.append(f"[done] exit_code={exit_code}")
    cmd = getattr(main._command_service, "active_command", "") or ""
    if "fix" in cmd or "cycle" in cmd:
        summary = format_fix_report_summary(main)
        if summary:
            main.terminal_emulator_output.append(summary)
    from .dashboard_handlers import refresh_dashboard

    refresh_dashboard(main)


def format_fix_report_summary(main: MainWindow) -> str:
    root = Path(main.root_edit.text().strip() or ".").resolve()
    report_path = root / "eurika_fix_report.json"
    if not report_path.exists():
        return ""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    parts: list[str] = []
    if data.get("dry_run"):
        parts.append("Dry run — no changes applied.")
        ops = (
            data.get("patch_plan", {}).get("operations")
            or data.get("operations")
            or []
        )
        parts.append(f"Planned: {len(ops)} operation(s).")
        return " — ".join(parts)
    msg = data.get("message", "").strip()
    if msg:
        parts.append(msg)
    modified = data.get("modified") or []
    m_count = len(modified)
    verify = data.get("verify") or {}
    gates = data.get("safety_gates") or {}
    verify_ran = gates.get("verify_ran", True)
    v_ok = verify.get("success") if verify_ran else None
    rollback = gates.get("rollback_done", False)
    if m_count > 0:
        files = ", ".join(modified[:3])
        if m_count > 3:
            files += f" (+{m_count - 3} more)"
        parts.append(f"Modified: {m_count} file(s) — {files}")
    if verify_ran:
        parts.append(f'Verify: {"✓" if v_ok else "✗"}')
    if rollback:
        parts.append("Rollback: done (verify failed)")
    return " | ".join(parts) if parts else ""


def on_state_changed(main: MainWindow, state: str) -> None:
    main.status_label.setText(f"State: {state}")
    running = state in {"thinking", "stopping"}
    main.stop_btn.setEnabled(running)
    main.run_btn.setEnabled(not running)
