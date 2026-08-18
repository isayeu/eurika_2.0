"""Safe workspace-confined implementations of local coding tools."""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .protocol import (
    ERR_APPROVAL_REQUIRED,
    ERR_CANCELLED,
    ERR_INVALID_PARAMS,
    ERR_TIMEOUT,
    ERR_TOOL_FAILED,
    ERR_WORKSPACE_VIOLATION,
    RpcError,
)

EventSink = Callable[[str, dict[str, Any]], None]
_IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
_SEARCH_KIND_RANK = {"implementation": 0, "docs": 1, "test": 2}
_SYMBOL_LINE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:(?:async\s+)?def|class|function|"
    r"interface|type|enum|struct|trait|const|let|var)\s+([A-Za-z_$][\w$]*)"
)


def _search_source_kind(relative: str) -> str:
    posix = relative.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1]
    if (
        posix == "tests"
        or posix.startswith("tests/")
        or "/tests/" in f"/{posix}/"
        or name.startswith("test_")
        or ".test." in name
        or name.endswith("_test.py")
    ):
        return "test"
    if posix.startswith("docs/") or posix.endswith(".md"):
        return "docs"
    return "implementation"


class WorkspaceTools:
    """Structured tools whose filesystem access cannot escape one root."""

    def __init__(self, root: str | Path) -> None:
        candidate = Path(root).expanduser()
        if not candidate.is_dir():
            raise RpcError(ERR_INVALID_PARAMS, f"Workspace root is not a directory: {candidate}")
        self.root = candidate.resolve(strict=True)

    def resolve(self, value: str | None = None, *, must_exist: bool = False) -> Path:
        raw = value or "."
        supplied = Path(raw)
        if supplied.is_absolute():
            try:
                absolute = supplied.expanduser().resolve(strict=False)
                raw = absolute.relative_to(self.root).as_posix()
                supplied = Path(raw)
            except ValueError as exc:
                raise RpcError(
                    ERR_WORKSPACE_VIOLATION,
                    "Paths must be workspace-relative",
                    {"path": value},
                ) from exc
        try:
            target = (self.root / supplied).resolve(strict=False)
        except OSError as exc:
            raise RpcError(ERR_INVALID_PARAMS, f"Could not resolve path: {exc}", {"path": raw}) from exc
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise RpcError(ERR_WORKSPACE_VIOLATION, "Path escapes workspace root", {"path": raw}) from exc
        if must_exist and not target.exists():
            raise RpcError(ERR_INVALID_PARAMS, "Path does not exist", {"path": raw})
        return target

    @staticmethod
    def _approved(args: dict[str, Any], operation: str) -> None:
        if args.get("approval") is not True:
            raise RpcError(
                ERR_APPROVAL_REQUIRED,
                f"Explicit approval is required for {operation}",
                {"operation": operation, "requiresApproval": True},
            )

    @staticmethod
    def _check_cancel(cancel: threading.Event) -> None:
        if cancel.is_set():
            raise RpcError(ERR_CANCELLED, "Request cancelled")

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        handlers = {
            "search": self.search,
            "read": self.read,
            "market_status": self.market_status,
            "edit": self.edit,
            "terminal": self.terminal,
            "diagnostics": self.diagnostics,
            "tests": self.tests,
            "git_diff": self.git_diff,
        }
        handler = handlers.get(name)
        if handler is None:
            raise RpcError(ERR_INVALID_PARAMS, f"Unknown tool: {name}")
        return handler(args, cancel=cancel, emit=emit)

    def market_status(
        self,
        _args: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        """Return factual paper-Market state without executing shell commands."""
        self._check_cancel(cancel)
        from eurika.ml.learning_status import (
            format_market_situation_block,
            market_economic_verdict,
            market_learning_status,
        )
        from eurika.ml.root import resolve_market_root

        root = resolve_market_root()
        status = market_learning_status(root)
        return {
            "marketRoot": str(root),
            "summary": format_market_situation_block(root),
            "verdict": market_economic_verdict(status),
            "paper": status.get("paper"),
            "live": status.get("live"),
            "portfolio": status.get("portfolio"),
            "pnl": status.get("pnl"),
            "opens": status.get("opens"),
            "model": status.get("model"),
            "market": status.get("market"),
        }

    def search(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query:
            raise RpcError(ERR_INVALID_PARAMS, "search.query must be a non-empty string")
        scope = self.resolve(str(args.get("path") or "."), must_exist=True)
        if not scope.is_dir():
            raise RpcError(ERR_INVALID_PARAMS, "search.path must name a directory")
        limit = max(1, min(int(args.get("maxResults", 100)), 1000))
        flags = 0 if args.get("caseSensitive") else re.IGNORECASE
        symbol_mode = args.get("mode") == "symbol"
        try:
            pattern = re.compile(query if args.get("regex") else re.escape(query), flags)
        except re.error as exc:
            raise RpcError(ERR_INVALID_PARAMS, f"Invalid search regex: {exc}") from exc
        glob_pattern = str(args.get("glob") or "*")
        results: list[dict[str, Any]] = []
        gather_limit = min(max(limit * 8, limit), 1000)
        scanned_all = True
        for path in self._search_files(scope):
            self._check_cancel(cancel)
            relative = path.relative_to(self.root).as_posix()
            if not fnmatch.fnmatch(relative, glob_pattern) and not fnmatch.fnmatch(path.name, glob_pattern):
                continue
            try:
                safe_path = self.resolve(relative, must_exist=True)
                if not safe_path.is_file() or safe_path.stat().st_size > 2_000_000:
                    continue
                text = safe_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, RpcError):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                symbol = _SYMBOL_LINE.match(line) if symbol_mode else None
                candidate = symbol.group(1) if symbol else line
                if symbol_mode and symbol is None:
                    continue
                match = pattern.search(candidate)
                if match:
                    column = (symbol.start(1) if symbol else match.start()) + 1
                    item = {
                        "path": relative,
                        "line": number,
                        "column": column,
                        "text": line[:1000],
                        "kind": _search_source_kind(relative),
                    }
                    if symbol:
                        item["symbol"] = symbol.group(1)
                    results.append(item)
                    if len(results) >= gather_limit:
                        scanned_all = False
                        break
            if not scanned_all:
                break
        results.sort(key=lambda item: (_SEARCH_KIND_RANK[item["kind"]], item["path"], item["line"]))
        return {
            "matches": results[:limit],
            "truncated": (not scanned_all) or len(results) > limit,
        }

    def _search_files(self, scope: Path) -> list[Path]:
        """Prefer Git's ignore engine, then fall back to a safe filesystem walk."""
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "-co", "--exclude-standard", "-z"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if completed.returncode == 0:
                files: list[Path] = []
                for raw in completed.stdout.split(b"\0"):
                    if not raw:
                        continue
                    try:
                        relative = raw.decode("utf-8")
                        candidate = self.resolve(relative, must_exist=True)
                        candidate.relative_to(scope)
                    except (UnicodeError, OSError, ValueError, RpcError):
                        continue
                    files.append(candidate)
                return files
        except (OSError, subprocess.SubprocessError):
            pass
        files = []
        for directory, dirnames, filenames in os.walk(scope, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in _IGNORED_DIRS]
            files.extend(Path(directory) / filename for filename in filenames)
        return files

    def read(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        path_value = args.get("path")
        if not isinstance(path_value, str):
            raise RpcError(ERR_INVALID_PARAMS, "read.path must be a string")
        path = self.resolve(path_value, must_exist=True)
        if not path.is_file():
            raise RpcError(ERR_INVALID_PARAMS, "read.path must name a file")
        self._check_cancel(cancel)
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise RpcError(ERR_TOOL_FAILED, f"Could not read UTF-8 file: {exc}") from exc
        lines = text.splitlines(keepends=True)
        start = max(1, int(args.get("startLine", 1)))
        end = min(len(lines), int(args.get("endLine", len(lines))))
        content = "".join(lines[start - 1 : end]) if end >= start else ""
        return {
            "path": path.relative_to(self.root).as_posix(),
            "content": content,
            "startLine": start,
            "endLine": end,
            "totalLines": len(lines),
            "version": hashlib.sha256(raw).hexdigest(),
        }

    def edit(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        self._approved(args, "edit")
        batch = args.get("edits")
        if batch is not None:
            if not isinstance(batch, list) or not batch or not all(isinstance(item, dict) for item in batch):
                raise RpcError(ERR_INVALID_PARAMS, "edit.edits must be a non-empty array of objects")
            snapshots: list[tuple[Path, bytes | None]] = []
            for item in batch:
                path_value = item.get("path")
                if not isinstance(path_value, str):
                    raise RpcError(ERR_INVALID_PARAMS, "Every batch edit requires a path")
                path = self.resolve(path_value)
                snapshots.append((path, path.read_bytes() if path.is_file() else None))
            results: list[dict[str, Any]] = []
            try:
                for item in batch:
                    results.append(
                        self.edit(
                            {**item, "approval": True},
                            cancel=cancel,
                            emit=emit,
                        )
                    )
            except Exception:
                for path, content in snapshots:
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)
                raise
            return {"files": results}
        path_value = args.get("path")
        if not isinstance(path_value, str):
            raise RpcError(ERR_INVALID_PARAMS, "edit.path must be a string")
        path = self.resolve(path_value)
        exists = path.exists()
        if not exists and args.get("create") is not True:
            raise RpcError(ERR_INVALID_PARAMS, "File does not exist; set create=true to create it")
        if exists and not path.is_file():
            raise RpcError(ERR_INVALID_PARAMS, "edit.path must name a file")
        try:
            current_bytes = path.read_bytes() if exists else b""
            current = current_bytes.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise RpcError(ERR_TOOL_FAILED, f"Could not read target file: {exc}") from exc
        expected = args.get("expectedVersion")
        actual = hashlib.sha256(current_bytes).hexdigest()
        if expected is not None and expected != actual:
            raise RpcError(ERR_TOOL_FAILED, "File changed since it was read", {"expectedVersion": expected, "actualVersion": actual})
        if isinstance(args.get("content"), str):
            updated = args["content"]
        elif isinstance(args.get("oldText"), str) and isinstance(args.get("newText"), str):
            old = args["oldText"]
            occurrences = current.count(old)
            if occurrences != 1:
                raise RpcError(ERR_TOOL_FAILED, "oldText must occur exactly once", {"occurrences": occurrences})
            updated = current.replace(old, args["newText"], 1)
        else:
            raise RpcError(ERR_INVALID_PARAMS, "edit requires content or oldText/newText")
        self._check_cancel(cancel)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            self._check_cancel(cancel)
            os.replace(temporary, path)
            temporary = None
        except OSError as exc:
            raise RpcError(ERR_TOOL_FAILED, f"Could not write file: {exc}") from exc
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
        encoded = updated.encode("utf-8")
        return {
            "path": path.relative_to(self.root).as_posix(),
            "created": not exists,
            "bytes": len(encoded),
            "version": hashlib.sha256(encoded).hexdigest(),
        }

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
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
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

    def diagnostics(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
        supplied = args.get("paths")
        if supplied is not None and (not isinstance(supplied, list) or not all(isinstance(item, str) for item in supplied)):
            raise RpcError(ERR_INVALID_PARAMS, "diagnostics.paths must be a string array")
        paths: list[Path] = []
        if supplied:
            for item in supplied:
                candidate = self.resolve(item, must_exist=True)
                paths.extend(candidate.rglob("*.py") if candidate.is_dir() else [candidate])
        else:
            paths = list(self.root.rglob("*.py"))
        diagnostics: list[dict[str, Any]] = []
        checked = 0
        for path in paths:
            self._check_cancel(cancel)
            relative = path.relative_to(self.root)
            if any(part in _IGNORED_DIRS for part in relative.parts):
                continue
            safe = self.resolve(relative.as_posix(), must_exist=True)
            if not safe.is_file() or safe.suffix != ".py":
                continue
            checked += 1
            try:
                ast.parse(safe.read_text(encoding="utf-8"), filename=relative.as_posix())
            except SyntaxError as exc:
                diagnostics.append(
                    {
                        "path": relative.as_posix(),
                        "line": exc.lineno or 1,
                        "column": exc.offset or 1,
                        "severity": "error",
                        "message": exc.msg,
                        "source": "python",
                    }
                )
            except (OSError, UnicodeError) as exc:
                diagnostics.append(
                    {"path": relative.as_posix(), "line": 1, "column": 1, "severity": "error", "message": str(exc), "source": "io"}
                )
        return {"diagnostics": diagnostics, "checked": checked}

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

    def git_diff(self, args: dict[str, Any], *, cancel: threading.Event, emit: EventSink) -> dict[str, Any]:
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
