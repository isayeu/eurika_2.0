"""Backup and file-write helpers for patch_apply."""

from __future__ import annotations

from pathlib import Path
from typing import Any

BACKUP_DIR = ".eurika_backups"


def backup_file(
    root: Path,
    path: Path,
    target_file: str,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
) -> str | None:
    """Copy path to .eurika_backups/run_id/target_file if do_backup. Returns backup_dir."""
    if not do_backup:
        return backup_dir
    backup_root = root / BACKUP_DIR / run_id
    backup_path = backup_root / target_file
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup_root) if backup_dir is None else backup_dir


def write_single_file_change(
    root: Path,
    path: Path,
    target_file: str,
    new_content: str,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
) -> tuple[str | None, bool]:
    """
    Backup and write content to an existing file.

    Returns (backup_dir, changed).
    """
    backup_dir = backup_file(root, path, target_file, run_id, backup_dir, do_backup)
    path.write_text(new_content, encoding="utf-8")
    return backup_dir, True


def write_extracted_and_original(
    root: Path,
    path: Path,
    target_file: str,
    new_rel_path: str,
    new_content: str,
    modified_original: str,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
    exists_reason: str,
    skip_cb,
) -> tuple[str | None, bool]:
    """
    Write extracted module and modified original with backup.

    Returns (backup_dir, changed). If extracted file exists, returns (backup_dir, False).
    """
    new_path = root / new_rel_path
    if new_path.exists():
        skip_cb(exists_reason)
        return backup_dir, False
    backup_dir = backup_file(root, path, target_file, run_id, backup_dir, do_backup)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(new_content, encoding="utf-8")
    path.write_text(modified_original, encoding="utf-8")
    return backup_dir, True


def list_backups(project_root: Path) -> dict[str, Any]:
    """
    List available backup run_ids in .eurika_backups/.

    Returns:
        {"run_ids": [str], "backup_dir": str}
    """
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    if not backup_root.is_dir():
        return {"run_ids": [], "backup_dir": str(backup_root)}
    run_ids = sorted(path.name for path in backup_root.iterdir() if path.is_dir())
    return {"run_ids": run_ids, "backup_dir": str(backup_root)}


def restore_backup(project_root: Path, run_id: str | None = None) -> dict[str, Any]:
    """
    Restore files from .eurika_backups/<run_id>/ to project root.
    If run_id is None, restores from the latest run (most recent by name).

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    restored: list[str] = []
    errors: list[str] = []

    if not backup_root.is_dir():
        errors.append(f"Backup dir not found: {backup_root}")
        return {"restored": [], "errors": errors, "run_id": None}

    if run_id is None:
        run_ids = sorted(path.name for path in backup_root.iterdir() if path.is_dir())
        if not run_ids:
            errors.append("No backup runs found")
            return {"restored": [], "errors": errors, "run_id": None}
        run_id = run_ids[-1]

    run_path = backup_root / run_id
    if not run_path.is_dir():
        errors.append(f"Run not found: {run_id}")
        return {"restored": [], "errors": errors, "run_id": run_id}

    for backup_file_path in run_path.rglob("*"):
        if not backup_file_path.is_file():
            continue
        rel = backup_file_path.relative_to(run_path)
        target = root / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(backup_file_path.read_text(encoding="utf-8"), encoding="utf-8")
            restored.append(str(rel))
        except Exception as exc:  # pragma: no cover - defensive I/O path
            errors.append(f"{rel}: {exc}")

    return {"restored": restored, "errors": errors, "run_id": run_id}
