"""Command run, fix team-mode, apply-approved handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QFileDialog, QMessageBox

if TYPE_CHECKING:
    from ..main_window import MainWindow


def select_module(main: MainWindow) -> None:
    """Open file picker to select a Python module from project root."""
    root = main.root_edit.text().strip() or "."
    base = Path(root).resolve()
    if not base.exists() or not base.is_dir():
        QMessageBox.warning(
            main, "Select module",
            "Select project root first.",
        )
        return
    path, _ = QFileDialog.getOpenFileName(
        main,
        "Select module",
        str(base),
        "Python files (*.py);;All files (*)",
    )
    if path:
        try:
            rel = Path(path).resolve().relative_to(base)
            main.module_edit.setText(str(rel).replace("\\", "/"))
        except ValueError:
            main.module_edit.setText(path)


def validate_project_root(root: str) -> tuple[bool, str]:
    if not root or not root.strip():
        return (False, "Project root is empty. Select a folder with Browse.")
    path = Path(root.strip()).resolve()
    if not path.exists():
        return (False, f"Path does not exist: {path}")
    if not path.is_dir():
        return (False, f"Project root must be a directory: {path}")
    if (path / "pyproject.toml").is_file() or (path / "self_map.json").is_file():
        return (True, "")
    if _has_python_sources(path):
        return (True, "")
    return (
        False,
        "Project root has no pyproject.toml, self_map.json, or Python files. "
        "Select a Python project or run `eurika scan .` first.",
    )


def _has_python_sources(path: Path, *, max_depth: int = 2) -> bool:
    """True if directory looks like a Python project (`.py` within max_depth)."""
    try:
        for child in path.rglob("*.py"):
            rel = child.relative_to(path)
            if any(part in {"__pycache__", ".venv", "venv", ".git"} for part in rel.parts[:-1]):
                continue
            if len(rel.parts) <= max_depth:
                return True
    except OSError:
        return False
    return False


def run_command(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    ollama_model = main._resolve_ollama_model_for_command()
    cmd = main._get_current_command()
    runtime_mode_val = main._get_runtime_mode()
    learn_light_w = getattr(main, "learn_light_check", None)
    learn_scan_w = getattr(main, "learn_scan_check", None)
    learn_build_w = getattr(main, "learn_build_patterns_check", None)
    learn_light = bool(learn_light_w.isChecked()) if learn_light_w is not None else False
    learn_scan = bool(learn_scan_w.isChecked()) if learn_scan_w is not None else False
    learn_build = bool(learn_build_w.isChecked()) if learn_build_w is not None else False
    learn_limit_w = getattr(main, "learn_limit_spin", None)
    learn_limit = int(learn_limit_w.value()) if learn_limit_w is not None else 0
    if cmd == "cycle":
        main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
        main._command_service.run_ritual(
            project_root=root,
            window=main.window_spin.value(),
            dry_run=main.dry_run_check.isChecked(),
            no_llm=main.no_llm_check.isChecked(),
            no_clean_imports=main.no_clean_imports_check.isChecked(),
            no_code_smells=main.no_code_smells_check.isChecked(),
            use_llm_extract=main.use_llm_extract_check.isChecked(),
            allow_low_risk_campaign=main.allow_low_risk_campaign_check.isChecked(),
            team_mode=main.team_mode_check.isChecked(),
            runtime_mode=runtime_mode_val,
            ollama_model=ollama_model,
        )
        return
    main._command_service.start(
        command=cmd,
        project_root=root,
        module=main.module_edit.text().strip(),
        window=main.window_spin.value(),
        dry_run=main.dry_run_check.isChecked(),
        no_llm=main.no_llm_check.isChecked(),
        no_clean_imports=main.no_clean_imports_check.isChecked(),
        no_code_smells=main.no_code_smells_check.isChecked(),
        use_llm_extract=main.use_llm_extract_check.isChecked(),
        allow_low_risk_campaign=main.allow_low_risk_campaign_check.isChecked(),
        team_mode=main.team_mode_check.isChecked(),
        runtime_mode=runtime_mode_val,
        ollama_model=ollama_model,
        learn_light=learn_light,
        learn_scan=learn_scan,
        learn_build_patterns=learn_build,
        learn_limit_repos=learn_limit,
    )


def run_fix_team_mode(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
    ollama_model = main._resolve_ollama_model_for_command()
    runtime_mode_val = main._get_runtime_mode()
    main._command_service.start(
        command="fix",
        project_root=root,
        module="",
        window=main.window_spin.value(),
        dry_run=False,
        no_llm=False,
        no_clean_imports=main.no_clean_imports_check.isChecked(),
        no_code_smells=main.no_code_smells_check.isChecked(),
        use_llm_extract=main.use_llm_extract_check.isChecked(),
        allow_low_risk_campaign=main.allow_low_risk_campaign_check.isChecked(),
        team_mode=True,
        runtime_mode=runtime_mode_val,
        ollama_model=ollama_model,
    )


def run_ruff(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    main._command_service.run_ruff(project_root=root)


def run_mypy(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    main._command_service.run_mypy(project_root=root)


def run_release_check(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    script = Path(root).resolve() / "scripts" / "release_check.sh"
    if not script.is_file():
        QMessageBox.warning(
            main, "Release check",
            f"scripts/release_check.sh not found in {Path(root).resolve()}",
        )
        return
    ollama_model = main._resolve_ollama_model_for_command()
    main._command_service.run_release_check(project_root=root, ollama_model=ollama_model)


def run_apply_approved(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    if main._pending_operations:
        main._pending_operations = []
        from . import approve_handlers
        approve_handlers.render_approvals_table(main)
    main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
    main._command_service.run_apply_approved(project_root=root)


def run_apply_from_report(main: MainWindow) -> None:
    root = main.root_edit.text().strip() or "."
    ok, msg = validate_project_root(root)
    if not ok:
        QMessageBox.warning(main, "Invalid project root", msg)
        return
    report_path = Path(root).resolve() / "eurika_fix_report.json"
    if not report_path.is_file():
        QMessageBox.warning(
            main,
            "Apply from report",
            "eurika_fix_report.json not found. Run fix --dry-run first (Commands tab).",
        )
        return
    main.tabs.setCurrentIndex(main.tabs.indexOf(main.commands_tab))
    main._command_service.run_apply_from_report(project_root=root)


def on_command_started(main: MainWindow, command_line: str) -> None:
    from ..tabs import terminal_tab
    terminal_tab._append_stream(main, f"$ {command_line}\n")
    main.tabs.setCurrentWidget(main.terminal_tab)


def append_stdout(main: MainWindow, chunk: str) -> None:
    """Append stdout chunk; use stream append to preserve progress dots on one line."""
    from ..main_window_helpers import strip_ansi
    from ..tabs import terminal_tab
    terminal_tab._append_stream(main, strip_ansi(chunk))


def append_stderr(main: MainWindow, chunk: str) -> None:
    """Append stderr chunk; use stream append to preserve progress dots on one line."""
    from ..main_window_helpers import strip_ansi
    from ..tabs import terminal_tab
    terminal_tab._append_stream(main, f"[stderr] {strip_ansi(chunk)}")


def on_command_finished(main: MainWindow, exit_code: int) -> None:
    main.terminal_emulator_output.append(f"[done] exit_code={exit_code}\n")
    cmd = getattr(main._command_service, "active_command", "") or ""
    if "fix" in cmd or "cycle" in cmd:
        summary = format_fix_report_summary(main)
        if summary:
            main.terminal_emulator_output.append(summary)
    if "apply-approved" in cmd:
        main._pending_operations = []
        from . import approve_handlers
        approve_handlers.render_approvals_table(main)
    from .dashboard_handlers import refresh_dashboard

    refresh_dashboard(main)
    if "scan" in cmd or "doctor" in cmd or "ritual" in cmd:
        from . import chat_handlers as _chat_handlers

        _chat_handlers.refresh_chat_mention_candidates(main)


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


def _format_idle_status(main: MainWindow) -> str:
    """Status text when idle: Ready · <project_path>."""
    root = (main.root_edit.text() or "").strip() or "."
    if len(root) > 48:
        root = "…" + root[-45:]
    return f"Ready · {root}" if root != "." else "Ready — select project root"


def on_state_changed(main: MainWindow, state: str) -> None:
    if state == "idle":
        main.status_label.setText(_format_idle_status(main))
    else:
        main.status_label.setText(f"State: {state}")
    running = state in {"thinking", "stopping"}
    main.stop_btn.setEnabled(running)
    main.run_btn.setEnabled(not running)
    main.ruff_btn.setEnabled(not running)
    main.mypy_btn.setEnabled(not running)
    main.release_check_btn.setEnabled(not running)
    # Stop on Terminal tab: active when CommandService running, or terminal emulator running
    term_proc = getattr(main, "_terminal_process", None)
    term_running = (
        term_proc is not None
        and term_proc.state() != QProcess.ProcessState.NotRunning
    )
    main.terminal_emulator_stop_btn.setEnabled(running or term_running)
