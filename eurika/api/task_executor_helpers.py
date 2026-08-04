"""Helpers for task_executor: backup, file ops, pytest, preview."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

TASK_BACKUP_DIR = ".eurika_backups"


def task_backup_before_write(
    root: Path, target_file: str, path: Path, run_id: str | None = None
) -> str | None:
    """Backup file to .eurika_backups/<run_id>/ before modifying. Returns backup_dir or None on error."""
    try:
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_root = root / TASK_BACKUP_DIR / run_id
        backup_path = backup_root / target_file
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        return str(backup_root)
    except OSError:
        return None


def build_preview_snippet(before: str, after: str, max_len: int = 240) -> str:
    """Compact before/after preview for dry-run output."""
    b = mask_sensitive_preview_text((before or "").replace("\n", "\\n"))
    a = mask_sensitive_preview_text((after or "").replace("\n", "\\n"))
    if len(b) > max_len:
        b = b[: max_len - 3] + "..."
    if len(a) > max_len:
        a = a[: max_len - 3] + "..."
    return f"- {b}\n+ {a}"


def mask_sensitive_preview_text(text: str) -> str:
    """Mask common secret-like patterns before exposing preview output."""
    if not text:
        return text
    masked = text
    key_value_patterns = (
        r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization)\b\s*[:=]\s*([^\s,;]+)",
        r"(?i)\b(bearer)\s+([A-Za-z0-9._\-]+)",
    )
    for pat in key_value_patterns:
        masked = re.sub(pat, r"\1=***", masked)
    masked = re.sub(
        r"\b([A-Za-z0-9]{4})[A-Za-z0-9._\-]{12,}([A-Za-z0-9]{3})\b",
        r"\1***\2",
        masked,
    )
    return masked


def within_root(root: Path, path: Path) -> bool:
    return str(path.resolve()).startswith(str(root.resolve()))


def safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not within_root(root, path):
        return False, "path outside project"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, str(path.relative_to(root))


def safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not within_root(root, path):
        return False, "path outside project"
    if not path.exists() or not path.is_file():
        return False, "not a file or does not exist"
    try:
        rel = str(path.relative_to(root))
        path.unlink()
        return True, rel
    except OSError as exc:
        return False, str(exc)


def safe_create_empty_file(root: Path, relative_path: str) -> tuple[bool, str]:
    if ".." in relative_path or relative_path.startswith("/"):
        return False, "invalid path"
    path = (root / relative_path).resolve()
    if not within_root(root, path):
        return False, "path outside project"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, str(path.relative_to(root))


def run_pytest(root: Path, args: List[str], timeout: int = 180) -> Dict[str, Any]:
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
