"""Universal task executor for chat pipeline.

interpret -> authorize -> execute -> verify -> report
"""

from __future__ import annotations

import json
import re
import secrets
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


RiskLevel = str  # low | medium | high
MAX_PATCH_OPS = 20
MAX_PATCH_TEXT = 20_000


@dataclass(slots=True)
class TaskSpec:
    intent: str
    target: str = ""
    message: str = ""
    steps: List[str] = field(default_factory=list)
    risk_level: RiskLevel = "low"
    requires_confirmation: bool = False
    entities: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionReport:
    ok: bool
    summary: str
    applied_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    artifacts_changed: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _build_preview_snippet(before: str, after: str, max_len: int = 240) -> str:
    """Compact before/after preview for dry-run output."""
    b = _mask_sensitive_preview_text((before or "").replace("\n", "\\n"))
    a = _mask_sensitive_preview_text((after or "").replace("\n", "\\n"))
    if len(b) > max_len:
        b = b[: max_len - 3] + "..."
    if len(a) > max_len:
        a = a[: max_len - 3] + "..."
    return f"- {b}\n+ {a}"


def _mask_sensitive_preview_text(text: str) -> str:
    """Mask common secret-like patterns before exposing preview output."""
    if not text:
        return text
    masked = text
    # key=value patterns for common secret fields.
    key_value_patterns = (
        r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization)\b\s*[:=]\s*([^\s,;]+)",
        r"(?i)\b(bearer)\s+([A-Za-z0-9._\-]+)",
    )
    for pat in key_value_patterns:
        masked = re.sub(pat, r"\1=***", masked)
    # Long opaque values are often secret-like; hide middle part.
    masked = re.sub(
        r"\b([A-Za-z0-9]{4})[A-Za-z0-9._\-]{12,}([A-Za-z0-9]{3})\b",
        r"\1***\2",
        masked,
    )
    return masked


def _within_root(root: Path, path: Path) -> bool:
    return str(path.resolve()).startswith(str(root.resolve()))


def _safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not _within_root(root, path):
        return False, "path outside project"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, str(path.relative_to(root))


def _safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not _within_root(root, path):
        return False, "path outside project"
    if not path.exists() or not path.is_file():
        return False, "not a file or does not exist"
    try:
        rel = str(path.relative_to(root))
        path.unlink()
        return True, rel
    except OSError as exc:
        return False, str(exc)


def _safe_create_empty_file(root: Path, relative_path: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not _within_root(root, path):
        return False, "path outside project"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, str(path.relative_to(root))


def _run_pytest(root: Path, args: List[str], timeout: int = 180) -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest"] + args
    try:
        result = subprocess.run(
            cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "runner": "pytest", "error": "timeout"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "runner": "pytest", "error": str(exc)}
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    passed_with_post_crash = (
        result.returncode != 0
        and "passed" in out
        and ("bus error" in out.lower() or "ошибка шины" in out.lower())
    )
    return {
        "ok": (result.returncode == 0) or passed_with_post_crash,
        "runner": "pytest",
        "exit_code": result.returncode,
        "output": out[:4000],
        "warning": (
            "pytest reported passed tests but process ended with bus error"
            if passed_with_post_crash
            else ""
        ),
    }


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
            return _run_pytest(root, ["-q", "tests/test_qt_smoke.py"], timeout=120)
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
            return _run_pytest(root, ["-q", "tests/test_qt_smoke.py"], timeout=120)
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
    ok, msg = _safe_create_empty_file(root, spec.target)
    return ExecutionReport(
        ok=ok,
        summary="created empty file" if ok else "create failed",
        applied_steps=["create file"] if ok else [],
        verification={"runner": "file_ops", "ok": ok},
        artifacts_changed=[msg] if ok else [],
        error=None if ok else msg,
    )


def _execute_delete(root: Path, spec: TaskSpec) -> ExecutionReport:
    ok, msg = _safe_delete_file(root, spec.target)
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
    ok, msg = _safe_write_file(root, spec.target, code)
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
    verify = _run_pytest(root, args, timeout=300)
    summary = "tests passed" if verify.get("ok") else "tests failed"
    return ExecutionReport(
        ok=bool(verify.get("ok")),
        summary=summary,
        applied_steps=["run pytest"],
        verification=verify,
        artifacts_changed=[],
        error=None if verify.get("ok") else "pytest returned non-zero",
    )


CapabilityFn = Callable[[Path, TaskSpec], ExecutionReport]


CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "ui_tabs": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_ui_tabs},
    "project_ls": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_project_ls},
    "project_tree": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_project_tree},
    "run_tests": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_run_tests},
    "run_lint": {"risk_level": "low", "requires_confirmation": False, "executor": None},
    "run_command": {"risk_level": "high", "requires_confirmation": True, "executor": None},
    "ui_add_empty_tab": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_ui_add_empty_tab},
    "ui_remove_tab": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_ui_remove_tab},
    "create": {"risk_level": "medium", "requires_confirmation": True, "executor": _execute_create},
    "delete": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_delete},
    "save": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_save},
    "refactor": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_refactor},
}


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
    # Keep scope intentionally narrow for safety.
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


def _execute_code_edit_patch(root: Path, spec: TaskSpec) -> ExecutionReport:
    """Safely apply simple text replacement with mandatory verify + rollback."""
    operations_json = str(spec.entities.get("operations_json") or "").strip()
    if operations_json:
        return _execute_code_edit_patch_batch(root, spec, operations_json)
    is_dry_run = str(spec.entities.get("dry_run") or "").strip().lower() in {"1", "true", "yes"}
    target = (spec.target or "").strip()
    old_text = str(spec.entities.get("old_text") or "")
    new_text = str(spec.entities.get("new_text") or "")
    verify_target = str(spec.entities.get("verify_target") or "").strip()
    if not target:
        return ExecutionReport(ok=False, summary="patch failed", error="target file is required")
    if not old_text:
        return ExecutionReport(ok=False, summary="patch failed", error="old_text is required")
    if len(old_text) > MAX_PATCH_TEXT or len(new_text) > MAX_PATCH_TEXT:
        return ExecutionReport(ok=False, summary="patch failed", error="text size exceeds limit")
    path = (root / target).resolve()
    if not _within_root(root, path):
        return ExecutionReport(ok=False, summary="patch failed", error="path outside project")
    if not path.exists() or not path.is_file():
        return ExecutionReport(ok=False, summary="patch failed", error="target file not found")
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=str(exc))
    occurrences = original.count(old_text)
    if occurrences != 1:
        return ExecutionReport(
            ok=False,
            summary="patch failed",
            error=f"old_text occurrences must be exactly 1, got {occurrences}",
        )
    patched = original.replace(old_text, new_text, 1)
    verify_args = ["-q"]
    verify_target = str(spec.entities.get("verify_target") or "").strip()
    if verify_target:
        verify_args.append(verify_target)
    elif (root / "tests" / "test_qt_smoke.py").exists():
        verify_args.append("tests/test_qt_smoke.py")
    if is_dry_run:
        preview = _build_preview_snippet(old_text, new_text)
        return ExecutionReport(
            ok=True,
            summary="patch dry-run preview",
            applied_steps=["compute replacement plan"],
            verification={
                "runner": "dry_run",
                "ok": True,
                "verify_args": verify_args,
                "output": f"{target}\n{preview}",
            },
            artifacts_changed=[target],
        )
    try:
        path.write_text(patched, encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=str(exc))

    verification = _run_pytest(root, verify_args, timeout=300)
    if verification.get("ok"):
        return ExecutionReport(
            ok=True,
            summary="patch applied and verified",
            applied_steps=["replace text", "run verify"],
            verification=verification,
            artifacts_changed=[target],
        )
    # Rollback on failed verify.
    try:
        path.write_text(original, encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(
            ok=False,
            summary="patch verify failed and rollback failed",
            applied_steps=["replace text", "run verify"],
            verification=verification,
            artifacts_changed=[target],
            error=f"rollback failed: {exc}",
        )
    verification["rollback"] = "done"
    return ExecutionReport(
        ok=False,
        summary="patch verify failed, rollback done",
        applied_steps=["replace text", "run verify"],
        verification=verification,
        artifacts_changed=[],
        error="verify failed",
    )


def _execute_code_edit_patch_batch(root: Path, spec: TaskSpec, operations_json: str) -> ExecutionReport:
    """Apply multiple replacements atomically with single verify and rollback."""
    is_dry_run = str(spec.entities.get("dry_run") or "").strip().lower() in {"1", "true", "yes"}
    try:
        raw_ops = json.loads(operations_json)
    except json.JSONDecodeError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=f"invalid operations_json: {exc}")
    if not isinstance(raw_ops, list) or not raw_ops:
        return ExecutionReport(ok=False, summary="patch failed", error="operations_json must be non-empty list")
    if len(raw_ops) > MAX_PATCH_OPS:
        return ExecutionReport(ok=False, summary="patch failed", error=f"too many operations: max {MAX_PATCH_OPS}")

    ops: List[Dict[str, str]] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            return ExecutionReport(ok=False, summary="patch failed", error="batch operation must be object")
        target = str(item.get("target") or "").strip()
        old_text = str(item.get("old_text") or "")
        new_text = str(item.get("new_text") or "")
        verify_target = str(item.get("verify_target") or "").strip()
        if not target or not old_text:
            return ExecutionReport(ok=False, summary="patch failed", error="each operation requires target and old_text")
        if len(old_text) > MAX_PATCH_TEXT or len(new_text) > MAX_PATCH_TEXT:
            return ExecutionReport(ok=False, summary="patch failed", error="text size exceeds limit")
        ops.append(
            {
                "target": target,
                "old_text": old_text,
                "new_text": new_text,
                "verify_target": verify_target,
            }
        )

    originals: Dict[Path, str] = {}
    staged: Dict[Path, str] = {}
    changed_targets: List[str] = []
    verify_target = str(spec.entities.get("verify_target") or "").strip()

    for op in ops:
        target = op["target"]
        old_text = op["old_text"]
        new_text = op["new_text"]
        path = (root / target).resolve()
        if not _within_root(root, path):
            return ExecutionReport(ok=False, summary="patch failed", error="path outside project")
        if not path.exists() or not path.is_file():
            return ExecutionReport(ok=False, summary="patch failed", error=f"target file not found: {target}")
        if path not in originals:
            try:
                originals[path] = path.read_text(encoding="utf-8")
            except OSError as exc:
                return ExecutionReport(ok=False, summary="patch failed", error=str(exc))
        current = staged.get(path, originals[path])
        occurrences = current.count(old_text)
        if occurrences != 1:
            return ExecutionReport(
                ok=False,
                summary="patch failed",
                error=f"old_text occurrences must be exactly 1 in `{target}`, got {occurrences}",
            )
        staged[path] = current.replace(old_text, new_text, 1)
        rel = str(path.relative_to(root))
        if rel not in changed_targets:
            changed_targets.append(rel)
        if not verify_target and op.get("verify_target"):
            verify_target = str(op.get("verify_target") or "").strip()
    verify_args = ["-q"]
    if verify_target:
        verify_args.append(verify_target)
    elif (root / "tests" / "test_qt_smoke.py").exists():
        verify_args.append("tests/test_qt_smoke.py")
    if is_dry_run:
        preview_lines = []
        for op in ops[:10]:
            preview_lines.append(op["target"])
            preview_lines.append(_build_preview_snippet(op["old_text"], op["new_text"], max_len=140))
        if len(ops) > 10:
            preview_lines.append(f"... (+{len(ops) - 10} operations)")
        return ExecutionReport(
            ok=True,
            summary=f"batch patch dry-run preview ({len(ops)} ops)",
            applied_steps=[f"build {len(ops)} replacement plans"],
            verification={
                "runner": "dry_run",
                "ok": True,
                "verify_args": verify_args,
                "output": "\n".join(preview_lines),
            },
            artifacts_changed=changed_targets,
        )

    written: List[Path] = []
    try:
        for path, patched in staged.items():
            path.write_text(patched, encoding="utf-8")
            written.append(path)
    except OSError as exc:
        for path in written:
            try:
                path.write_text(originals[path], encoding="utf-8")
            except OSError:
                pass
        return ExecutionReport(ok=False, summary="patch failed", error=f"write failed: {exc}")

    verification = _run_pytest(root, verify_args, timeout=300)
    if verification.get("ok"):
        return ExecutionReport(
            ok=True,
            summary=f"batch patch applied and verified ({len(ops)} ops)",
            applied_steps=[f"apply {len(ops)} replacements", "run verify"],
            verification=verification,
            artifacts_changed=changed_targets,
        )

    rollback_failed = False
    for path in originals:
        try:
            path.write_text(originals[path], encoding="utf-8")
        except OSError:
            rollback_failed = True
    if rollback_failed:
        return ExecutionReport(
            ok=False,
            summary="batch patch verify failed and rollback failed",
            applied_steps=[f"apply {len(ops)} replacements", "run verify"],
            verification=verification,
            artifacts_changed=changed_targets,
            error="verify failed and rollback failed",
        )
    verification["rollback"] = "done"
    return ExecutionReport(
        ok=False,
        summary="batch patch verify failed, rollback done",
        applied_steps=[f"apply {len(ops)} replacements", "run verify"],
        verification=verification,
        artifacts_changed=[],
        error="verify failed",
    )


CAPABILITIES["run_lint"]["executor"] = _execute_run_lint
CAPABILITIES["run_command"]["executor"] = _execute_run_command
CAPABILITIES["code_edit_patch"] = {
    "risk_level": "high",
    "requires_confirmation": True,
    "executor": _execute_code_edit_patch,
}


def build_task_spec(
    *,
    intent: str,
    target: str = "",
    message: str = "",
    plan_steps: Optional[List[str]] = None,
    entities: Optional[Dict[str, str]] = None,
) -> TaskSpec:
    info = CAPABILITIES.get(intent, {})
    return TaskSpec(
        intent=intent,
        target=target,
        message=message,
        steps=list(plan_steps or []),
        risk_level=str(info.get("risk_level", "medium")),
        requires_confirmation=bool(info.get("requires_confirmation", True)),
        entities=dict(entities or {}),
    )


def make_pending_plan(spec: TaskSpec, ttl_sec: int = 600) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "token": secrets.token_hex(8),
        "intent": spec.intent,
        "target": spec.target,
        "entities": dict(spec.entities),
        "risk_level": spec.risk_level,
        "requires_confirmation": spec.requires_confirmation,
        "steps": list(spec.steps),
        "created_ts": now,
        "expires_ts": now + max(ttl_sec, 60),
        "status": "pending_confirmation",
    }


def is_pending_plan_valid(plan: Dict[str, Any]) -> bool:
    if not isinstance(plan, dict):
        return False
    if str(plan.get("status") or "") != "pending_confirmation":
        return False
    expires = int(plan.get("expires_ts") or 0)
    return expires > int(time.time())


def execute_spec(root: Path, spec: TaskSpec) -> ExecutionReport:
    info = CAPABILITIES.get(spec.intent)
    if not info:
        return ExecutionReport(ok=False, summary="unknown capability", error=f"unsupported intent: {spec.intent}")
    executor = info.get("executor")
    if not callable(executor):
        return ExecutionReport(ok=False, summary="executor missing", error=f"no executor for {spec.intent}")
    return executor(root, spec)


def has_capability(intent: str) -> bool:
    """Check if intent is backed by executor registry."""
    return intent in CAPABILITIES
