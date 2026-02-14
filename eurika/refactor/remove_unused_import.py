"""
Remove unused imports from Python file (AST-based).

Used for Remove Dead Code / Killer-feature: detects imports that are never
referenced in the file and removes them.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Set


def remove_unused_imports(file_path: Path) -> Optional[str]:
    """
    Remove all unused imports from a Python file.

    An import is considered unused if the bound name is never referenced
    in a load context (read, not assigned). Handles:
    - `import foo`, `import foo as f`
    - `from foo import a, b`
    Skips: `from x import *`, `from __future__ import ...`

    Returns:
        New file content with unused imports removed, or None on error.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    used = _collect_used_names(tree)
    remover = _UnusedImportRemover(used)
    remover.visit(tree)
    if not remover.removed:
        return None
    return ast.unparse(tree)


def _collect_used_names(tree: ast.AST) -> Set[str]:
    """Collect all names used in load context (and root of attributes)."""
    used: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            root = _root_name(node.value)
            if root:
                used.add(root)
    return used


def _root_name(node: ast.AST) -> Optional[str]:
    """Get root identifier from expr (e.g. foo.bar.baz -> foo)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return None


class _UnusedImportRemover(ast.NodeTransformer):
    """AST transformer that removes unused imports."""

    def __init__(self, used_names: Set[str]) -> None:
        self.used_names = used_names
        self.removed = False

    def visit_Import(self, node: ast.Import) -> Optional[ast.AST]:
        new_names = []
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            if bound in self.used_names:
                new_names.append(alias)
            else:
                self.removed = True
        if not new_names:
            return None
        node.names = new_names
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Optional[ast.AST]:
        if node.module == "__future__":
            return node
        if any(a.name == "*" for a in node.names):
            return node
        new_names = []
        for alias in node.names:
            bound = alias.asname or alias.name
            if bound in self.used_names:
                new_names.append(alias)
            else:
                self.removed = True
        if not new_names:
            return None
        node.names = new_names
        return node
