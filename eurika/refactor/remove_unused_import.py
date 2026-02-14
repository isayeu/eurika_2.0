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
    # Imports inside `if TYPE_CHECKING:` are for type hints only (often stringified
    # by `from __future__ import annotations`). Treat them as always used.
    used.update(_names_imported_under_type_checking(tree))
    # Names in __all__ are re-exports; treat them as used.
    used.update(_names_in_all(tree))
    return used


def _names_in_all(tree: ast.AST) -> Set[str]:
    """Return names listed in __all__ = [...] or __all__ = (...)."""
    names: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "__all__":
                names.update(_string_elts(node.value))
                break
    return names


def _string_elts(node: ast.AST) -> Set[str]:
    """Extract string elements from list/tuple literal."""
    out: Set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.add(elt.value)
    return out


def _names_imported_under_type_checking(tree: ast.AST) -> Set[str]:
    """Return names bound by imports inside `if TYPE_CHECKING:` blocks."""
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_cond(node.test):
            for child in ast.walk(node):
                if isinstance(child, ast.Import):
                    for a in child.names:
                        names.add(a.asname or a.name.split(".")[0])
                elif isinstance(child, ast.ImportFrom) and child.module != "__future__":
                    for a in child.names:
                        if a.name != "*":
                            names.add(a.asname or a.name)
    return names


def _is_type_checking_cond(node: ast.AST) -> bool:
    """True if node is `TYPE_CHECKING` (Name in Load context)."""
    return isinstance(node, ast.Name) and node.id == "TYPE_CHECKING"


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
