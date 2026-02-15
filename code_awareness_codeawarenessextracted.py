"""Extracted from parent class to reduce complexity."""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

class CodeAwarenessExtracted:
    """Extracted methods (static)."""

    @staticmethod
    def read_file(path: Path):
        """Read file contents. Read-only."""
        return path.read_text(encoding='utf-8')

    @staticmethod
    def _import_to_dicts(node: ast.Import):
        """Convert ast.Import node to list of dicts."""
        return [{'module': alias.name, 'alias': alias.asname} for alias in node.names]

    @staticmethod
    def _importfrom_to_dicts(node: ast.ImportFrom):
        """Convert ast.ImportFrom node to list of dicts."""
        module = node.module or ''
        return [{'module': module, 'name': alias.name, 'alias': alias.asname} for alias in node.names]

    @staticmethod
    def _function_lines(node: ast.FunctionDef, source_lines: List[str]):
        """Count logical lines of function body."""
        if not node.end_lineno or not node.lineno:
            return 0
        return node.end_lineno - node.lineno + 1

    @staticmethod
    def _normalize_body(text: str):
        """Normalize code for duplicate comparison."""
        return ' '.join((line.strip() for line in text.splitlines() if line.strip()))
