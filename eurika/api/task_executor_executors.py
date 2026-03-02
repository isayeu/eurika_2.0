"""Task executor implementations: file ops, UI, run_tests, run_lint, run_command, refactor."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from .task_executor_helpers import (
    run_pytest,
    safe_create_empty_file,
    safe_delete_file,
    safe_write_file,
    task_backup_before_write,
    within_root,
)
from .task_executor_types import ExecutionReport, TaskSpec


def _execute_ui_add_empty_tab(root: Path, spec: TaskSpec) -> ExecutionReport:
    target_file = root / "qt_app" / "ui" / "main_window.py"
    if not target_file.exists():
        return ExecutionReport(
            ok=False,
            summary="ui tab change failed",
            error="target file not found: qt_app/ui/main_window.py",
        )
    tab_name = str(spec.entities.get("tab_name") or "New Tab").strip() or "New Tab"
    src = target_file.read_text(encoding="utf-8")
    smoke_path = root / "tests" / "test_qt_smoke.py"

    def _verify() -> Dict[str, Any]:
        if smoke_path.exists():
            return run_pytest(root, ["-q", "tests/test_qt_smoke.py"], timeout=120)
        return {"ok": True, "runner": "pytest", "output": "smoke skipped (tests/test_qt_smoke.py not found)"}

    add_line = f'self.tabs.addTab(QWidget(), "{tab_name}")'
    if add_line in src:
        verify = _verify()
        return ExecutionReport(
            ok=bool(verify.get("ok")),
            summary="tab already exists",
            skipped_steps=[f"insert {tab_name}"],
            verification=verify,
            artifacts_changed=[],
            error=None if verify.get("ok") else "smoke failed",
        )
    anchor = 'self.tabs.addTab(tab, "Chat")'
    pos = src.find(anchor)
    if pos < 0:
        return ExecutionReport(
            ok=False,
            summary="ui tab change failed",
            error="anchor not found: Chat tab",
        )
    line_end = src.find("\n", pos)
    if line_end < 0:
        line_end = len(src)
    insert_snippet = f'\n        self.tabs.addTab(QWidget(), "{tab_name}")'
    updated = src[:line_end] + insert_snippet + src[line_end:]
    task_backup_before_write(root, "qt_app/ui/main_window.py", target_file)
    target_file.write_text(updated, encoding="utf-8")
    verify = _verify()
    return ExecutionReport(
        ok=bool(verify.get("ok")),
        summary=f"added tab `{tab_name}` after Chat",
        applied_steps=[f"insert {tab_name}"],
        verification=verify,
        artifacts_changed=["qt_app/ui/main_window.py"],
        error=None if verify.get("ok") else "smoke failed",
    )


def _execute_ui_remove_tab(root: Path, spec: TaskSpec) -> ExecutionReport:
    target_file = root / "qt_app" / "ui" / "main_window.py"
    if not target_file.exists():
        return ExecutionReport(
            ok=False,
            summary="ui tab change failed",
            error="target file not found: qt_app/ui/main_window.py",
        )
    tab_name = str(spec.entities.get("tab_name") or "New Tab").strip() or "New Tab"
    src = target_file.read_text(encoding="utf-8")
    smoke_path = root / "tests" / "test_qt_smoke.py"

    def _verify() -> Dict[str, Any]:
        if smoke_path.exists():
            return run_pytest(root, ["-q", "tests/test_qt_smoke.py"], timeout=120)
        return {"ok": True, "runner": "pytest", "output": "smoke skipped (tests/test_qt_smoke.py not found)"}

    patt = re.compile(
        rf'^\s*self\.tabs\.addTab\([^,\n]+,\s*["\']{re.escape(tab_name)}["\']\)\s*$',
        re.MULTILINE,
    )
    updated, removed_count = patt.subn("", src)
    if removed_count == 0:
        verify = _verify()
        return ExecutionReport(
            ok=bool(verify.get("ok")),
            summary=f"tab `{tab_name}` already absent",
            skipped_steps=[f"remove tab `{tab_name}`"],
            verification=verify,
            artifacts_changed=[],
            error=None if verify.get("ok") else "smoke failed",
        )
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    task_backup_before_write(root, "qt_app/ui/main_window.py", target_file)
    target_file.write_text(updated, encoding="utf-8")
    verify = _verify()
    return ExecutionReport(
        ok=bool(verify.get("ok")),
        summary=f"removed tab `{tab_name}`",
        applied_steps=[f"remove tab `{tab_name}`"],
        verification=verify,
        artifacts_changed=["qt_app/ui/main_window.py"],
        error=None if verify.get("ok") else "smoke failed",
    )


def _execute_refactor(root: Path, spec: TaskSpec) -> ExecutionReport:
    dry_run = "dry-run" in (spec.message or "").lower() or "dry run" in (spec.message or "").lower()
    cmd = ["python", "-m", "eurika_cli", "fix", str(root), "--quiet"] + (["--dry-run"] if dry_run else [])
    try:
        res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return ExecutionReport(ok=False, summary="refactor timeout", error="timeout")
    out = ((res.stdout or "") + (res.stderr or "")).strip()[:4000]
    verify = {"runner": "eurika_fix", "ok": res.returncode == 0, "output": out}
    return ExecutionReport(
        ok=res.returncode == 0,
        summary="ran eurika fix" + (" (dry-run)" if dry_run else ""),
        applied_steps=["eurika fix"],
        verification=verify,
        artifacts_changed=[],
        error=None if res.returncode == 0 else f"fix exit {res.returncode}",
    )


def _execute_create(root: Path, spec: TaskSpec) -> ExecutionReport:
    ok, msg = safe_create_empty_file(root, spec.target)
    return ExecutionReport(
        ok=ok,
        summary="created empty file" if ok else "create failed",
        applied_steps=["create file"] if ok else [],
        verification={"runner": "file_ops", "ok": ok},
        artifacts_changed=[msg] if ok else [],
        error=None if ok else msg,
    )


def _execute_delete(root: Path, spec: TaskSpec) -> ExecutionReport:
    ok, msg = safe_delete_file(root, spec.target)
    return ExecutionReport(
        ok=ok,
        summary="deleted file" if ok else "delete failed",
        applied_steps=["delete file"] if ok else [],
        verification={"runner": "file_ops", "ok": ok},
        artifacts_changed=[msg] if ok else [],
        error=None if ok else msg,
    )


def _execute_save(root: Path, spec: TaskSpec) -> ExecutionReport:
    code = spec.entities.get("code", "")
    if not code.strip():
        return ExecutionReport(ok=False, summary="save failed", error="no code extracted")
    path = (root / spec.target).resolve()
    if within_root(root, path) and path.exists() and path.is_file():
        target_rel = str(path.relative_to(root))
        task_backup_before_write(root, target_rel, path)
    ok, msg = safe_write_file(root, spec.target, code)
    return ExecutionReport(
        ok=ok,
        summary="saved code file" if ok else "save failed",
        applied_steps=["write file"] if ok else [],
        verification={"runner": "file_ops", "ok": ok},
        artifacts_changed=[msg] if ok else [],
        error=None if ok else msg,
    )


def _execute_ui_tabs(_root: Path, _spec: TaskSpec) -> ExecutionReport:
    return ExecutionReport(ok=True, summary="ui tabs fetched", verification={"runner": "grounded", "ok": True})


def _execute_project_ls(root: Path, _spec: TaskSpec) -> ExecutionReport:
    try:
        _ = sorted(root.iterdir())
    except OSError as exc:
        return ExecutionReport(ok=False, summary="ls failed", error=str(exc))
    return ExecutionReport(ok=True, summary="root listing fetched", verification={"runner": "grounded", "ok": True})


def _execute_project_tree(root: Path, _spec: TaskSpec) -> ExecutionReport:
    try:
        _ = sorted(root.iterdir())
    except OSError as exc:
        return ExecutionReport(ok=False, summary="tree failed", error=str(exc))
    return ExecutionReport(ok=True, summary="project tree fetched", verification={"runner": "grounded", "ok": True})


def _execute_run_tests(root: Path, spec: TaskSpec) -> ExecutionReport:
    target = (spec.target or "").strip()
    args = ["-q"]
    if target:
        args.append(target)
    verify = run_pytest(root, args, timeout=300)
    summary = "tests passed" if verify.get("ok") else "tests failed"
    return ExecutionReport(
        ok=bool(verify.get("ok")),
        summary=summary,
        applied_steps=["run pytest"],
        verification=verify,
        artifacts_changed=[],
        error=None if verify.get("ok") else "pytest returned non-zero",
    )


def _execute_run_lint(root: Path, _spec: TaskSpec) -> ExecutionReport:
    """Run best-effort lint command from known toolchain."""
    candidates = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "flake8", "."],
        [sys.executable, "-m", "pylint", "eurika", "qt_app"],
    ]
    last_error = ""
    for cmd in candidates:
        try:
            res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return ExecutionReport(ok=False, summary="lint timeout", error="timeout")
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
            continue
        out = ((res.stdout or "") + (res.stderr or "")).strip()
        if "No module named" in out and res.returncode != 0:
            last_error = out[:300]
            continue
        return ExecutionReport(
            ok=res.returncode == 0,
            summary="lint passed" if res.returncode == 0 else "lint failed",
            applied_steps=["run lint"],
            verification={"runner": "lint", "ok": res.returncode == 0, "exit_code": res.returncode, "output": out[:4000]},
            artifacts_changed=[],
            error=None if res.returncode == 0 else "lint returned non-zero",
        )
    return ExecutionReport(ok=False, summary="lint unavailable", error=last_error or "no lint tool available")


def _is_allowed_command(parts: List[str]) -> tuple[bool, str]:
    if not parts:
        return False, "empty command"
    first = parts[0]
    if first in {"eurika"}:
        return True, ""
    if first in {"pytest"}:
        return True, ""
    if first == "python":
        if len(parts) >= 3 and parts[1] == "-m" and parts[2] in {"pytest", "eurika_cli"}:
            return True, ""
        return False, "python command is allowed only with -m pytest or -m eurika_cli"
    return False, f"command not allowed: {first}"


def _execute_run_command(root: Path, spec: TaskSpec) -> ExecutionReport:
    command = (spec.target or "").strip()
    if not command:
        return ExecutionReport(ok=False, summary="command failed", error="empty command")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return ExecutionReport(ok=False, summary="command parse failed", error=str(exc))
    allowed, reason = _is_allowed_command(parts)
    if not allowed:
        return ExecutionReport(ok=False, summary="command rejected", error=reason)
    try:
        res = subprocess.run(parts, cwd=str(root), capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return ExecutionReport(ok=False, summary="command timeout", error="timeout")
    except Exception as exc:  # pragma: no cover
        return ExecutionReport(ok=False, summary="command failed", error=str(exc))
    out = ((res.stdout or "") + (res.stderr or "")).strip()
    return ExecutionReport(
        ok=res.returncode == 0,
        summary="command passed" if res.returncode == 0 else "command failed",
        applied_steps=[f"run `{command}`"],
        verification={"runner": "command", "ok": res.returncode == 0, "exit_code": res.returncode, "output": out[:4000]},
        artifacts_changed=[],
        error=None if res.returncode == 0 else f"exit {res.returncode}",
    )
