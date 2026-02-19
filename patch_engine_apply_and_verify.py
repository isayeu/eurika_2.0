"""Extracted from parent module to reduce complexity."""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from patch_engine_apply_patch import apply_patch
from patch_engine_rollback_patch import rollback_patch
from patch_engine_verify_patch import verify_patch


def _verify_py_compile(project_root: Path, modified: List[str], timeout: int = 60) -> Dict[str, Any]:
    """Run py_compile on modified .py files. Returns same shape as verify_patch."""
    root = Path(project_root).resolve()
    py_files = [str(root / p) for p in modified if p.endswith(".py")]
    if not py_files:
        return {"success": True, "returncode": 0, "stdout": "no .py files to compile", "stderr": ""}
    cmd = [sys.executable, "-m", "py_compile"] + py_files
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-3000:],
        "stderr": (proc.stderr or "")[-3000:],
    }


def apply_and_verify(project_root: Path, plan: Dict[str, Any], *, backup: bool=True, verify: bool=True, verify_timeout: int=120, verify_cmd: Optional[str]=None, auto_rollback: bool=True, retry_on_import_error: bool=True) -> Dict[str, Any]:
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
        report.setdefault('verify', {'success': None, 'returncode': None, 'stdout': '', 'stderr': ''})
        return report
    report['verify'] = verify_patch(root, timeout=verify_timeout, verify_cmd=verify_cmd)
    if not report['verify']['success'] and retry_on_import_error and report.get('run_id'):
        from eurika.refactor.fix_import_from_verify import parse_verify_import_error, suggest_fix_import_operations
        v = report['verify']
        parsed = parse_verify_import_error(v.get('stdout', ''), v.get('stderr', ''))
        if parsed:
            fix_ops = suggest_fix_import_operations(root, parsed)
            if fix_ops:
                fix_plan = {'operations': fix_ops}
                fix_report = apply_patch(root, fix_plan, backup=False)
                report['modified'] = report.get('modified', []) + fix_report.get('modified', [])
                report['fix_import_retry'] = {'applied': fix_report.get('modified', [])}
                report['verify'] = verify_patch(root, timeout=verify_timeout, verify_cmd=verify_cmd)
    # Fallback: pytest returncode 5 (no tests collected) → py_compile on modified files
    v = report['verify']
    if (
        not v['success']
        and verify_cmd is None
        and v.get('returncode') == 5
        and 'no tests' in (v.get('stdout', '') + v.get('stderr', '')).lower()
        and report.get('modified')
    ):
        py_compile_result = _verify_py_compile(root, report['modified'], timeout=min(verify_timeout, 60))
        py_compile_result['py_compile_fallback'] = True
        if py_compile_result['success']:
            report['verify'] = py_compile_result
    if not report['verify']['success'] and auto_rollback and report.get('run_id'):
        rb = rollback_patch(root, report['run_id'])
        report['rollback'] = {'done': True, 'run_id': report['run_id'], 'restored': rb.get('restored', []), 'errors': rb.get('errors', [])}
    elif not report['verify']['success'] and auto_rollback and (not report.get('run_id')):
        report['rollback'] = {'done': False, 'reason': 'no run_id (no backup)'}
    return report


# TODO (eurika): refactor long_function 'apply_and_verify' — consider extracting helper
