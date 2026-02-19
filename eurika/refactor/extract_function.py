"""
AST-based Extract Nested Function refactoring (long_function smell).

Moves a nested function from inside a long function to module level.
Conservative: only extracts when the nested function does not use
variables from the parent's scope (no closure dependency).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Set, Tuple


def _names_used_in_node(node: ast.AST) -> Set[str]:
    """Collect names that are read (loaded) in node, excluding assigned names."""
    loaded: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            loaded.add(n.id)
        elif isinstance(n, ast.Attribute):
            # For x.y we consider x as used
            if isinstance(n.value, ast.Name):
                loaded.add(n.value.id)
    return loaded


def _names_assigned_in(node: ast.AST) -> Set[str]:
    """Collect names assigned in node (params, assignments)."""
    assigned: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef):
            for a in n.args.args:
                assigned.add(a.arg)
            if n.args.vararg:
                assigned.add(n.args.vararg.arg or "")
            if n.args.kwarg:
                assigned.add(n.args.kwarg.arg or "")
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            assigned.add(n.target.id)
        elif isinstance(n, (ast.For, ast.With)):
            for inner in ast.iter_child_nodes(n):
                if isinstance(inner, ast.Name) and isinstance(getattr(inner, "ctx", None), ast.Store):
                    assigned.add(inner.id)
    return assigned


def _parent_locals(parent: ast.FunctionDef) -> Set[str]:
    """Names in parent scope (params + assigned in body, excluding nested defs)."""
    result: Set[str] = set()
    for a in parent.args.args:
        result.add(a.arg)
    if parent.args.vararg:
        result.add(parent.args.vararg.arg or "")
    if parent.args.kwarg:
        result.add(parent.args.kwarg.arg or "")
    for stmt in parent.body:
        if isinstance(stmt, ast.FunctionDef):
            continue
        result.update(_names_assigned_in(stmt))
    return result


def _nested_uses_parent_locals(nested: ast.FunctionDef, parent: ast.FunctionDef) -> bool:
    """True if nested function reads any name from parent's scope."""
    used = _names_used_in_node(nested)
    nested_own = _names_assigned_in(nested)
    used -= nested_own
    parent_locals = _parent_locals(parent)
    return bool(used & parent_locals)


def suggest_extract_nested_function(
    file_path: Path,
    function_name: str,
) -> Optional[Tuple[str, int]]:
    """
    Find a nested function inside the given function that can be safely extracted.

    Returns (nested_function_name, approximate_line_count) or None.
    Prefers the largest self-contained nested function.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    parent_func: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            parent_func = node
            break
    if not parent_func:
        return None

    def _has_nonlocal_or_global(nested: ast.FunctionDef) -> bool:
        """True if nested function declares nonlocal or global (modifies outer scope)."""
        for stmt in ast.walk(nested):
            if isinstance(stmt, (ast.Nonlocal, ast.Global)):
                return True
        return False

    candidates: List[Tuple[ast.FunctionDef, int]] = []
    for stmt in parent_func.body:
        if isinstance(stmt, ast.FunctionDef):
            if _nested_uses_parent_locals(stmt, parent_func):
                continue
            if _has_nonlocal_or_global(stmt):
                continue
            line_count = (stmt.end_lineno or stmt.lineno or 0) - (stmt.lineno or 0) + 1
            if line_count >= 3:
                candidates.append((stmt, line_count))

    if not candidates:
        return None
    best = max(candidates, key=lambda x: x[1])
    return (best[0].name, best[1])


def extract_nested_function(
    file_path: Path,
    parent_function_name: str,
    nested_function_name: str,
) -> Optional[str]:
    """
    Move the nested function to module level, placing it before the parent's container.

    Returns new file content or None on failure.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    def find_and_extract(node: ast.AST) -> Optional[ast.FunctionDef]:
        if isinstance(node, ast.FunctionDef):
            if node.name == parent_function_name:
                for stmt in node.body:
                    if isinstance(stmt, ast.FunctionDef) and stmt.name == nested_function_name:
                        return stmt
                return None
            for stmt in node.body:
                found = find_and_extract(stmt)
                if found:
                    return found
        elif isinstance(node, (ast.ClassDef, ast.Module)):
            for stmt in getattr(node, "body", []):
                found = find_and_extract(stmt)
                if found:
                    return found
        return None

    def remove_nested_from_parent(node: ast.AST) -> bool:
        if isinstance(node, ast.FunctionDef) and node.name == parent_function_name:
            node.body = [
                s for s in node.body
                if not (isinstance(s, ast.FunctionDef) and s.name == nested_function_name)
            ]
            return True
        for stmt in getattr(node, "body", []):
            if remove_nested_from_parent(stmt):
                return True
        return False

    nested = find_and_extract(tree)
    if nested is None:
        return None

    if not remove_nested_from_parent(tree):
        return None

    # Build extracted function (standalone copy), preserve location for unparse
    extracted = ast.copy_location(
        ast.FunctionDef(
            name=nested.name,
            args=nested.args,
            body=nested.body,
            decorator_list=list(nested.decorator_list),
            returns=nested.returns,
            type_comment=getattr(nested, "type_comment", None),
        ),
        nested,
    )
    ast.fix_missing_locations(extracted)

    # Find insert index: before the module-level node containing parent (class or function)
    insert_idx: Optional[int] = None
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, ast.FunctionDef) and stmt.name == parent_function_name:
            insert_idx = i
            break
        if isinstance(stmt, ast.ClassDef):
            for m in stmt.body:
                if isinstance(m, ast.FunctionDef) and m.name == parent_function_name:
                    insert_idx = i
                    break
            if insert_idx is not None:
                break
    if insert_idx is None:
        return None

    new_body = list(tree.body)
    new_body.insert(insert_idx, extracted)
    tree.body = new_body

    try:
        return ast.unparse(tree)
    except Exception:
        return None


# TODO (eurika): refactor deep_nesting '_names_assigned_in' — consider extracting nested block


# TODO (eurika): refactor long_function 'extract_nested_function' — consider extracting helper
