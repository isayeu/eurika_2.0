"""Extracted from parent module to reduce complexity."""
from pathlib import Path
from typing import Any, Dict, Optional
from patch_apply import restore_backup

def rollback_patch(project_root: Path, run_id: Optional[str]=None) -> Dict[str, Any]:
    """
    Restore files from .eurika_backups to project root.
    If run_id is None, restores from the latest backup run.

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    return restore_backup(Path(project_root).resolve(), run_id=run_id)