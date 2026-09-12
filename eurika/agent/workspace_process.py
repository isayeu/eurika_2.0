"""Process/terminal-related workspace tools (mixin for WorkspaceTools)."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .protocol import (
    ERR_CANCELLED,
    ERR_INVALID_PARAMS,
    ERR_TIMEOUT,
    ERR_TOOL_FAILED,
    RpcError,
)

EventSink = Callable[[str, dict[str, Any]], None]


class WorkspaceProcessMixin:
    """Mixin for WorkspaceTools: host provides ``root``, ``resolve``, ``_approved``."""

    root: Path

    def resolve(self, value: str | None = None, *, must_exist: bool = False) -> Path:
        raise NotImplementedError

    def _approved(self, args: dict[str, Any], operation: str) -> None:
        raise NotImplementedError

    def _check_cancel(self, cancel: threading.Event) -> None:
        if cancel.is_set():
            raise RpcError(ERR_CANCELLED, "Request cancelled")

    def _run_process(
        self,
        argv: list[str],
        *,
        cwd: Path,
        timeout_ms: int,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            from eurika.utils.env import child_process_environ

            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                env=child_process_environ(),
            )
        except OSError as exc:
            raise RpcError(ERR_TOOL_FAILED, f"Could not start command: {exc}") from exc
        while True:
            if cancel.is_set():
                process.kill()
                process.communicate()
                raise RpcError(ERR_CANCELLED, "Request cancelled")
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if elapsed_ms >= timeout_ms:
                process.kill()
                process.communicate()
                raise RpcError(ERR_TIMEOUT, f"Command timed out after {timeout_ms} ms")
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, (timeout_ms - elapsed_ms) / 1000))
                break
            except subprocess.TimeoutExpired:
                continue
        if stdout:
            emit("tool/output", {"stream": "stdout", "text": stdout})
        if stderr:
            emit("tool/output", {"stream": "stderr", "text": stderr})
        return {
            "argv": argv,
            "cwd": cwd.relative_to(self.root).as_posix() or ".",
            "exitCode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "durationMs": int((time.monotonic() - started) * 1000),
        }

    def terminal(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._approved(args, "terminal command")
        argv = args.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise RpcError(ERR_INVALID_PARAMS, "terminal.argv must be a non-empty string array")
        cwd = self.resolve(str(args.get("cwd") or "."), must_exist=True)
        if not cwd.is_dir():
            raise RpcError(ERR_INVALID_PARAMS, "terminal.cwd must name a directory")
        timeout_ms = max(1, min(int(args.get("timeoutMs", 120_000)), 3_600_000))
        return self._run_process(argv, cwd=cwd, timeout_ms=timeout_ms, cancel=cancel, emit=emit)

    def tests(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._approved(args, "tests")
        supplied = args.get("paths", [])
        extra = args.get("extraArgs", [])
        if not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied):
            raise RpcError(ERR_INVALID_PARAMS, "tests.paths must be a string array")
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            raise RpcError(ERR_INVALID_PARAMS, "tests.extraArgs must be a string array")
        targets: list[str] = []
        for item in supplied:
            target = self.resolve(item, must_exist=True)
            targets.append(target.relative_to(self.root).as_posix())
        argv = [sys.executable, "-m", "pytest", *targets, *extra]
        timeout_ms = max(1, min(int(args.get("timeoutMs", 300_000)), 3_600_000))
        return self._run_process(argv, cwd=self.root, timeout_ms=timeout_ms, cancel=cancel, emit=emit)

    def skill(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        """Named product rituals — same implementations as Chat handlers, as a tool."""
        self._check_cancel(cancel)
        name = str(args.get("name") or "").strip()
        allowed = {"release_check", "scan", "ritual", "self_check", "self_model"}
        if name not in allowed:
            raise RpcError(ERR_INVALID_PARAMS, f"Unknown skill: {name}")
        emit("skill/started", {"name": name})
        if name == "release_check":
            from eurika.api.chat_tools import run_release_check
            from eurika.api.last_check import seal_check_verification

            ok, output = run_release_check(self.root)
            seal_check_verification(
                self.root,
                {
                    "ok": ok,
                    "runner": "release_check",
                    "command": ["./scripts/release_check.sh"],
                    "exit_code": 0 if ok else 1,
                    "output": output,
                },
            )
            return {"ok": ok, "name": name, "output": (output or "")[-8000:]}
        if name == "scan":
            from eurika.api.chat_tools import run_eurika_command

            ok, output = run_eurika_command(self.root, "scan")
            return {"ok": ok, "name": name, "output": (output or "")[-8000:]}
        if name == "ritual":
            from eurika.api.chat_tools import run_eurika_ritual

            ok, output = run_eurika_ritual(self.root)
            return {"ok": ok, "name": name, "output": (output or "")[-8000:]}
        if name == "self_check":
            from eurika.api.chat_tools import run_eurika_command

            ok, output = run_eurika_command(self.root, "self-check")
            return {"ok": ok, "name": name, "output": (output or "")[-8000:]}
        from eurika.api.self_model import format_self_model_text, load_self_model

        snap = load_self_model(self.root, refresh=True, persist=True)
        text = format_self_model_text(snap, mode="full")
        return {"ok": True, "name": name, "output": text}
