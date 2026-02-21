"""Extracted from parent module to reduce complexity."""

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
