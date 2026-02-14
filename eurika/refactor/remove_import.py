"""
Remove import from Python file (AST-based).

Used for Remove Cyclic Import operation: given (src_file, dst_file) edge to break,
removes the import statement in src that imports the module resolving to dst.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


def remove_import_from_file(
    file_path: Path,
    target_module: str,
) -> Optional[str]:
    """
    Remove the import of target_module from a Python file.

    Handles:
    - `import target_module` / `import target_module as x`
    - `from target_module import ...`
    Uses first-part matching: "eurika.storage" matches target_module "eurika".

    Returns:
        New file content with the import removed, or None if not found / error.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    target_first = target_module.split(".")[0]
    remover = _ImportRemover(target_first, target_module)
    remover.visit(tree)
    if not remover.removed:
        return None
    return ast.unparse(tree)


class _ImportRemover(ast.NodeTransformer):
    """AST transformer that removes matching imports."""

    def __init__(self, target_first: str, target_full: str) -> None:
        self.target_first = target_first
        self.target_full = target_full
        self.removed = False

    def visit_Import(self, node: ast.Import) -> Optional[ast.AST]:
        new_names = []
        for alias in node.names:
            first = alias.name.split(".")[0]
            if first != self.target_first:
                new_names.append(alias)
            else:
                self.removed = True
        if not new_names:
            return None  # remove whole statement
        node.names = new_names
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Optional[ast.AST]:
        if node.module is None:
            return node
        first = node.module.split(".")[0]
        if first != self.target_first:
            return node
        self.removed = True
        return None  # remove whole statement
