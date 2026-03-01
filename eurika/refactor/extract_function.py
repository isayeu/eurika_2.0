"""
AST-based Extract Nested Function refactoring (long_function smell).

Moves a nested function from inside a long function to module level.
Conservative: only extracts when the nested function does not use
variables from the parent's scope (no closure dependency).
"""
from __future__ import annotations
import ast
import builtins
from pathlib import Path
from typing import List, Optional, Set, Tuple

def _names_used_in_node(node: ast.AST) -> Set[str]:
    """Collect names that are read (loaded) in node, excluding assigned names."""
    loaded: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            loaded.add(n.id)
        elif isinstance(n, ast.Attribute):
            if isinstance(n.value, ast.Name):
                loaded.add(n.value.id)
    return loaded

def _extracted_block_29(assigned, n):
    for a in n.args.args:
        assigned.add(a.arg)
    if n.args.vararg:
        assigned.add(n.args.vararg.arg or '')
    if n.args.kwarg:
        assigned.add(n.args.kwarg.arg or '')

def _names_assigned_in(node: ast.AST) -> Set[str]:
    """Collect names assigned in node (params, assignments)."""
    assigned: Set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef):
            _extracted_block_29(assigned, n)
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

def _parent_locals(parent: ast.FunctionDef) -> Set[str]:
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
        names.add(parent.args.vararg.arg or '')
    if parent.args.kwarg:
        names.add(parent.args.kwarg.arg or '')
    return names

def _used_from_parent(nested: ast.FunctionDef, parent: ast.FunctionDef) -> Set[str]:
    """Names from parent scope that nested reads (excluding nested's own)."""
    used = _names_used_in_node(nested)
    used -= _names_assigned_in(nested)
    return used & _parent_locals(parent)

def _validate_and_unparse_module(tree: ast.Module) -> Optional[str]:
    """Return source only when resulting AST is syntactically valid."""
    try:
        ast.fix_missing_locations(tree)
        rendered = ast.unparse(tree)
        reparsed = ast.parse(rendered)
        compile(reparsed, '<eurika-extract-validate>', 'exec')
        return rendered
    except Exception:
        return None

def _find_parent_with_nested(tree: ast.Module, parent_function_name: str, nested_function_name: str) -> Optional[Tuple[ast.FunctionDef, ast.AST]]:
    """
    Find a concrete parent function node and its module-level container.

    Container is either the parent function itself (module-level function) or
    a module-level class/function that contains the parent.
    """
    candidates: List[Tuple[ast.FunctionDef, ast.AST]] = []

    def visit(node: ast.AST, container: ast.AST) -> None:
        body = list(getattr(node, 'body', []) or [])
        for child in body:
            next_container = child if isinstance(node, ast.Module) else container
            if isinstance(child, ast.FunctionDef):
                if child.name == parent_function_name:
                    for stmt in child.body:
                        if isinstance(stmt, ast.FunctionDef) and stmt.name == nested_function_name:
                            candidates.append((child, next_container))
                            break
                visit(child, next_container)
            elif isinstance(child, ast.ClassDef):
                visit(child, next_container)
    visit(tree, tree)
    if not candidates:
        return None
    return min(candidates, key=lambda item: getattr(item[0], 'lineno', 0))

def _has_nonlocal_or_global(nested: ast.FunctionDef) -> bool:
    """True if nested function declares nonlocal or global (modifies outer scope)."""
    for stmt in ast.walk(nested):
        if isinstance(stmt, (ast.Nonlocal, ast.Global)):
            return True
    return False

def suggest_extract_nested_function(file_path: Path, function_name: str) -> Optional[Tuple[str, int, List[str]]]:
    """
    Find a nested function inside the given function that can be safely extracted.

    Returns (nested_function_name, approximate_line_count, extra_params) or None.
    extra_params: list of parent var names to pass as args when nested uses them (max 3).
    Prefers the largest self-contained nested function; then nested that uses only a small
    set of parent-scope vars (params or locals).
    """
    try:
        content = file_path.read_text(encoding='utf-8')
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
    parent_locals = _parent_locals(parent_func)
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    candidates: List[Tuple[ast.FunctionDef, int, List[str]]] = []
    for stmt in parent_func.body:
        if isinstance(stmt, ast.FunctionDef):
            if _has_nonlocal_or_global(stmt):
                continue
            free_names = _names_used_in_node(stmt) - _names_assigned_in(stmt)
            free_names.discard(stmt.name)
            used_from_parent = free_names & parent_locals
            unresolved = free_names - parent_locals - module_bound - builtin_names
            if unresolved or len(used_from_parent) > 3:
                continue
            extra_params = sorted(used_from_parent)
            line_count = (stmt.end_lineno or stmt.lineno or 0) - (stmt.lineno or 0) + 1
            if line_count >= 3:
                candidates.append((stmt, line_count, extra_params))
    if not candidates:
        return None
    best = max(candidates, key=lambda x: x[1])
    return (best[0].name, best[1], best[2])

def add_extra_args_to_calls(node: ast.AST, extra, nested_function_name) -> None:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id == nested_function_name and extra:
                for p in extra:
                    n.args.append(ast.Name(id=p, ctx=ast.Load()))

def extract_nested_function(file_path: Path, parent_function_name: str, nested_function_name: str, extra_params: Optional[List[str]]=None) -> Optional[str]:
    """
    Move the nested function to module level, placing it before the parent's container.
    When extra_params is set, adds those parent vars as parameters and passes them at call sites.
    Returns new file content or None on failure.
    """
    extra = list(extra_params or [])
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    parent_and_container = _find_parent_with_nested(tree, parent_function_name, nested_function_name)
    if parent_and_container is None:
        return None
    parent_node, container_node = parent_and_container
    nested: Optional[ast.FunctionDef] = None
    retained_body: List[ast.stmt] = []
    for stmt in parent_node.body:
        if nested is None and isinstance(stmt, ast.FunctionDef) and (stmt.name == nested_function_name):
            nested = stmt
            continue
        retained_body.append(stmt)
    if nested is None:
        return None
    free_names = _names_used_in_node(nested) - _names_assigned_in(nested)
    free_names.discard(nested.name)
    parent_locals = _parent_locals(parent_node)
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    unresolved = free_names - parent_locals - module_bound - builtin_names
    used_from_parent = free_names & parent_locals
    if unresolved or len(used_from_parent) > 3:
        return None
    provided = set(extra)
    if not provided and used_from_parent:
        extra = sorted(used_from_parent)
        provided = set(extra)
    if provided:
        if len(provided) > 3:
            return None
        if provided - parent_locals:
            return None
        if not used_from_parent <= provided:
            return None
    add_extra_args_to_calls(parent_node, extra, nested_function_name)
    parent_node.body = retained_body
    new_args_list = list(nested.args.args)
    for p in extra:
        if not any((a.arg == p for a in new_args_list)):
            new_args_list.append(ast.arg(arg=p))
    extracted_args = ast.arguments(posonlyargs=getattr(nested.args, 'posonlyargs', []) or [], args=new_args_list, vararg=nested.args.vararg, kwonlyargs=nested.args.kwonlyargs, kw_defaults=nested.args.kw_defaults, kwarg=nested.args.kwarg, defaults=nested.args.defaults) if extra else nested.args
    extracted = ast.copy_location(ast.FunctionDef(name=nested.name, args=extracted_args, body=nested.body, decorator_list=list(nested.decorator_list), returns=nested.returns, type_comment=getattr(nested, 'type_comment', None)), nested)
    ast.fix_missing_locations(extracted)
    insert_idx: Optional[int] = None
    for i, stmt in enumerate(tree.body):
        if stmt is container_node:
            insert_idx = i
            break
    if insert_idx is None:
        return None
    new_body = list(tree.body)
    new_body.insert(insert_idx, extracted)
    tree.body = new_body
    return _validate_and_unparse_module(tree)

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


def _names_bound_by_block_node(node: ast.AST) -> Set[str]:
    """Names that a For/With/AsyncFor node binds (loop vars, with-vars)."""
    result: Set[str] = set()
    if isinstance(node, (ast.For, ast.AsyncFor)):
        target = getattr(node, "target", None)
        if isinstance(target, ast.Name):
            result.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    result.add(elt.id)
    elif isinstance(node, ast.With):
        items = getattr(node, "items", None)
        if items is not None:
            for item in items:
                var = getattr(item, "optional_vars", None)
                if isinstance(var, ast.Name):
                    result.add(var.id)
                elif isinstance(var, (ast.Tuple, ast.List)):
                    for elt in var.elts:
                        if isinstance(elt, ast.Name):
                            result.add(elt.id)
        else:
            var = getattr(node, "optional_vars", None)
            if isinstance(var, ast.Name):
                result.add(var.id)
    return result

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

def _module_level_bound_names(tree: ast.AST) -> Set[str]:
    """Collect names bound at module scope (globals accessible to extracted helper)."""
    names: Set[str] = set()
    if not isinstance(tree, ast.Module):
        return names
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(stmt, ast.Import):
            for a in stmt.names:
                names.add((a.asname or a.name.split('.')[0]).strip())
        elif isinstance(stmt, ast.ImportFrom):
            for a in stmt.names:
                names.add((a.asname or a.name).strip())
    return names

def suggest_extract_block(file_path: Path, function_name: str, *, min_lines: int=5, max_extra_params: int=3) -> Optional[Tuple[str, int, int, List[str]]]:
    """
    Find a deeply nested block (if/for/while/with body) that can be extracted to a helper.

    Returns (helper_name, block_start_line, line_count, extra_params) or None.
    extra_params: names from parent scope to pass as args (max max_extra_params).
    Uses only parent params; skips blocks that assign to parent params.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
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
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))

    def _nesting_depth(n: ast.AST) -> int:
        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            children = list(ast.iter_child_nodes(n))
            child_depths = [_nesting_depth(c) for c in children]
            return 1 + (max(child_depths) if child_depths else 0)
        return max((_nesting_depth(c) for c in ast.iter_child_nodes(n)), default=0)
    block_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    candidates: List[Tuple[ast.stmt, List[ast.stmt], int, int]] = []

    def _block_contains_extracted_call(n: ast.AST) -> bool:
        """True if block (recursively) contains a call to _extracted_block_*."""
        for node in ast.walk(n):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.startswith("_extracted_block_"):
                    return True
        return False

    def collect_blocks(node: ast.AST, depth: int) -> None:
        if isinstance(node, block_types):
            body = getattr(node, 'body', None)
            if body and isinstance(body, list):
                if _block_contains_extracted_call(node):
                    pass  # skip block that calls already-extracted helper (avoid recursion)
                elif not _block_has_control_flow_exit(body):
                    used = _names_used_in_statements(body)
                    assigned = _names_assigned_in_statements(body)
                    writes_to_params = assigned & parent_params
                    free_names = used - assigned
                    used_from_outer = free_names & parent_params
                    block_bound = _names_bound_by_block_node(node) & free_names
                    extra_count = len(used_from_outer | block_bound)
                    unresolved = free_names - parent_locals - module_bound - builtin_names
                    if (
                        not unresolved
                        and not writes_to_params
                        and extra_count <= max_extra_params
                    ):
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
    used_from_outer = (used - assigned) & parent_params
    block_bound = _names_bound_by_block_node(block_node) & (used - assigned)
    all_extra = used_from_outer | block_bound
    if len(all_extra) > max_extra_params:
        all_extra = used_from_outer
    extra_params = sorted(all_extra)
    helper_name = f'_extracted_block_{block_node.lineno}'
    return (helper_name, block_node.lineno, line_count, extra_params)

def extract_block_to_helper(file_path: Path, parent_function_name: str, block_start_line: int, helper_name: str, extra_params: Optional[List[str]]=None) -> Optional[str]:
    """
    Extract a block (if/for/while/with body) into a new helper function.
    Replaces the block with a call to the helper.
    """
    extra = list(extra_params or [])
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    block_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    parent_func: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == parent_function_name:
            parent_func = node
            break
    if parent_func is None:
        return None

    def _block_has_extracted_call(n: ast.AST) -> bool:
        """True if block contains a call to _extracted_block_* (avoids recursion)."""
        for node in ast.walk(n):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id.startswith("_extracted_block_"):
                    return True
        return False

    candidates: List[Tuple[ast.AST, List[ast.stmt], int, int]] = []

    def collect_blocks(node: ast.AST, depth: int) -> None:
        if isinstance(node, block_types):
            body = getattr(node, 'body', None)
            if body and isinstance(body, list):
                if _block_has_extracted_call(node):
                    pass  # skip: would put call inside helper -> recursion
                else:
                    lineno = int(getattr(node, 'lineno', -1) or -1)
                    line_delta = abs(lineno - block_start_line) if lineno > 0 else 10 ** 6
                    candidates.append((node, body, line_delta, depth))
        for child in ast.iter_child_nodes(node):
            collect_blocks(child, depth + 1)
    collect_blocks(parent_func, 0)
    if not candidates:
        return None
    block_node, body, _, _ = sorted(candidates, key=lambda item: (item[2], -item[3], getattr(item[0], 'lineno', 10 ** 9)))[0]
    block_bound = _names_bound_by_block_node(block_node)
    body_used = _names_used_in_statements(body) - _names_assigned_in_statements(body)
    for name in sorted(block_bound & body_used):
        if name not in extra:
            extra.append(name)

    parent_locals = _parent_locals(parent_func)
    return_var: Optional[str] = None
    if body and isinstance(body[-1], ast.Assign):
        last = body[-1]
        if len(last.targets) == 1 and isinstance(last.targets[0], ast.Name):
            out_name = last.targets[0].id
            if out_name in parent_locals and out_name not in block_bound:
                return_var = out_name

    def replace_body_with_call(node: ast.AST) -> bool:
        if node is block_node:
            call_args: List[ast.expr] = [ast.Name(id=p, ctx=ast.Load()) for p in extra]
            call_expr = ast.Call(ast.Name(id=helper_name, ctx=ast.Load()), call_args, [])
            if return_var:
                call = ast.Assign(targets=[ast.Name(id=return_var, ctx=ast.Store())], value=call_expr)
            else:
                call = ast.Expr(call_expr)
            typed_node = node
            if isinstance(typed_node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                typed_node.body = [call]
            else:
                return False
            return True
        for child in ast.iter_child_nodes(node):
            if replace_body_with_call(child):
                return True
        return False
    if not replace_body_with_call(parent_func):
        return None
    if return_var:
        new_body = list(body[:-1])
        new_body.append(ast.Return(body[-1].value))
        body = new_body
    args_list = [ast.arg(arg=p) for p in extra]
    extracted = ast.FunctionDef(name=helper_name, args=ast.arguments(posonlyargs=[], args=args_list, vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]), body=body, decorator_list=[], returns=None)
    ast.copy_location(extracted, block_node)
    ast.fix_missing_locations(extracted)

    def _contains_function_named(node: ast.AST, target_name: str) -> bool:
        for n in ast.walk(node):
            if isinstance(n, ast.FunctionDef) and n.name == target_name:
                return True
        return False
    insert_idx: Optional[int] = None
    for i, stmt in enumerate(tree.body):
        if _contains_function_named(stmt, parent_function_name):
            insert_idx = i
            break
    if insert_idx is None:
        return None
    new_body = list(tree.body)
    new_body.insert(insert_idx, extracted)
    tree.body = new_body
    return _validate_and_unparse_module(tree)

def diagnose_extract_nested_failure(file_path: Path, parent_function_name: str, nested_function_name: str) -> str:
    """Return a stable, human-readable reason when nested extraction returns None."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return 'extract_nested_function: file read failed'
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 'extract_nested_function: source has syntax errors'
    found = _find_parent_with_nested(tree, parent_function_name, nested_function_name)
    if found is None:
        return 'extract_nested_function: parent or nested function not found'
    parent_node, _ = found
    nested_node: Optional[ast.FunctionDef] = None
    for stmt in parent_node.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == nested_function_name:
            nested_node = stmt
            break
    if nested_node is None:
        return 'extract_nested_function: nested function not found in parent body'
    free_names = _names_used_in_node(nested_node) - _names_assigned_in(nested_node)
    free_names.discard(nested_node.name)
    parent_locals = _parent_locals(parent_node)
    used_from_parent = free_names & parent_locals
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    unresolved = free_names - parent_locals - module_bound - builtin_names
    if unresolved:
        return 'extract_nested_function: nested has unresolved free names'
    if len(used_from_parent) > 3:
        return 'extract_nested_function: nested needs more than 3 parent vars'
    if _nested_uses_parent_locals(nested_node, parent_node):
        return 'extract_nested_function: nested uses parent locals but params were not provided'
    return 'extract_nested_function: AST transform validation failed'

def diagnose_extract_block_failure(file_path: Path, parent_function_name: str, block_start_line: int) -> str:
    """Return a stable, human-readable reason when block extraction returns None."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return 'extract_block_to_helper: file read failed'
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return 'extract_block_to_helper: source has syntax errors'
    parent_func: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == parent_function_name:
            parent_func = node
            break
    if parent_func is None:
        return 'extract_block_to_helper: parent function not found'
    block_types = (ast.If, ast.For, ast.While, ast.Try, ast.With)
    candidates = [n for n in ast.walk(parent_func) if isinstance(n, block_types) and isinstance(getattr(n, 'body', None), list) and getattr(n, 'body', None)]
    if not candidates:
        return 'extract_block_to_helper: no extractable blocks in parent function'
    if not any((int(getattr(n, 'lineno', -1) or -1) == block_start_line for n in candidates)):
        return 'extract_block_to_helper: target block line not found'
    return 'extract_block_to_helper: AST transform validation failed'