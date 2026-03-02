"""Command execution service for Qt UI using QProcess."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from eurika.orchestration.cycle_state import CycleState
from qt_app.services.command_builder import build_cli_args


class CommandService(QObject):
    """Run Eurika CLI commands with live output and stop/cancel support."""

    output_line = Signal(str)
    error_line = Signal(str)
    state_changed = Signal(str)
    command_started = Signal(str)
    command_finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._state = CycleState.IDLE.value
        self._active_command = ""
        self._wire_process()

    @property
    def state(self) -> str:
        return self._state

    @property
    def active_command(self) -> str:
        """Last executed command string (e.g. 'eurika fix .')."""
        return self._active_command

    def _wire_process(self) -> None:
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

    def _set_state(self, state: str) -> None:
        self._state = state
        self.state_changed.emit(state)

    def start(
        self,
        *,
        command: str,
        project_root: str,
        module: str = "",
        window: int = 5,
        dry_run: bool = False,
        no_llm: bool = False,
        no_clean_imports: bool = False,
        no_code_smells: bool = False,
        use_llm_extract: bool = False,
        allow_low_risk_campaign: bool = False,
        team_mode: bool = False,
        ollama_model: str = "",
    ) -> None:
        if self._process.state() != QProcess.NotRunning:
            self.error_line.emit("A command is already running.")
            return

        try:
            args = build_cli_args(
                command=command,
                project_root=project_root,
                module=module,
                window=window,
                dry_run=dry_run,
                no_llm=no_llm,
                no_clean_imports=no_clean_imports,
                no_code_smells=no_code_smells,
                allow_low_risk_campaign=allow_low_risk_campaign,
                team_mode=team_mode,
            )
        except ValueError as exc:
            self.error_line.emit(str(exc))
            return

        root = str(Path(project_root).resolve())
        full_args = ["-m", "eurika_cli"] + args
        self._active_command = " ".join(["eurika"] + args)
        self.command_started.emit(self._active_command)
        self._set_state(CycleState.THINKING.value)
        self._process.setWorkingDirectory(root)
        if ollama_model.strip() or use_llm_extract:
            env = QProcessEnvironment.systemEnvironment()
            if ollama_model.strip():
                env.insert("OLLAMA_OPENAI_MODEL", ollama_model.strip())
            if use_llm_extract:
                env.insert("EURIKA_USE_LLM_EXTRACT", "1")
            self._process.setProcessEnvironment(env)
        self._process.start(sys.executable, full_args)

    def run_apply_approved(self, *, project_root: str) -> None:
        if self._process.state() != QProcess.NotRunning:
            self.error_line.emit("A command is already running.")
            return
        root = str(Path(project_root or ".").resolve())
        args = ["-m", "eurika_cli", "fix", root, "--apply-approved"]
        self._active_command = f"eurika fix {root} --apply-approved"
        self.command_started.emit(self._active_command)
        self._set_state(CycleState.THINKING.value)
        self._process.setWorkingDirectory(root)
        self._process.start(sys.executable, args)

    def run_ruff(self, *, project_root: str) -> None:
        """Run ruff check eurika cli from project root. Uses .venv if present."""
        if self._process.state() != QProcess.NotRunning:
            self.error_line.emit("A command is already running.")
            return
        root = Path(project_root or ".").resolve()
        ruff_exe = root / ".venv" / "bin" / "ruff"
        cmd = str(ruff_exe) if ruff_exe.is_file() else "ruff"
        args = ["check", "eurika", "cli"]
        self._active_command = f"{cmd} {' '.join(args)}"
        self.command_started.emit(self._active_command)
        self._set_state(CycleState.THINKING.value)
        self._process.setWorkingDirectory(str(root))
        self._process.start(cmd, args)

    def run_mypy(self, *, project_root: str) -> None:
        """Run mypy eurika cli from project root. Uses .venv if present."""
        if self._process.state() != QProcess.NotRunning:
            self.error_line.emit("A command is already running.")
            return
        root = Path(project_root or ".").resolve()
        py_exe = root / ".venv" / "bin" / "python"
        if py_exe.is_file():
            exe = str(py_exe)
            args = ["-m", "mypy", "eurika", "cli"]
        else:
            exe = sys.executable
            args = ["-m", "mypy", "eurika", "cli"]
        self._active_command = f"{exe} -m mypy eurika cli"
        self.command_started.emit(self._active_command)
        self._set_state(CycleState.THINKING.value)
        self._process.setWorkingDirectory(str(root))
        self._process.start(exe, args)

    def run_release_check(self, *, project_root: str) -> None:
        """Run scripts/release_check.sh from project root (CR-F1, CR-B2)."""
        if self._process.state() != QProcess.NotRunning:
            self.error_line.emit("A command is already running.")
            return
        root = Path(project_root or ".").resolve()
        script = root / "scripts" / "release_check.sh"
        if not script.is_file():
            self.error_line.emit(f"scripts/release_check.sh not found in {root}")
            return
        self._active_command = "./scripts/release_check.sh"
        self.command_started.emit(self._active_command)
        self._set_state(CycleState.THINKING.value)
        self._process.setWorkingDirectory(str(root))
        self._process.start("bash", [str(script)])

    def stop(self) -> None:
        if self._process.state() == QProcess.NotRunning:
            return
        self._set_state("stopping")  # transient; will become error/done on finish
        self._process.terminate()
        QTimer.singleShot(2000, self._kill_if_still_running)

    def shutdown(self, *, timeout_ms: int = 1500) -> None:
        """Terminate running command process during app shutdown."""
        if self._process.state() == QProcess.NotRunning:
            return
        self._set_state("stopping")
        self._process.terminate()
        if self._process.waitForFinished(timeout_ms):
            self._set_state(CycleState.IDLE.value)
            return
        self._process.kill()
        self._process.waitForFinished(timeout_ms)
        self._set_state(CycleState.IDLE.value)

    def _kill_if_still_running(self) -> None:
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def _on_stdout(self) -> None:
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.output_line.emit(data)

    def _on_stderr(self) -> None:
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.error_line.emit(data)

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self.command_finished.emit(exit_code)
        # R2: explicit state model — emit done/error before returning to idle
        terminal = CycleState.DONE if exit_code == 0 else CycleState.ERROR
        self._set_state(terminal.value)
        QTimer.singleShot(300, lambda: self._set_state(CycleState.IDLE.value))

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        msg = self._process.errorString() or "Unknown process error"
        self.error_line.emit(msg)

