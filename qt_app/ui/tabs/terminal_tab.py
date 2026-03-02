"""Terminal tab: output from Commands + manual shell. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess
from PySide6.QtGui import QTextCursor
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
    main.terminal_emulator_stop_btn.clicked.connect(lambda: stop_terminal_or_command(main))
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


def _append_stream(main: MainWindow, text: str) -> None:
    """Append text as a stream (preserves horizontal flow: dots on one line, etc.)."""
    te = main.terminal_emulator_output
    cursor = te.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(text)
    te.setTextCursor(cursor)
    te.ensureCursorVisible()


def _on_terminal_stdout(main: MainWindow) -> None:
    if main._terminal_process:
        data = main._terminal_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        _append_stream(main, strip_ansi(data))


def _on_terminal_stderr(main: MainWindow) -> None:
    if main._terminal_process:
        data = main._terminal_process.readAllStandardError().data().decode("utf-8", errors="replace")
        _append_stream(main, f"[stderr] {strip_ansi(data)}")


def _on_terminal_finished(main: MainWindow, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
    main._terminal_process = None
    main.terminal_emulator_output.append(f"[done] exit_code={exit_code}")
    main.terminal_emulator_input.setEnabled(True)
    main.terminal_emulator_btn.setEnabled(True)
    # Keep Stop enabled if CommandService (scan/doctor/fix) is still running
    cmd_running = main._command_service.state in ("thinking", "stopping")
    main.terminal_emulator_stop_btn.setEnabled(cmd_running)


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


def stop_terminal_or_command(main: MainWindow) -> None:
    """Stop CommandService command (scan/doctor/fix) or terminal emulator — whichever is running."""
    if main._command_service.state in ("thinking", "stopping"):
        main._command_service.stop()
        return
    stop_terminal_emulator(main)


def stop_terminal_emulator(main: MainWindow) -> None:
    """Terminate running terminal process."""
    proc = main._terminal_process
    if proc is None or proc.state() == QProcess.NotRunning:
        return
    proc.terminate()
    if not proc.waitForFinished(3000):
        proc.kill()
        proc.waitForFinished(1000)


def execute_command_from_chat(main: MainWindow, cmd: str) -> bool:
    """Run shell command from Chat (release_check, ls, eurika scan, etc.).
    Returns True if started, False if terminal busy.
    """
    return _run_command_in_terminal(main, cmd, result_holder=None)


def run_command_with_result(main: MainWindow, cmd: str, result_holder: list) -> None:
    """Run command, stream to terminal, put (output, exit_code) in result_holder when done.
    Uses subprocess for reliable output capture (QProcess buffer had cross-thread issues).
    """
    cmd = (cmd or "").strip()
    if not cmd:
        result_holder[:] = [("", -1)]
        return
    proc = getattr(main, "_terminal_process", None)
    if proc is not None and proc.state() != QProcess.NotRunning:
        result_holder[:] = [("terminal busy", -1)]
        return
    cwd = getattr(main, "_terminal_cwd", None) or (main.root_edit.text() or ".").strip()
    cwd = str(Path(cwd).resolve())
    main.terminal_emulator_input.setEnabled(False)
    main.terminal_emulator_btn.setEnabled(False)
    main.terminal_emulator_stop_btn.setEnabled(True)
    try:
        r = subprocess.run(
            ["bash", "-c", cmd],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=None,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        out_clean = strip_ansi(out)
        _append_stream(main, out_clean)
        main.terminal_emulator_output.append(f"[done] exit_code={r.returncode}")
        result_holder[:] = [(out_clean, r.returncode)]
    except subprocess.TimeoutExpired:
        result_holder[:] = [("timeout", -1)]
    except Exception as e:
        result_holder[:] = [(str(e), -1)]
    finally:
        main.terminal_emulator_input.setEnabled(True)
        main.terminal_emulator_btn.setEnabled(True)


def _run_command_in_terminal(
    main: MainWindow, cmd: str, result_holder: list | None = None
) -> bool:
    """Internal: run command, optionally accumulate output into result_holder[0] when done."""
    cmd = (cmd or "").strip()
    if not cmd:
        if result_holder is not None:
            result_holder[:] = [("", -1)]
        return False
    proc = getattr(main, "_terminal_process", None)
    if proc is not None and proc.state() != QProcess.NotRunning:
        if result_holder is not None:
            result_holder[:] = [("terminal busy", -1)]
        return False
    cwd = getattr(main, "_terminal_cwd", None) or (main.root_edit.text() or ".").strip()
    cwd = str(Path(cwd).resolve())
    main.terminal_emulator_input.setEnabled(False)
    main.terminal_emulator_btn.setEnabled(False)
    main.terminal_emulator_stop_btn.setEnabled(True)
    output_buffer: list[str] = [] if result_holder is not None else []
    process = QProcess(main)
    process.setWorkingDirectory(cwd)

    def _on_stdout() -> None:
        if process:
            data = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
            text = strip_ansi(data)
            _append_stream(main, text)
            if output_buffer is not None:
                output_buffer.append(text)

    def _on_stderr() -> None:
        if process:
            data = process.readAllStandardError().data().decode("utf-8", errors="replace")
            text = f"[stderr] {strip_ansi(data)}"
            _append_stream(main, text)
            if output_buffer is not None:
                output_buffer.append(text)

    def _on_finished(code: int, status: QProcess.ExitStatus) -> None:
        # Read any remaining data (QProcess can emit finished before all readyRead)
        if process:
            leftover_out = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
            leftover_err = process.readAllStandardError().data().decode("utf-8", errors="replace")
            if leftover_out:
                output_buffer.append(strip_ansi(leftover_out))
                _append_stream(main, strip_ansi(leftover_out))
            if leftover_err:
                txt = f"[stderr] {strip_ansi(leftover_err)}"
                output_buffer.append(txt)
                _append_stream(main, txt)
        main._terminal_process = None
        main.terminal_emulator_output.append(f"[done] exit_code={code}")
        main.terminal_emulator_input.setEnabled(True)
        main.terminal_emulator_btn.setEnabled(True)
        cmd_running = main._command_service.state in ("thinking", "stopping")
        main.terminal_emulator_stop_btn.setEnabled(cmd_running)
        if result_holder is not None:
            result_holder[:] = [("".join(output_buffer), code)]

    main._terminal_process = process
    process.readyReadStandardOutput.connect(_on_stdout)
    process.readyReadStandardError.connect(_on_stderr)
    process.finished.connect(_on_finished)
    process.start("bash", ["-c", cmd])
    if result_holder is not None:
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop(main)
        process.finished.connect(loop.quit)
        loop.exec()
    return True
