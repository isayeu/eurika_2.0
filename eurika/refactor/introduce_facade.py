"""
Introduce facade for bottleneck refactoring.

Creates a new {stem}_api.py that re-exports public symbols from the bottleneck.
Reduces direct fan-in by providing a stable API boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Tuple


def introduce_facade(
    bottleneck_path: Path,
    target_file: str,
    callers: Optional[List[str]] = None,
) -> Optional[Tuple[str, str]]:
    """
    Create a facade module that re-exports public symbols from the bottleneck.

    Args:
        bottleneck_path: Path to the bottleneck module.
        target_file: Original target path (e.g. "eurika/reasoning/graph_ops.py") for naming.
        callers: Optional list of caller module paths (for docstring).

    Returns:
        (new_rel_path, new_content) or None if no public symbols.
    """
    try:
        content = bottleneck_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    names = _public_names(tree)
    if not names:
        return None

    t = Path(target_file)
    if t.stem.endswith("_api"):
        return None  # Already a facade
    stem = t.stem
    parent = t.parent
    new_name = stem + "_api.py"
    new_rel_path = str(parent / new_name) if str(parent) != "." else new_name

    # Import path: eurika/reasoning/graph_ops -> from eurika.reasoning.graph_ops; patch_apply -> from patch_apply
    parent_str = str(parent).replace("/", ".").replace("\\", ".").strip(". ")
    if parent_str:
        mod_path = f"{parent_str}.{stem}"
    else:
        mod_path = stem
    import_stmt = f"from {mod_path} import " + ", ".join(names)

    callers_note = ""
    if callers:
        callers_note = f"\n\nCallers (candidates to switch): {', '.join(callers[:5])}{'...' if len(callers) > 5 else ''}."

    new_content = f'''"""Facade for {stem} — stable API boundary.{callers_note}"""

{import_stmt}

__all__ = {repr(names)}
'''

    return (new_rel_path, new_content)


def _public_names(tree: ast.AST) -> List[str]:
    """Extract public top-level names (classes, functions). Prefer __all__ if present."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    return _names_from_all(node.value)
    # No __all__: collect top-level def/class not starting with _
    names: List[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _names_from_all(node: ast.AST) -> List[str]:
    """Extract string names from __all__ = [...] or (...)."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            elt.value for elt in node.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
    return []
