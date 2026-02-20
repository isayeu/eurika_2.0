"""Typed orchestration models for fix-cycle flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class FixCycleContext:
    """Runtime context for fix-cycle execution parameters."""

    path: Path
    runtime_mode: str = "assist"
    non_interactive: bool = False
    session_id: str | None = None
    window: int = 5
    dry_run: bool = False
    quiet: bool = False
    skip_scan: bool = False
    no_clean_imports: bool = False
    no_code_smells: bool = False
    verify_cmd: str | None = None
