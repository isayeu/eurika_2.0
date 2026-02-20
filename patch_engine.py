"""
Patch Engine (ROADMAP 2.1 / review.md).

Facade: apply_patch(plan), verify_patch(), rollback_patch().
Plan is built elsewhere (arch-review → suggest_patch_plan); this module
applies, verifies (pytest or custom command), and restores. Optional auto_rollback on verify failure.

Usage:
    from patch_engine import apply_patch, verify_patch, rollback_patch, apply_and_verify
    report = apply_patch(project_root, plan, backup=True)
    v = verify_patch(project_root)
    if not v["success"]:
        rollback_patch(project_root, report.get("run_id"))
    # Or in one call:
    report = apply_and_verify(project_root, plan, backup=True, verify=True, auto_rollback=True)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from patch_engine_apply_patch import apply_patch
from patch_engine_apply_and_verify import apply_and_verify
from patch_engine_rollback_patch import rollback_patch
from patch_engine_verify_patch import verify_patch
from patch_apply import BACKUP_DIR
from patch_apply import apply_patch_plan as _apply_patch_plan
from patch_apply import list_backups as _list_backups


def rollback(project_root: Path, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Alias for rollback_patch."""
    return rollback_patch(project_root, run_id)

def list_backups(project_root: Path) -> Dict[str, Any]:
    """List available backup run_ids in .eurika_backups/."""
    return _list_backups(Path(project_root).resolve())


def apply_patch_dry_run(project_root: Path, plan: Dict[str, Any], *, backup: bool = True) -> Dict[str, Any]:
    """Dry-run patch apply via patch_engine facade (compat wrapper)."""
    root = Path(project_root).resolve()
    return _apply_patch_plan(root, plan, dry_run=True, backup=backup)