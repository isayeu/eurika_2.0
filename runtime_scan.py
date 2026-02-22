"""
Eurika Runtime Scan v0.1

Core orchestration for `eurika scan`.
CLI (`eurika_cli.py`) is only responsible for argument parsing and exit codes.
"""

from __future__ import annotations

from runtime_scan_run_scan import run_scan

__all__ = ["run_scan"]
