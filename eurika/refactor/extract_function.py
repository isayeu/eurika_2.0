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


def _parent_param_names(parent: ast.FunctionDef) -> Set[str]:
    """Names of parent function's parameters."""
    names: Set[str] = set()
    for a in parent.args.args:
        names.add(a.arg)
    if parent.args.vararg:
        names.add(parent.args.vararg.arg or "")
    if parent.args.kwarg:
        names.add(parent.args.kwarg.arg or "")
    return names


def _used_from_parent(nested: ast.FunctionDef, parent: ast.FunctionDef) -> Set[str]:
    """Names from parent scope that nested reads (excluding nested's own)."""
    used = _names_used_in_node(nested)
    used -= _names_assigned_in(nested)
    return used & _parent_locals(parent)


def suggest_extract_nested_function(
    file_path: Path,
    function_name: str,
) -> Optional[Tuple[str, int, List[str]]]:
    """
    Find a nested function inside the given function that can be safely extracted.

    Returns (nested_function_name, approximate_line_count, extra_params) or None.
    extra_params: list of parent var names to pass as args when nested uses them (max 3).
    Prefers the largest self-contained nested function; then nested that uses only parent params.
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

    parent_params = _parent_param_names(parent_func)

    candidates: List[Tuple[ast.FunctionDef, int, List[str]]] = []
    for stmt in parent_func.body:
        if isinstance(stmt, ast.FunctionDef):
            if _has_nonlocal_or_global(stmt):
                continue
            used_from = _used_from_parent(stmt, parent_func)
            if not used_from:
                extra_params: List[str] = []
            elif used_from <= parent_params and len(used_from) <= 3:
                extra_params = sorted(used_from)
            else:
                continue
            line_count = (stmt.end_lineno or stmt.lineno or 0) - (stmt.lineno or 0) + 1
            if line_count >= 3:
                candidates.append((stmt, line_count, extra_params))

    if not candidates:
        return None
    best = max(candidates, key=lambda x: x[1])
    return (best[0].name, best[1], best[2])


def extract_nested_function(
    file_path: Path,
    parent_function_name: str,
    nested_function_name: str,
    extra_params: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Move the nested function to module level, placing it before the parent's container.
    When extra_params is set, adds those parent vars as parameters and passes them at call sites.
    Returns new file content or None on failure.
    """
    extra = list(extra_params or [])
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

    def add_extra_args_to_calls(node: ast.AST) -> None:
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id == nested_function_name and extra:
                    for p in extra:
                        n.args.append(ast.Name(id=p, ctx=ast.Load()))

    def remove_nested_from_parent(node: ast.AST) -> bool:
        if isinstance(node, ast.FunctionDef) and node.name == parent_function_name:
            add_extra_args_to_calls(node)
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

    new_args_list = list(nested.args.args)
    for p in extra:
        if not any(a.arg == p for a in new_args_list):
            new_args_list.append(ast.arg(arg=p))
    extracted_args = ast.arguments(
        posonlyargs=getattr(nested.args, "posonlyargs", []) or [],
        args=new_args_list,
        vararg=nested.args.vararg,
        kwonlyargs=nested.args.kwonlyargs,
        kw_defaults=nested.args.kw_defaults,
        kwarg=nested.args.kwarg,
        defaults=nested.args.defaults,
    ) if extra else nested.args

    extracted = ast.copy_location(
        ast.FunctionDef(
            name=nested.name,
            args=extracted_args,
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


def _block_has_control_flow_exit(block: List[ast.stmt]) -> bool:
    """True if block contains break, continue, or return (not safely extractable)."""
    for stmt in block:
        for n in ast.walk(stmt):
            if isinstance(n, (ast.Break, ast.Continue, ast.Return)):
                return True
    return False


def _block_line_count(block: List[ast.stmt]) -> int:
    """Approximate line count of block."""
    if not block:
        return 0
    first = block[0]
    last = block[-1]
    return (last.end_lineno or last.lineno or 0) - (first.lineno or 0) + 1


def _names_used_in_statements(stmts: List[ast.stmt]) -> Set[str]:
    """Collect names loaded in statements."""
    loaded: Set[str] = set()
    for s in stmts:
        loaded.update(_names_used_in_node(s))
    return loaded


def _names_assigned_in_statements(stmts: List[ast.stmt]) -> Set[str]:
    """Collect names assigned in statements."""
    assigned: Set[str] = set()
    for s in stmts:
        assigned.update(_names_assigned_in(s))
    return assigned


def suggest_extract_block(
    file_path: Path,
    function_name: str,
    *,
    min_lines: int = 5,
    max_extra_params: int = 3,
) -> Optional[Tuple[str, int, int, List[str]]]:
    """
    Find a deeply nested block (if/for/while/with body) that can be extracted to a helper.

    Returns (helper_name, block_start_line, line_count, extra_params) or None.
    extra_params: names from parent scope to pass as args (max max_extra_params).
    Only considers blocks with no break/continue/return; uses only parent params.
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

    parent_params = _parent_param_names(parent_func)
    parent_locals = _parent_locals(parent_func)

    def _nesting_depth(n: ast.AST) -> int:
        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            children = list(ast.iter_child_nodes(n))
            child_depths = [_nesting_depth(c) for c in children]
            return 1 + (max(child_depths) if child_depths else 0)
        return max((_nesting_depth(c) for c in ast.iter_child_nodes(n)), default=0)

    block_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    candidates: List[Tuple[ast.AST, List[ast.stmt], int, int]] = []

    def collect_blocks(node: ast.AST, depth: int) -> None:
        if isinstance(node, block_types):
            body = getattr(node, "body", None)
            if body and isinstance(body, list):
                if not _block_has_control_flow_exit(body):
                    used = _names_used_in_statements(body)
                    assigned = _names_assigned_in_statements(body)
                    used_from_outer = (used - assigned) & parent_locals
                    if used_from_outer <= parent_params and len(used_from_outer) <= max_extra_params:
                        line_count = _block_line_count(body)
                        if line_count >= min_lines:
                            candidates.append((node, body, depth, line_count))
            for child in ast.iter_child_nodes(node):
                collect_blocks(child, depth + 1)
        else:
            for child in ast.iter_child_nodes(node):
                collect_blocks(child, depth)

    collect_blocks(parent_func, 0)

    if not candidates:
        return None

    best = max(candidates, key=lambda x: (x[2], x[3]))
    block_node, body, _, line_count = best
    used = _names_used_in_statements(body)
    assigned = _names_assigned_in_statements(body)
    extra_params = sorted((used - assigned) & parent_params)
    helper_name = f"_extracted_block_{block_node.lineno}"
    return (helper_name, block_node.lineno, line_count, extra_params)


def extract_block_to_helper(
    file_path: Path,
    parent_function_name: str,
    block_start_line: int,
    helper_name: str,
    extra_params: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Extract a block (if/for/while/with body) into a new helper function.
    Replaces the block with a call to the helper.
    """
    extra = list(extra_params or [])
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    block_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    target_block: Optional[Tuple[ast.AST, List[ast.stmt], ast.AST]] = None

    def find_block(node: ast.AST) -> bool:
        nonlocal target_block
        if isinstance(node, block_types) and getattr(node, "lineno", None) == block_start_line:
            body = getattr(node, "body", None)
            if body and isinstance(body, list):
                target_block = (node, body, node)
                return True
        for child in ast.iter_child_nodes(node):
            if find_block(child):
                return True
        return False

    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.FunctionDef) and stmt.name == parent_function_name:
            if find_block(stmt):
                break

    if not target_block:
        return None

    block_node, body, _ = target_block

    def replace_body_with_call(node: ast.AST) -> bool:
        if node is block_node:
            call_args = [ast.Name(id=p, ctx=ast.Load()) for p in extra]
            call = ast.Expr(ast.Call(ast.Name(id=helper_name, ctx=ast.Load()), call_args, []))
            if isinstance(node, ast.For):
                node.body = [call]
            elif isinstance(node, ast.While):
                node.body = [call]
            elif isinstance(node, ast.With):
                node.body = [call]
            elif isinstance(node, ast.If):
                node.body = [call]
            return True
        for child in ast.iter_child_nodes(node):
            if replace_body_with_call(child):
                return True
        return False

    replace_body_with_call(tree)

    args_list = [ast.arg(arg=p) for p in extra]
    extracted = ast.FunctionDef(
        name=helper_name,
        args=ast.arguments(
            posonlyargs=[],
            args=args_list,
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=body,
        decorator_list=[],
        returns=None,
    )
    ast.copy_location(extracted, block_node)
    ast.fix_missing_locations(extracted)

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
