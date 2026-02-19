"""Extracted from parent module to reduce complexity."""
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-3000:],
        "stderr": (proc.stderr or "")[-3000:],
    }
