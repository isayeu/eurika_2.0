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
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from patch_apply import apply_patch_plan, list_backups as _list_backups, restore_backup


def _get_verify_cmd(project_root: Path, override: Optional[str] = None) -> List[str]:
    """Resolve verify command: override > pyproject.toml [tool.eurika] verify_cmd > default pytest."""
    if override is not None and override.strip():
        return shlex.split(override.strip())
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r'verify_cmd\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                return shlex.split(m.group(1).strip())
        except (OSError, UnicodeDecodeError):
            pass
    return [sys.executable, "-m", "pytest", "-q"]


def apply_patch(
    project_root: Path,
    plan: Dict[str, Any],
    *,
    backup: bool = True,
) -> Dict[str, Any]:
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


def verify_patch(
    project_root: Path,
    *,
    timeout: int = 120,
    verify_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run verify command in project_root (default: pytest -q).
    verify_cmd overrides [tool.eurika] verify_cmd in pyproject.toml.

    Returns:
        {"success": bool, "returncode": int, "stdout": str, "stderr": str}
    """
    root = Path(project_root).resolve()
    cmd = _get_verify_cmd(root, override=verify_cmd)
    proc = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-3000:],
        "stderr": (proc.stderr or "")[-3000:],
    }


def rollback_patch(
    project_root: Path,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Restore files from .eurika_backups to project root.
    If run_id is None, restores from the latest backup run.

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    return restore_backup(Path(project_root).resolve(), run_id=run_id)


# Alias for backward compatibility and ROADMAP naming
def rollback(project_root: Path, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Alias for rollback_patch."""
    return rollback_patch(project_root, run_id)


def apply_and_verify(
    project_root: Path,
    plan: Dict[str, Any],
    *,
    backup: bool = True,
    verify: bool = True,
    verify_timeout: int = 120,
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
        return report
    report["verify"] = verify_patch(root, timeout=verify_timeout, verify_cmd=verify_cmd)

    # Retry on import error: parse verify output, apply fix, re-verify once
    if (
        not report["verify"]["success"]
        and retry_on_import_error
        and report.get("run_id")
    ):
        from eurika.refactor.fix_import_from_verify import (
            parse_verify_import_error,
            suggest_fix_import_operations,
        )
        v = report["verify"]
        parsed = parse_verify_import_error(v.get("stdout", ""), v.get("stderr", ""))
        if parsed:
            fix_ops = suggest_fix_import_operations(root, parsed)
            if fix_ops:
                fix_plan = {"operations": fix_ops}
                fix_report = apply_patch(root, fix_plan, backup=False)
                report["modified"] = report.get("modified", []) + fix_report.get("modified", [])
                report["fix_import_retry"] = {"applied": fix_report.get("modified", [])}
                report["verify"] = verify_patch(root, timeout=verify_timeout, verify_cmd=verify_cmd)

    if not report["verify"]["success"] and auto_rollback and report.get("run_id"):
        rb = rollback_patch(root, report["run_id"])
        report["rollback"] = {
            "done": True,
            "run_id": report["run_id"],
            "restored": rb.get("restored", []),
            "errors": rb.get("errors", []),
        }
    elif not report["verify"]["success"] and auto_rollback and not report.get("run_id"):
        report["rollback"] = {"done": False, "reason": "no run_id (no backup)"}
    return report


def list_backups(project_root: Path) -> Dict[str, Any]:
    """List available backup run_ids in .eurika_backups/."""
    return _list_backups(Path(project_root).resolve())

# TODO: Refactor patch_engine.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: patch_apply.py.
# - Consider grouping callers: cli/agent_handlers.py, cli/orchestrator.py, tests/test_cycle.py.
# - Introduce facade for callers: cli/agent_handlers.py, cli/orchestrator.py, tests/test_cycle.py....
