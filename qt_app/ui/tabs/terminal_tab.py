"""Terminal tab: output from Commands + manual shell. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ..main_window_helpers import TerminalLineEdit, is_tui_command, strip_ansi

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_terminal_tab(main: MainWindow) -> None:
    """Build Terminal tab: output from Commands + manual shell commands."""
    main.terminal_tab = tab = QWidget()
    layout = QVBoxLayout(tab)
    emulator_box = QGroupBox("Terminal")
    emulator_box.setStyleSheet("QGroupBox { color: #0f0; }")
    emulator_box.setToolTip(
        "Output from Commands (scan, doctor, fix…) and manual shell. Cwd = project root."
    )
    emulator_layout = QVBoxLayout(emulator_box)
    terminal_style = "background-color: #000; color: #0f0; font-family: monospace;"
    main.terminal_emulator_output = QTextEdit()
    main.terminal_emulator_output.setReadOnly(True)
    main.terminal_emulator_output.setStyleSheet(terminal_style)
    main.terminal_emulator_output.setPlaceholderText(
        "Output from Commands (Run) or enter command below (ls, pwd, eurika scan .)."
    )
    emulator_layout.addWidget(main.terminal_emulator_output, 1)
    input_row = QHBoxLayout()
    input_row.addWidget(QLabel("$"))
    main.terminal_emulator_input = TerminalLineEdit()
    main.terminal_emulator_input.setStyleSheet(terminal_style)
    main.terminal_emulator_input.setPlaceholderText(
        "Enter command and press Return (e.g. ls, pwd, eurika scan .)"
    )
    main.terminal_emulator_input.returnPressed.connect(lambda: run_terminal_emulator_command(main))
    input_row.addWidget(main.terminal_emulator_input, 1)
    main.terminal_emulator_btn = QPushButton("Run")
    main.terminal_emulator_btn.clicked.connect(lambda: run_terminal_emulator_command(main))
    input_row.addWidget(main.terminal_emulator_btn)
    main.terminal_emulator_stop_btn = QPushButton("Stop")
    main.terminal_emulator_stop_btn.setEnabled(False)
    main.terminal_emulator_stop_btn.clicked.connect(lambda: stop_terminal_emulator(main))
    input_row.addWidget(main.terminal_emulator_stop_btn)
    main.terminal_emulator_clear_btn = QPushButton("Clear")
    main.terminal_emulator_clear_btn.clicked.connect(lambda: clear_terminal_emulator(main))
    input_row.addWidget(main.terminal_emulator_clear_btn)
    emulator_layout.addLayout(input_row)
    layout.addWidget(emulator_box, 1)
    main.tabs.addTab(tab, "Terminal")
    main._terminal_process = None
    main._terminal_cwd = ""


def clear_terminal_emulator(main: MainWindow) -> None:
    """Clear terminal output area."""
    main.terminal_emulator_output.clear()


def handle_cd_command(main: MainWindow, cmd: str, cwd: str) -> str | None:
    """Handle cd command: return new absolute path or None on error."""
    parts = cmd.split(None, 1)
    target = (parts[1].strip() if len(parts) > 1 else "").strip()
    if not target:
        target = os.environ.get("HOME", cwd)
    base = Path(cwd).resolve()
    try:
        new_path = (base / target).resolve()
        if not new_path.is_dir():
            main.terminal_emulator_output.append(f"$ {cmd}")
            main.terminal_emulator_output.append(f"[cd] No such directory: {new_path}")
            return None
        return str(new_path)
    except OSError as e:
        main.terminal_emulator_output.append(f"$ {cmd}")
        main.terminal_emulator_output.append(f"[cd] {e}")
        return None


def _on_terminal_stdout(main: MainWindow) -> None:
    if main._terminal_process:
        data = main._terminal_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        main.terminal_emulator_output.append(strip_ansi(data).rstrip("\n"))


def _on_terminal_stderr(main: MainWindow) -> None:
    if main._terminal_process:
        data = main._terminal_process.readAllStandardError().data().decode("utf-8", errors="replace")
        main.terminal_emulator_output.append(f"[stderr] {strip_ansi(data).rstrip()}")


def _on_terminal_finished(main: MainWindow, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
    main._terminal_process = None
    main.terminal_emulator_output.append(f"[done] exit_code={exit_code}")
    main.terminal_emulator_input.setEnabled(True)
    main.terminal_emulator_btn.setEnabled(True)
    main.terminal_emulator_stop_btn.setEnabled(False)


def run_terminal_emulator_command(main: MainWindow) -> None:
    """Run command from terminal input in bash subprocess."""
    cmd = (main.terminal_emulator_input.text() or "").strip()
    if not cmd:
        return
    main.terminal_emulator_input.add_to_history(cmd)
    if is_tui_command(cmd):
        main.terminal_emulator_output.append(
            f"$ {cmd}\n[Note] TUI programs (htop, vim, nano, less, etc.) need a real terminal.\n"
            "Use: ls, pwd, eurika scan ., or run htop in an external terminal."
        )
        main.terminal_emulator_input.clear()
        return
    cwd = main._terminal_cwd or main.root_edit.text().strip() or "."
    cwd = str(Path(cwd).resolve())
    if cmd == "cd" or cmd.startswith("cd "):
        new_cwd = handle_cd_command(main, cmd, cwd)
        if new_cwd is not None:
            main._terminal_cwd = new_cwd
            main.terminal_emulator_output.append(f"$ {cmd}")
            main.terminal_emulator_output.append(new_cwd)
        main.terminal_emulator_input.clear()
        return
    main.terminal_emulator_output.append(f"$ {cmd}")
    main.terminal_emulator_input.clear()
    main.terminal_emulator_input.setEnabled(False)
    main.terminal_emulator_btn.setEnabled(False)
    main.terminal_emulator_stop_btn.setEnabled(True)
    main._terminal_process = QProcess(main)
    main._terminal_process.setWorkingDirectory(cwd)
    main._terminal_process.readyReadStandardOutput.connect(lambda: _on_terminal_stdout(main))
    main._terminal_process.readyReadStandardError.connect(lambda: _on_terminal_stderr(main))
    main._terminal_process.finished.connect(
        lambda code, status: _on_terminal_finished(main, code, status)
    )
    main._terminal_process.start("bash", ["-c", cmd])


def stop_terminal_emulator(main: MainWindow) -> None:
    """Terminate running terminal process."""
    proc = main._terminal_process
    if proc is None or proc.state() == QProcess.NotRunning:
        return
    proc.terminate()
    if not proc.waitForFinished(3000):
        proc.kill()
        proc.waitForFinished(1000)
