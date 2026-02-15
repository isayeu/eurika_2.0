"""Extracted from parent module to reduce complexity."""

from pathlib import Path
from typing import Any, Dict, List

def list_backups(project_root: Path) -> Dict[str, Any]:
    """
    List available backup run_ids in .eurika_backups/.

    Returns:
        {"run_ids": [str], "backup_dir": str}
    """
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    if not backup_root.is_dir():
        return {'run_ids': [], 'backup_dir': str(backup_root)}
    run_ids = sorted((p.name for p in backup_root.iterdir() if p.is_dir()))
    return {'run_ids': run_ids, 'backup_dir': str(backup_root)}

def restore_backup(project_root: Path, run_id: str | None=None) -> Dict[str, Any]:
    """
    Restore files from .eurika_backups/<run_id>/ to project root.
    If run_id is None, restores from the latest run (most recent by name).

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    restored: List[str] = []
    errors: List[str] = []
    if not backup_root.is_dir():
        errors.append(f'Backup dir not found: {backup_root}')
        return {'restored': [], 'errors': errors, 'run_id': None}
    if run_id is None:
        run_ids = sorted((p.name for p in backup_root.iterdir() if p.is_dir()))
        if not run_ids:
            errors.append('No backup runs found')
            return {'restored': [], 'errors': errors, 'run_id': None}
        run_id = run_ids[-1]
    run_path = backup_root / run_id
    if not run_path.is_dir():
        errors.append(f'Run not found: {run_id}')
        return {'restored': [], 'errors': errors, 'run_id': run_id}
    for backup_file in run_path.rglob('*'):
        if not backup_file.is_file():
            continue
        rel = backup_file.relative_to(run_path)
        target = root / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(backup_file.read_text(encoding='utf-8'), encoding='utf-8')
            restored.append(str(rel))
        except Exception as e:
            errors.append(f'{rel}: {e}')
    return {'restored': restored, 'errors': errors, 'run_id': run_id}
