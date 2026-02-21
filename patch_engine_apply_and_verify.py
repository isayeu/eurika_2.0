"""Extracted from parent module to reduce complexity."""

import time
from pathlib import Path
from typing import Any, Dict, Optional

from patch_engine_apply_patch import apply_patch
from patch_engine_apply_and_verify_helpers import (
    maybe_apply_py_compile_fallback,
    maybe_auto_rollback,
    maybe_retry_import_fix,
)
from patch_engine_rollback_patch import rollback_patch
from patch_engine_verify_patch import verify_patch


def _run_verify_with_fallbacks(
    root: Path,
    report: Dict[str, Any],
    *,
    verify_timeout: int,
    verify_cmd: Optional[str],
    retry_on_import_error: bool,
    auto_rollback: bool,
) -> None:
    """Run verify, optional retry/compile fallback, and auto_rollback. Mutates report."""
    verify_started = time.perf_counter()
    report["verify"] = verify_patch(root, timeout=verify_timeout, verify_cmd=verify_cmd)
    maybe_retry_import_fix(
        root=root,
        report=report,
        verify_timeout=verify_timeout,
        verify_cmd=verify_cmd,
        retry_on_import_error=retry_on_import_error,
        apply_patch_fn=apply_patch,
        verify_patch_fn=verify_patch,
    )
    maybe_apply_py_compile_fallback(
        root=root,
        report=report,
        verify_timeout=verify_timeout,
        verify_cmd=verify_cmd,
    )
    report["verify_duration_ms"] = int((time.perf_counter() - verify_started) * 1000)
    maybe_auto_rollback(
        root=root,
        report=report,
        auto_rollback=auto_rollback,
        rollback_patch_fn=rollback_patch,
    )


def apply_and_verify(
    project_root: Path,
    plan: Dict[str, Any],
    *,
    backup: bool = True,
    verify: bool = True,
    verify_timeout: int = 300,
    verify_cmd: Optional[str] = None,
    auto_rollback: bool = True,
    retry_on_import_error: bool = True,
) -> Dict[str, Any]:
    """
    Apply a patch plan and optionally run verify command. On verify failure, optionally
    try to fix import errors (create missing stub or redirect import) and retry verify.

    Args:
        project_root: Project directory.
        plan: Patch plan dict.
        backup: If True, copy files to .eurika_backups/<run_id>/ before modifying.
        verify: If True, run verify command after apply.
        verify_timeout: Timeout in seconds for the verify step.
        verify_cmd: Override for verify command (e.g. "python manage.py test"); else use pyproject or pytest.
        auto_rollback: If True and verify fails (after retry if any), restore from backup (last run_id).
        retry_on_import_error: If True and verify fails with ModuleNotFoundError/ImportError, try fix and re-verify once.

    Returns:
        Report with keys: dry_run, modified, skipped, errors, backup_dir, run_id;
        if verify=True: verify (success, returncode, stdout, stderr);
        if auto_rollback was triggered: rollback (done, run_id, restored?, errors?).
    """
    root = Path(project_root).resolve()
    report = apply_patch(root, plan, backup=backup)
    if not verify:
        report.setdefault("verify", {"success": None, "returncode": None, "stdout": "", "stderr": ""})
        report["verify_duration_ms"] = 0
        return report
    _run_verify_with_fallbacks(
        root=root,
        report=report,
        verify_timeout=verify_timeout,
        verify_cmd=verify_cmd,
        retry_on_import_error=retry_on_import_error,
        auto_rollback=auto_rollback,
    )
    return report

# TODO: Refactor patch_engine_apply_and_verify.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - OSS (django): django/template/backends/django.py — Consider splitting into smaller modules; extract coherent sub-responsibilities.
# - Extract from imports: patch_engine_apply_patch.py, patch_engine_apply_and_verify_helpers.py, patch_engine_rollback_patch.py.
# - Consider grouping callers: patch_engine.py.
# - Extract patch application logic into `patch_engine_apply_logic.py`
# - Separate rollback functionality into `patch_engine_rollback_logic.py`
# - Consolidate verification procedures into `patch_engine_verification_utils.py`
