"""Extracted from parent module to reduce complexity."""
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

def verify_patch(project_root: Path, *, timeout: int=120) -> Dict[str, Any]:
    """
    Run pytest in project_root to verify the current state (e.g. after apply_patch).

    Returns:
        {"success": bool, "returncode": int, "stdout": str, "stderr": str}
    """
    root = Path(project_root).resolve()
    proc = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=root, capture_output=True, text=True, timeout=timeout)
    return {'success': proc.returncode == 0, 'returncode': proc.returncode, 'stdout': (proc.stdout or '')[-3000:], 'stderr': (proc.stderr or '')[-3000:]}