"""
Execution — alias над patch_engine (TARGET_V3_STRUCTURE §4, R6).

Re-exports apply, verify, rollback, simulate. Не перемещаем patch_engine.
Импорт: from eurika.execution import apply_and_verify, simulate_patch
"""

from __future__ import annotations

from patch_engine import (
    BACKUP_DIR,
    apply_and_verify,
    apply_patch,
    apply_patch_dry_run,
    list_backups,
    rollback,
    rollback_patch,
    simulate_patch,
    verify_patch,
)

__all__ = [
    "BACKUP_DIR",
    "apply_and_verify",
    "apply_patch",
    "apply_patch_dry_run",
    "list_backups",
    "rollback",
    "rollback_patch",
    "simulate_patch",
    "verify_patch",
]
