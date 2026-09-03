"""Git-related workspace tools (mixin for WorkspaceTools)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Protocol

from .protocol import ERR_INVALID_PARAMS, ERR_TOOL_FAILED, RpcError

EventSink = Callable[[str, dict[str, Any]], None]


class _WorkspaceHost(Protocol):
    root: Path

    def resolve(self, value: str | None = None, *, must_exist: bool = False) -> Path: ...

    def _approved(self, args: dict[str, Any], operation: str) -> None: ...

    def _check_cancel(self, cancel: threading.Event) -> None: ...

    def _run_process(
        self,
        argv: list[str],
        *,
        cwd: Path,
        timeout_ms: int,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]: ...


class WorkspaceGitMixin:
    def git_diff(self: _WorkspaceHost, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        supplied = args.get("paths", [])
        if not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied):
            raise RpcError(ERR_INVALID_PARAMS, "git_diff.paths must be a string array")
        targets: list[str] = []
        for item in supplied:
            target = self.resolve(item)
            targets.append(target.relative_to(self.root).as_posix())
        argv = ["git", "diff"]
        if args.get("staged") is True:
            argv.append("--staged")
        if targets:
            argv.extend(["--", *targets])
        return self._run_process(argv, cwd=self.root, timeout_ms=30_000, cancel=cancel, emit=emit)

    def git_status(self: _WorkspaceHost, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._check_cancel(cancel)
        from eurika.api.chat_git import collect_commit_preview

        preview = collect_commit_preview(self.root)
        emit("tool/output", {"stream": "stdout", "text": str(preview.get("status") or "")})
        return preview

    def git_commit(self: _WorkspaceHost, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._approved(args, "git commit")
        self._check_cancel(cancel)
        message = str(args.get("message") or "").strip()
        if not message:
            raise RpcError(ERR_INVALID_PARAMS, "git_commit.message is required")
        supplied = args.get("paths", [])
        if supplied is None:
            supplied = []
        if not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied):
            raise RpcError(ERR_INVALID_PARAMS, "git_commit.paths must be a string array")
        paths: list[str] = []
        for item in supplied:
            target = self.resolve(item)
            paths.append(target.relative_to(self.root).as_posix())
        from eurika.api.chat_git import collect_commit_preview, commit_selected

        if not paths:
            preview = collect_commit_preview(self.root)
            paths = list(preview.get("include") or [])
        ok, output, terminal = commit_selected(self.root, message, paths)
        if output:
            emit("tool/output", {"stream": "stdout" if ok else "stderr", "text": output})
        if not ok:
            raise RpcError(ERR_TOOL_FAILED, output or "git commit failed", {"terminal": terminal})
        return {"ok": True, "output": output, "terminal": terminal, "paths": paths, "message": message}

    def git_push(self: _WorkspaceHost, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._approved(args, "git push")
        self._check_cancel(cancel)
        from eurika.api.chat_git import inspect_push, push_current_branch

        info = inspect_push(self.root)
        ok, output, terminal = push_current_branch(self.root)
        if output:
            emit("tool/output", {"stream": "stdout" if ok else "stderr", "text": output})
        if not ok:
            raise RpcError(ERR_TOOL_FAILED, output or "git push failed", {"terminal": terminal, "info": info})
        return {"ok": True, "output": output, "terminal": terminal, "info": info}
