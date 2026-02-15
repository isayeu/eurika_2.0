"""Facade for code_awareness — stable API boundary.

Callers (candidates to switch): runtime_scan.py, cli/core_handlers.py, eurika/analysis/scanner.py, runtime_scan_run_scan.py, tests/test_runtime_scan.py."""

from code_awareness import FileInfo, Smell, CodeAwareness

__all__ = ['FileInfo', 'Smell', 'CodeAwareness']
