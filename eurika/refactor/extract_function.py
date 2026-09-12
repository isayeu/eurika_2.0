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
from .extract_function_ast import names_assigned_in, names_used_in_node, nested_uses_parent_locals, parent_locals, parent_param_names, validate_and_unparse_module

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
    plocals = parent_locals(parent_func)
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    candidates: List[Tuple[ast.FunctionDef, int, List[str]]] = []
    for stmt in parent_func.body:
        if isinstance(stmt, ast.FunctionDef):
            if _has_nonlocal_or_global(stmt):
                continue
            free_names = names_used_in_node(stmt) - names_assigned_in(stmt)
            free_names.discard(stmt.name)
            used_from_parent = free_names & plocals
            unresolved = free_names - plocals - module_bound - builtin_names
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
    free_names = names_used_in_node(nested) - names_assigned_in(nested)
    free_names.discard(nested.name)
    plocals = parent_locals(parent_node)
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    unresolved = free_names - plocals - module_bound - builtin_names
    used_from_parent = free_names & plocals
    if unresolved or len(used_from_parent) > 3:
        return None
    provided = set(extra)
    if not provided and used_from_parent:
        extra = sorted(used_from_parent)
        provided = set(extra)
    if provided:
        if len(provided) > 3:
            return None
        if provided - plocals:
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
    return validate_and_unparse_module(tree)

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
        target = getattr(node, 'target', None)
        if isinstance(target, ast.Name):
            result.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    result.add(elt.id)
    elif isinstance(node, ast.With):
        items = getattr(node, 'items', None)
        if items is not None:
            for item in items:
                var = getattr(item, 'optional_vars', None)
                if isinstance(var, ast.Name):
                    result.add(var.id)
                elif isinstance(var, (ast.Tuple, ast.List)):
                    for elt in var.elts:
                        if isinstance(elt, ast.Name):
                            result.add(elt.id)
        else:
            var = getattr(node, 'optional_vars', None)
            if isinstance(var, ast.Name):
                result.add(var.id)
    return result

def _loop_target_names_in_statements(stmts: List[ast.stmt]) -> Set[str]:
    """For/with targets inside stmts — loop locals, never extract return values."""
    names: Set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.For, ast.AsyncFor)):
                for t in ast.walk(node.target):
                    if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                        names.add(t.id)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    var = item.optional_vars
                    if var is None:
                        continue
                    for t in ast.walk(var):
                        if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                            names.add(t.id)
    return names


def _outer_augassign_names(stmts: List[ast.stmt], outer: Set[str]) -> Set[str]:
    """Outer names updated via ``+=`` / ``-=`` etc. — unsafe for single-return extract."""
    names: Set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                if node.target.id in outer:
                    names.add(node.target.id)
    return names

def _names_used_in_statements(stmts: List[ast.stmt]) -> Set[str]:
    """Collect names loaded in statements."""
    loaded: Set[str] = set()
    for s in stmts:
        loaded.update(names_used_in_node(s))
    return loaded

def names_assigned_in_statements(stmts: List[ast.stmt]) -> Set[str]:
    """Collect names assigned in statements."""
    assigned: Set[str] = set()
    for s in stmts:
        assigned.update(names_assigned_in(s))
    return assigned

def names_assigned_in_excluding(node: ast.AST, exclude: ast.AST) -> Set[str]:
    """Names assigned in node minus names assigned inside exclude (for scope checks)."""
    full = names_assigned_in(node)
    in_exclude = names_assigned_in(exclude)
    return full - in_exclude


def _names_loaded_outside(parent: ast.AST, block: ast.AST) -> Set[str]:
    """Names loaded in ``parent`` excluding the ``block`` subtree."""
    skip = {id(n) for n in ast.walk(block)}
    names: Set[str] = set()
    for n in ast.walk(parent):
        if id(n) in skip:
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            names.add(n.id)
    return names


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

def _block_contains_extracted_call(n: ast.AST) -> bool:
    """True if block (recursively) contains a call to _extracted_block_*."""
    for node in ast.walk(n):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id.startswith('_extracted_block_'):
                return True
    return False

def suggest_extract_block(file_path: Path, function_name: str, *, min_lines: int=5, max_extra_params: int=6) -> Optional[Tuple[str, int, int, List[str]]]:
    """
    Find a deeply nested block (if/for/while/with body) that can be extracted to a helper.

    Returns (helper_name, block_start_line, line_count, extra_params) or None.
    extra_params: names from parent scope (params + body locals) and block-bound names (loop vars)
    to pass as args. Uses plocals so rows, report, path etc. are included, not just params.
    Skips blocks that assign to parent params. Max max_extra_params.
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
    parent_params = parent_param_names(parent_func)
    plocals = parent_locals(parent_func)
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

    def collect_blocks(node: ast.AST, depth: int) -> None:
        if isinstance(node, block_types):
            body = getattr(node, 'body', None)
            if body and isinstance(body, list):
                if _block_contains_extracted_call(node):
                    pass
                elif _is_low_value_extract_body(body):
                    pass
                elif not _block_has_control_flow_exit(body):
                    used = _names_used_in_statements(body)
                    assigned = names_assigned_in_statements(body)
                    writes_to_params = assigned & parent_params
                    outer_assigned = names_assigned_in_excluding(parent_func, node)
                    if len(assigned & outer_assigned) > 1:
                        pass
                    else:
                        free_names = used - assigned
                        used_from_outer = free_names & plocals
                        block_bound = _names_bound_by_block_node(node) & free_names
                        extra_count = len(used_from_outer | block_bound)
                        unresolved = free_names - plocals - module_bound - builtin_names
                        if not unresolved and (not writes_to_params) and (extra_count <= max_extra_params):
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
    assigned = names_assigned_in_statements(body)
    free_names = used - assigned
    used_from_outer = free_names & plocals
    block_bound = _names_bound_by_block_node(block_node) & free_names
    all_extra = used_from_outer | block_bound
    if len(all_extra) > max_extra_params:
        return None
    extra_params = sorted(all_extra)
    helper_name = f'_extracted_block_{block_node.lineno}'
    return (helper_name, block_node.lineno, line_count, extra_params)

def _block_has_extracted_call(n: ast.AST) -> bool:
    """True if block contains a call to _extracted_block_* (avoids recursion)."""
    for node in ast.walk(n):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id.startswith('_extracted_block_'):
                return True
    return False


def _is_trivial_call_wrapper_body(body: List[ast.stmt]) -> bool:
    """True when body only forwards to another non-builtin call (useless extract).

    ``threshold = float(x)`` is NOT trivial. ``handled = try_review_in_approvals_call(...)`` is.
    Also ``log.write(); log.flush(); return subprocess.Popen(...)`` — thin spawn wrapper.
    """
    builtin_names = set(dir(builtins))
    setup_attrs = {
        "write",
        "flush",
        "close",
        "seek",
        "truncate",
        "update",
        "clear",
        "append",
    }

    def _is_forwarding_call(call: ast.expr) -> bool:
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        if isinstance(func, ast.Name):
            return func.id not in builtin_names
        if isinstance(func, ast.Attribute):
            return True
        return False

    def _is_setup_side_effect(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Attribute) and func.attr in setup_attrs:
                return True
        return False

    def _stmt_is_forwarding(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Expr) and _is_forwarding_call(stmt.value):
            return True
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and _is_forwarding_call(stmt.value)
        ):
            return True
        if isinstance(stmt, ast.AnnAssign) and stmt.value is not None and _is_forwarding_call(stmt.value):
            return True
        if isinstance(stmt, ast.Return) and stmt.value is not None and _is_forwarding_call(stmt.value):
            return True
        return False

    if not body:
        return False
    if len(body) == 1:
        return _stmt_is_forwarding(body[0])
    if len(body) == 2:
        first, second = body
        if (
            isinstance(first, ast.Assign)
            and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name)
            and _is_forwarding_call(first.value)
            and isinstance(second, ast.Return)
            and isinstance(second.value, ast.Name)
            and second.value.id == first.targets[0].id
        ):
            return True
        # ``side_effect_call(); return True`` after rewriting ``flag = True``.
        if (
            isinstance(first, ast.Expr)
            and _is_forwarding_call(first.value)
            and isinstance(second, ast.Return)
            and isinstance(second.value, ast.Constant)
        ):
            return True
    # Setup side-effects then one forwarding call/return (Popen spawn extract).
    if _stmt_is_forwarding(body[-1]) and all(_is_setup_side_effect(s) for s in body[:-1]):
        return True
    return False


def _is_trivial_presentation_body(body: List[ast.stmt]) -> bool:
    """True for f-string / message assembly with no real control structure.

    HITL rejects like ``_extracted_block_1317(trained)`` that only format a status line.
    Simple ``for row in …: lines.append(f"…")`` loops are still presentation.
    """
    if not body:
        return False
    builtin_names = set(dir(builtins))
    allowed_attrs = {
        "get",
        "format",
        "join",
        "strip",
        "replace",
        "lower",
        "upper",
        "append",
        "extend",
    }
    has_stringy = False
    has_mutation = False

    def _leaf_stmts(stmts: List[ast.stmt]) -> bool:
        for part in stmts:
            if isinstance(part, (ast.While, ast.Try, ast.With)):
                return False
            if isinstance(part, ast.For):
                if not _leaf_stmts(list(part.body)):
                    return False
                continue
            if isinstance(part, ast.If):
                if not _leaf_stmts(list(part.body)):
                    return False
                orelse = list(getattr(part, "orelse", None) or [])
                # elif chains are nested If in orelse — allow.
                if not _leaf_stmts(orelse):
                    return False
                continue
            if isinstance(part, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Expr, ast.Pass, ast.Return)):
                continue
            return False
        return True

    for stmt in body:
        if isinstance(stmt, (ast.While, ast.Try, ast.With)):
            return False
        if isinstance(stmt, (ast.If, ast.For)):
            if not _leaf_stmts([stmt]):
                return False

    for node in ast.walk(ast.Module(body=list(body), type_ignores=[])):
        if isinstance(node, ast.JoinedStr):
            has_stringy = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) >= 8:
            # Long literals alone are weak; prefer JoinedStr / format paths.
            pass
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id not in builtin_names:
                return False
            if isinstance(func, ast.Attribute) and func.attr not in allowed_attrs:
                return False
            if isinstance(func, ast.Attribute) and func.attr in {"append", "extend", "join", "format"}:
                # append/join of strings → presentation signal
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    if isinstance(arg, ast.JoinedStr):
                        has_stringy = True
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and len(arg.value) >= 4:
                        has_stringy = True
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            has_mutation = True
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            has_mutation = True
    if has_mutation:
        return False
    return has_stringy


def _if_is_guard_raise(node: ast.If) -> bool:
    """True when If body is a lone Raise (optional elif Raise chain)."""
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Raise):
        return False
    orelse = list(node.orelse or [])
    if not orelse:
        return True
    if len(orelse) == 1 and isinstance(orelse[0], ast.If):
        return _if_is_guard_raise(orelse[0])
    if len(orelse) == 1 and isinstance(orelse[0], ast.Raise):
        return True
    return False


def _is_trivial_guard_body(body: List[ast.stmt]) -> bool:
    """True for validation-only extracts: ``if not x: raise …`` then fetch/return.

    HITL rejects like ``_extracted_block_272(runtime, session_id, tool_results)`` that
    only check params and call ``runtime._session(...)``.
    """
    if not body:
        return False
    has_raise = False
    builtin_names = set(dir(builtins))

    def _is_forwarding_call(call: ast.expr) -> bool:
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        if isinstance(func, ast.Name):
            return func.id not in builtin_names
        if isinstance(func, ast.Attribute):
            return True
        return False

    def _stmt_is_forwarding(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Expr) and _is_forwarding_call(stmt.value):
            return True
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and _is_forwarding_call(stmt.value)
        ):
            return True
        if isinstance(stmt, ast.AnnAssign) and stmt.value is not None and _is_forwarding_call(stmt.value):
            return True
        if isinstance(stmt, ast.Return) and stmt.value is not None and _is_forwarding_call(stmt.value):
            return True
        return False

    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.For, ast.While, ast.Try, ast.With)):
            return False
        if isinstance(stmt, ast.If):
            if not _if_is_guard_raise(stmt):
                return False
            has_raise = True
            continue
        if isinstance(stmt, ast.Raise):
            has_raise = True
            if i != len(body) - 1:
                # bare raise mid-body is odd but still a guard script
                continue
            continue
        if i == len(body) - 1 and _stmt_is_forwarding(stmt):
            continue
        return False
    return has_raise


def _is_copyish_expr(node: ast.expr) -> bool:
    """True for constants, names, and ``obj.get(...)`` — not computed config."""
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, ast.Attribute):
        return _is_copyish_expr(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _is_copyish_expr(node.operand)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "get"
    return False


def _is_trivial_dict_snippet_body(body: List[ast.stmt]) -> bool:
    """True when body only copies constants/.get into one dict (JSON snippet).

    Idle bug-hunt parked ``handle_prove_cycle`` ``if propose: snippet[k]=…``.
    Must NOT match real config like ``kwargs["model"] = … if str(model)…``.
    """
    if not body:
        return False
    dict_names: Set[str] = set()

    def _walk(stmts: List[ast.stmt]) -> bool:
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                if not _walk(list(stmt.body)):
                    return False
                orelse = list(getattr(stmt, "orelse", None) or [])
                if orelse and not _walk(orelse):
                    return False
                continue
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and _is_copyish_expr(stmt.value)
                ):
                    dict_names.add(target.value.id)
                    continue
            return False
        return True

    return _walk(body) and len(dict_names) == 1


def _is_low_value_extract_body(body: List[ast.stmt]) -> bool:
    return (
        _is_trivial_call_wrapper_body(body)
        or _is_trivial_presentation_body(body)
        or _is_trivial_guard_body(body)
        or _is_trivial_dict_snippet_body(body)
    )

def _line_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _dedent_prefixed_block(text: str, indent: str) -> str:
    """Strip a common leading indent from each line (preserve relative indents)."""
    if not text:
        return text
    out: list[str] = []
    for line in text.splitlines(True):
        if indent and line.startswith(indent):
            out.append(line[len(indent) :])
        elif line.strip() == "":
            out.append("\n" if line.endswith("\n") else line)
        else:
            out.append(line.lstrip(" \t"))
    return "".join(out)


def _indent_block(text: str, indent: str = "    ") -> str:
    out: list[str] = []
    for line in text.splitlines(True):
        if line.strip() == "":
            out.append("\n")
        elif line.endswith("\n"):
            out.append(indent + line)
        else:
            out.append(indent + line + "\n")
    return "".join(out)


def _splice_extract_block_source(
    content: str,
    *,
    parent_func: ast.FunctionDef,
    body: List[ast.stmt],
    helper_name: str,
    extra: List[str],
    return_var: Optional[str],
    rewrite_last_assign_to_return: bool,
) -> Optional[str]:
    """Surgical text edit: insert helper + replace block body; preserve file formatting."""
    if not body:
        return None
    first = body[0]
    last = body[-1]
    start = int(getattr(first, "lineno", 0) or 0)
    end = int(getattr(last, "end_lineno", None) or getattr(last, "lineno", 0) or 0)
    if start < 1 or end < start:
        return None
    lines = content.splitlines(keepends=True)
    if end > len(lines):
        return None
    body_indent = _line_indent(lines[start - 1])
    args = ", ".join(extra)
    if return_var:
        call_line = f"{body_indent}{return_var} = {helper_name}({args})\n"
    else:
        call_line = f"{body_indent}{helper_name}({args})\n"

    if rewrite_last_assign_to_return:
        if not isinstance(last, ast.Assign) or not last.targets:
            return None
        last_start = int(getattr(last, "lineno", 0) or 0)
        if last_start < start:
            return None
        prefix = "".join(lines[start - 1 : last_start - 1])
        val_seg = ast.get_source_segment(content, last.value)
        if val_seg is None:
            return None
        body_for_helper = prefix + f"{body_indent}return {val_seg}\n"
    else:
        body_for_helper = "".join(lines[start - 1 : end])
        if return_var:
            body_for_helper = body_for_helper.rstrip("\n") + f"\n{body_indent}return {return_var}\n"

    helper_inner = _dedent_prefixed_block(body_for_helper, body_indent)
    if not helper_inner.strip():
        return None
    helper_src = f"def {helper_name}({args}):\n{_indent_block(helper_inner)}"
    if not helper_src.endswith("\n"):
        helper_src += "\n"
    helper_src += "\n"

    replaced = lines[: start - 1] + [call_line] + lines[end:]
    insert_at = int(parent_func.lineno) - 1
    if insert_at < 0 or insert_at > len(replaced):
        return None
    helper_lines = helper_src.splitlines(keepends=True)
    out_lines = replaced[:insert_at] + helper_lines + replaced[insert_at:]
    result = "".join(out_lines)
    if not result.endswith("\n") and content.endswith("\n"):
        result += "\n"
    try:
        compile(ast.parse(result), "<eurika-extract-splice>", "exec")
    except Exception:
        return None
    return result


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
    candidates: List[Tuple[ast.AST, List[ast.stmt], int, int]] = []

    def collect_blocks(node: ast.AST, depth: int) -> None:
        if isinstance(node, block_types):
            body = getattr(node, 'body', None)
            if body and isinstance(body, list):
                if _block_has_extracted_call(node):
                    pass
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
    if _is_low_value_extract_body(body):
        return None
    block_bound = _names_bound_by_block_node(block_node)
    body_used = _names_used_in_statements(body) - names_assigned_in_statements(body)
    for name in sorted(block_bound & body_used):
        if name not in extra:
            extra.append(name)
    plocals = parent_locals(parent_func)
    # True outer writes: assigned in block AND (used outside block OR already bound in parent).
    # Intermediate temps (a=…; b=a*2; result=b) are not outer just because parent_locals sees them.
    used_outside = _names_loaded_outside(parent_func, block_node)
    pre_existing = parent_param_names(parent_func) | names_assigned_in_excluding(parent_func, block_node)
    loop_locals = _loop_target_names_in_statements(body)
    outer_scope = (used_outside | pre_existing) - block_bound - loop_locals
    if _outer_augassign_names(body, outer_scope):
        # ``n_exp += 1`` etc. cannot safely move without in/out params.
        return None
    assigned_outer = (names_assigned_in_statements(body) & (used_outside | pre_existing)) - block_bound - loop_locals
    return_var: Optional[str] = None
    if body and isinstance(body[-1], ast.Assign):
        last = body[-1]
        if len(last.targets) == 1 and isinstance(last.targets[0], ast.Name):
            out_name = last.targets[0].id
            if (
                out_name in plocals
                and out_name not in block_bound
                and out_name not in loop_locals
            ):
                return_var = out_name
    if return_var is None:
        # e.g. try/except that assigns ``threshold`` — last stmt is Try, not Assign.
        if len(assigned_outer) == 1:
            return_var = next(iter(assigned_outer))
        elif len(assigned_outer) > 1:
            # Multiple outer writes — cannot pack into one return safely.
            return None
    elif len(assigned_outer) > 1:
        # Last-stmt Assign would return one name and drop sibling outer writes.
        return None

    rewrite_last_assign_to_return = False
    if return_var:
        if (
            body
            and isinstance(body[-1], ast.Assign)
            and len(body[-1].targets) == 1
            and isinstance(body[-1].targets[0], ast.Name)
            and body[-1].targets[0].id == return_var
        ):
            rewrite_last_assign_to_return = True
    elif (names_assigned_in_statements(body) & (used_outside | pre_existing)) - block_bound - loop_locals:
        # Would drop outer assignments with a bare call — refuse.
        return None

    spliced = _splice_extract_block_source(
        content,
        parent_func=parent_func,
        body=body,
        helper_name=helper_name,
        extra=extra,
        return_var=return_var,
        rewrite_last_assign_to_return=rewrite_last_assign_to_return,
    )
    if spliced is not None:
        return spliced

    # Fallback: full-module ast.unparse (loses formatting — last resort).
    def replace_body_with_call(node: ast.AST) -> bool:
        if node is block_node:
            call_args: List[ast.expr] = [ast.Name(id=p, ctx=ast.Load()) for p in extra]
            call_expr = ast.Call(ast.Name(id=helper_name, ctx=ast.Load()), call_args, [])
            call: ast.stmt
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
    helper_body: List[ast.stmt] = list(body)
    if return_var:
        if rewrite_last_assign_to_return:
            new_body = list(body[:-1])
            last_stmt = body[-1]
            if isinstance(last_stmt, ast.Assign) and last_stmt.targets:
                new_body.append(ast.Return(last_stmt.value))
            helper_body = new_body
        else:
            helper_body = list(body) + [ast.Return(value=ast.Name(id=return_var, ctx=ast.Load()))]
    args_list = [ast.arg(arg=p) for p in extra]
    extracted = ast.FunctionDef(name=helper_name, args=ast.arguments(posonlyargs=[], args=args_list, vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]), body=helper_body, decorator_list=[], returns=None)
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
    return validate_and_unparse_module(tree)

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
    free_names = names_used_in_node(nested_node) - names_assigned_in(nested_node)
    free_names.discard(nested_node.name)
    plocals = parent_locals(parent_node)
    used_from_parent = free_names & plocals
    module_bound = _module_level_bound_names(tree)
    builtin_names = set(dir(builtins))
    unresolved = free_names - plocals - module_bound - builtin_names
    if unresolved:
        return 'extract_nested_function: nested has unresolved free names'
    if len(used_from_parent) > 3:
        return 'extract_nested_function: nested needs more than 3 parent vars'
    if nested_uses_parent_locals(nested_node, parent_node):
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