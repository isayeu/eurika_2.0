"""Extracted from parent module to reduce complexity."""
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_verify_timeout(project_root: Path, override: Optional[int] = None) -> int:
    """Resolve verify timeout: override > EURIKA_VERIFY_TIMEOUT > pyproject [tool.eurika] verify_timeout > 300."""
    if override is not None and override > 0:
        return int(override)
    env_val = os.environ.get("EURIKA_VERIFY_TIMEOUT")
    if env_val is not None:
        try:
            return max(1, int(env_val.strip()))
        except ValueError:
            pass
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r"verify_timeout\s*=\s*(\d+)", text)
            if m:
                return max(1, int(m.group(1)))
        except (OSError, UnicodeDecodeError):
            pass
    return 300


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


def _expand_py_compile_args(cmd: List[str], project_root: Path) -> List[str]:
    """If cmd is 'python -m py_compile' with no .py args, add all project .py files."""
    if len(cmd) < 2 or "py_compile" not in cmd:
        return cmd
    if any(arg.endswith(".py") for arg in cmd):
        return cmd
    exclude = {".venv", "venv", "__pycache__", ".eurika_backups"}
    py_files = [
        str(p) for p in project_root.rglob("*.py")
        if not any(x in p.parts for x in exclude)
    ]
    return cmd + py_files if py_files else cmd


def verify_patch(
    project_root: Path,
    *,
    timeout: int = 120,
    verify_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run verify command in project_root (default: pytest -q).
    verify_cmd overrides [tool.eurika] verify_cmd in pyproject.toml.
    For 'python -m py_compile' with no args, all project .py files are passed automatically.

    Returns:
        {"success": bool, "returncode": int, "stdout": str, "stderr": str}
    """
    root = Path(project_root).resolve()
    cmd = _get_verify_cmd(root, override=verify_cmd)
    cmd = _expand_py_compile_args(cmd, root)
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
        msg = f"verify command timed out after {timeout}s"
        if stderr:
            stderr = f"{stderr}\n{msg}"
        else:
            stderr = msg
        return {
            "success": False,
            "returncode": -1,
            "stdout": stdout[-3000:],
            "stderr": stderr[-3000:],
        }
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-3000:],
        "stderr": (proc.stderr or "")[-3000:],
    }
