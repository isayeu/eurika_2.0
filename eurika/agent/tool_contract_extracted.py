"""Extracted from parent module to reduce complexity."""

import subprocess
from pathlib import Path
from typing import Any, Protocol, Optional
from .models import ToolResult

class ToolContract(Protocol):
    """Protocol for tool adapters. Each method returns ToolResult."""

    def scan(self, path: Path, **kwargs: Any) -> ToolResult:
        """Scan project; update artifacts; return exit_code in payload."""
        ...

    def patch(self, path: Path, plan: dict[str, Any], *, dry_run: bool=True, backup: bool=True, **kwargs: Any) -> ToolResult:
        """Apply patch plan; dry_run=True reports without modifying files."""
        ...

    def verify(self, path: Path, *, timeout: int=120, verify_cmd: Optional[str]=None, **kwargs: Any) -> ToolResult:
        """Run verify command (default pytest). Returns success, returncode, stdout, stderr."""
        ...

    def rollback(self, path: Path, run_id: Optional[str]=None, **kwargs: Any) -> ToolResult:
        """Restore from .eurika_backups. run_id=None uses latest."""
        ...

    def tests(self, path: Path, *, timeout: int=120, verify_cmd: Optional[str]=None, **kwargs: Any) -> ToolResult:
        """Alias for verify: run pytest or custom verify command."""
        ...

    def git_read(self, path: Path, **kwargs: Any) -> ToolResult:
        """Read git state: commit hash, status summary."""
        ...

def _ok(payload: Any) -> ToolResult:
    return ToolResult(status='ok', payload=payload)

def _err(msg: str) -> ToolResult:
    return ToolResult(status='error', message=msg, payload=None)

class DefaultToolContract:
    """Concrete implementation wrapping patch_engine, runtime_scan, etc."""

    def scan(self, path: Path, **kwargs: Any) -> ToolResult:
        try:
            from runtime_scan import run_scan
            code = run_scan(path, **{k: v for k, v in kwargs.items() if k in ('format', 'color')})
            return _ok({'exit_code': code})
        except Exception as exc:
            return _err(str(exc))

    def patch(self, path: Path, plan: dict[str, Any], *, dry_run: bool=True, backup: bool=True, **kwargs: Any) -> ToolResult:
        try:
            if dry_run:
                from patch_engine import apply_patch_dry_run
                report = apply_patch_dry_run(path, plan, backup=backup)
            else:
                from patch_engine_apply_patch import apply_patch
                report = apply_patch(path, plan, backup=backup)
            if report.get('errors'):
                return ToolResult(status='error', message='; '.join(report['errors']), payload=report)
            return _ok(report)
        except Exception as exc:
            return _err(str(exc))

    def verify(self, path: Path, *, timeout: int=120, verify_cmd: Optional[str]=None, **kwargs: Any) -> ToolResult:
        try:
            from patch_engine_verify_patch import verify_patch
            result = verify_patch(path, timeout=timeout, verify_cmd=verify_cmd)
            return _ok(result)
        except Exception as exc:
            return _err(str(exc))

    def rollback(self, path: Path, run_id: Optional[str]=None, **kwargs: Any) -> ToolResult:
        try:
            from patch_engine_rollback_patch import rollback_patch
            result = rollback_patch(path, run_id=run_id)
            return _ok(result)
        except Exception as exc:
            return _err(str(exc))

    def tests(self, path: Path, *, timeout: int=120, verify_cmd: Optional[str]=None, **kwargs: Any) -> ToolResult:
        return self.verify(path, timeout=timeout, verify_cmd=verify_cmd, **kwargs)

    def git_read(self, path: Path, **kwargs: Any) -> ToolResult:
        try:
            root = Path(path).resolve()
            if not (root / '.git').exists():
                return _ok({'commit': None, 'status': 'not_a_repo'})
            r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, timeout=5)
            commit = r.stdout.strip()[:12] if r.returncode == 0 and r.stdout else None
            return _ok({'commit': commit})
        except Exception as exc:
            return _err(str(exc))
