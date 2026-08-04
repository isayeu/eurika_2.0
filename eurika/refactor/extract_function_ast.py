"""AST helpers for extract_function (extracted for file size)."""

from __future__ import annotations

import ast
from typing import Optional, Set


def names_used_in_node(node: ast.AST) -> Set[str]:
    """Collect names that are read (loaded) in node, excluding assigned names."""
    loaded: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            loaded.add(n.id)
        elif isinstance(n, ast.Attribute):
            if isinstance(n.value, ast.Name):
                loaded.add(n.value.id)
    return loaded


def _add_func_params(assigned: Set[str], n: ast.FunctionDef) -> None:
    for a in n.args.args:
        assigned.add(a.arg)
    if n.args.vararg:
        assigned.add(n.args.vararg.arg or '')
    if n.args.kwarg:
        assigned.add(n.args.kwarg.arg or '')


def names_assigned_in(node: ast.AST) -> Set[str]:
    """Collect names assigned in node (params, assignments)."""
    assigned: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef):
            _add_func_params(assigned, n)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            assigned.add(n.target.id)
        elif isinstance(n, (ast.For, ast.With)):
            for inner in ast.iter_child_nodes(n):
                if isinstance(inner, ast.Name) and isinstance(getattr(inner, 'ctx', None), ast.Store):
                    assigned.add(inner.id)
    return assigned


def parent_locals(parent: ast.FunctionDef) -> Set[str]:
    """Names in parent scope (params + assigned in body, excluding nested defs)."""
    result: Set[str] = set()
    for a in parent.args.args:
        result.add(a.arg)
    if parent.args.vararg:
        result.add(parent.args.vararg.arg or '')
    if parent.args.kwarg:
        result.add(parent.args.kwarg.arg or '')
    for stmt in parent.body:
        if isinstance(stmt, ast.FunctionDef):
            continue
        result.update(names_assigned_in(stmt))
    return result


def nested_uses_parent_locals(nested: ast.FunctionDef, parent: ast.FunctionDef) -> bool:
    """True if nested function reads any name from parent's scope."""
    used = names_used_in_node(nested)
    nested_own = names_assigned_in(nested)
    used -= nested_own
    parent_locals_set = parent_locals(parent)
    return bool(used & parent_locals_set)


def parent_param_names(parent: ast.FunctionDef) -> Set[str]:
    """Names of parent function's parameters."""
    names: Set[str] = set()
    for a in parent.args.args:
        names.add(a.arg)
    if parent.args.vararg:
        names.add(parent.args.vararg.arg or '')
    if parent.args.kwarg:
        names.add(parent.args.kwarg.arg or '')
    return names


def used_from_parent(nested: ast.FunctionDef, parent: ast.FunctionDef) -> Set[str]:
    """Names from parent scope that nested reads (excluding nested's own)."""
    used = names_used_in_node(nested)
    used -= names_assigned_in(nested)
    return used & parent_locals(parent)


def validate_and_unparse_module(tree: ast.Module) -> Optional[str]:
    """Return source only when resulting AST is syntactically valid."""
    try:
        ast.fix_missing_locations(tree)
        rendered = ast.unparse(tree)
        reparsed = ast.parse(rendered)
        compile(reparsed, '<eurika-extract-validate>', 'exec')
        return rendered
    except Exception:
        return None
