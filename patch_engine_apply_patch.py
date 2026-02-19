"""Extracted from parent module to reduce complexity."""
from pathlib import Path
from typing import Any, Dict
from patch_apply import apply_patch_plan

def apply_patch(project_root: Path, plan: Dict[str, Any], *, backup: bool=True) -> Dict[str, Any]:
    """
    Apply a patch plan. Does not run verification.

    Args:
        project_root: Project directory.
        plan: Patch plan dict (e.g. from suggest_patch_plan).
        backup: If True, copy files to .eurika_backups/<run_id>/ before modifying.

    Returns:
        Report with keys: dry_run, modified, skipped, errors, backup_dir, run_id.
    """
    root = Path(project_root).resolve()
    return apply_patch_plan(root, plan, dry_run=False, backup=backup)