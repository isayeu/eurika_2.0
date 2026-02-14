"""
Patch Engine (ROADMAP 2.1 / review.md).

Single facade for: apply plan → verify (pytest) → rollback.
Plan is built elsewhere (arch-review → suggest_patch_plan); this module
only applies, verifies, and restores.

Usage:
    from patch_engine import apply_and_verify, rollback, list_backups
    report = apply_and_verify(project_root, patch_plan, backup=True, verify=True)
    if not report["verify"]["success"]:
        rollback(project_root, report.get("run_id"))
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from patch_apply import (
    BACKUP_DIR,
    apply_patch_plan,
    list_backups as _list_backups,
    restore_backup,
)


def apply_and_verify(
    project_root: Path,
    plan: Dict[str, Any],
    *,
    backup: bool = True,
    verify: bool = True,
    verify_timeout: int = 120,
) -> Dict[str, Any]:
    """
    Apply a patch plan and optionally run pytest for verification.

    Args:
        project_root: Project directory.
        plan: Patch plan dict (e.g. from suggest_patch_plan arguments).
        backup: If True, copy files to .eurika_backups/<run_id>/ before modifying.
        verify: If True, run `python -m pytest -q` in project_root after apply.
        verify_timeout: Timeout in seconds for the verify step.

    Returns:
        Report dict with keys: dry_run, modified, skipped, errors, backup_dir,
        run_id; and if verify=True: verify (success, returncode, stdout, stderr).
    """
    root = Path(project_root).resolve()
    report = apply_patch_plan(root, plan, dry_run=False, backup=backup)

    if not verify:
        report.setdefault("verify", {"success": None, "returncode": None, "stdout": "", "stderr": ""})
        return report

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=verify_timeout,
    )
    report["verify"] = {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-3000:],
        "stderr": (proc.stderr or "")[-3000:],
    }
    return report


def rollback(project_root: Path, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Restore files from .eurika_backups to project root.

    If run_id is None, restores from the latest backup run.

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    return restore_backup(Path(project_root).resolve(), run_id=run_id)


def list_backups(project_root: Path) -> Dict[str, Any]:
    """List available backup run_ids in .eurika_backups/."""
    return _list_backups(Path(project_root).resolve())
