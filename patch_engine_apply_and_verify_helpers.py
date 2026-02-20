"""Helper flow functions for patch_engine_apply_and_verify."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def verify_py_compile(project_root: Path, modified: List[str], timeout: int = 60) -> Dict[str, Any]:
    """Run py_compile on modified .py files. Returns same shape as verify_patch."""
    root = Path(project_root).resolve()
    py_files = [str(root / path) for path in modified if path.endswith(".py")]
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


def maybe_retry_import_fix(
    *,
    root: Path,
    report: Dict[str, Any],
    verify_timeout: int,
    verify_cmd: Optional[str],
    retry_on_import_error: bool,
    apply_patch_fn: Callable[..., Dict[str, Any]],
    verify_patch_fn: Callable[..., Dict[str, Any]],
) -> None:
    """Try auto-fix for import errors and re-run verify once."""
    if report["verify"]["success"] or not retry_on_import_error or not report.get("run_id"):
        return
    from eurika.refactor.fix_import_from_verify import (
        parse_verify_import_error,
        suggest_fix_import_operations,
    )

    verify_data = report["verify"]
    parsed = parse_verify_import_error(verify_data.get("stdout", ""), verify_data.get("stderr", ""))
    if not parsed:
        return
    fix_ops = suggest_fix_import_operations(root, parsed)
    if not fix_ops:
        return
    fix_plan = {"operations": fix_ops}
    fix_report = apply_patch_fn(root, fix_plan, backup=False)
    report["modified"] = report.get("modified", []) + fix_report.get("modified", [])
    report["fix_import_retry"] = {"applied": fix_report.get("modified", [])}
    report["verify"] = verify_patch_fn(root, timeout=verify_timeout, verify_cmd=verify_cmd)


def maybe_apply_py_compile_fallback(
    *,
    root: Path,
    report: Dict[str, Any],
    verify_timeout: int,
    verify_cmd: Optional[str],
) -> None:
    """Fallback to py_compile when pytest reports no tests collected."""
    verify_data = report["verify"]
    if (
        verify_data["success"]
        or verify_cmd is not None
        or verify_data.get("returncode") != 5
        or "no tests" not in (verify_data.get("stdout", "") + verify_data.get("stderr", "")).lower()
        or not report.get("modified")
    ):
        return
    py_compile_result = verify_py_compile(
        root, report["modified"], timeout=min(verify_timeout, 60)
    )
    py_compile_result["py_compile_fallback"] = True
    if py_compile_result["success"]:
        report["verify"] = py_compile_result


def maybe_auto_rollback(
    *,
    root: Path,
    report: Dict[str, Any],
    auto_rollback: bool,
    rollback_patch_fn: Callable[..., Dict[str, Any]],
) -> None:
    """Attach rollback report when verify failed and rollback is enabled."""
    if report["verify"]["success"] or not auto_rollback:
        return
    if report.get("run_id"):
        rollback_report = rollback_patch_fn(root, report["run_id"])
        report["rollback"] = {
            "done": True,
            "run_id": report["run_id"],
            "restored": rollback_report.get("restored", []),
            "errors": rollback_report.get("errors", []),
            "trigger": "verify_failed",
        }
        return
    report["rollback"] = {
        "done": False,
        "reason": "no run_id (no backup)",
        "trigger": "verify_failed",
    }
