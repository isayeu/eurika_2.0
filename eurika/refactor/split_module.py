"""
AST-based module split for god_module refactoring.

Given a module and params (imports_from, imported_by from suggest_god_module_split_hint),
extracts a subset of top-level definitions that primarily use one of imports_from
into a new submodule, then updates the original to import from it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def split_module_by_import(
    file_path: Path,
    imports_from: List[str],
    extracted_module_stem: str = "_extracted",
    target_file: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """
    Attempt to split a Python module by extracting definitions that use one import.

    imports_from: list of module paths (e.g. from graph edges) — we use the
        stem of each to match ImportFrom/Import nodes (e.g. "remove_import").
    extracted_module_stem: suffix for new file (target_stem + extracted_module_stem + .py).

    Returns:
        (new_file_rel_path, new_file_content, modified_original_content) or None.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None

    # Build binding: name -> import_module_stem (e.g. "remove_import")
    bindings: Dict[str, str] = {}
    _collect_bindings(tree, bindings)

    # Map imports_from paths to stems for matching
    import_stems: Set[str] = set()
    for p in imports_from:
        stem = Path(p).stem
        if stem and stem != "__init__":
            import_stems.add(stem)

    if not import_stems:
        return None

    # For each top-level def, compute which import stems it uses
    defs_with_sources: List[Tuple[ast.FunctionDef | ast.ClassDef, Set[str]]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            used_stems = _used_import_stems(node, bindings)
            defs_with_sources.append((node, used_stems))

    _builtins = {"True", "False", "None", "bool", "int", "str", "list", "dict", "set", "type", "object"}
    # Find definitions that use ONLY one of imports_from (plus builtins)
    candidates_by_stem: Dict[str, List[ast.FunctionDef | ast.ClassDef]] = {}
    for def_node, used in defs_with_sources:
        relevant = used & import_stems
        others = used - import_stems - _builtins
        if len(relevant) == 1 and not others:
            stem = list(relevant)[0]
            candidates_by_stem.setdefault(stem, []).append(def_node)

    if not candidates_by_stem:
        return None

    # Pick the stem with most extractable defs
    best_stem = max(candidates_by_stem.keys(), key=lambda s: len(candidates_by_stem[s]))
    to_extract = candidates_by_stem[best_stem]
    if len(to_extract) < 1:
        return None

    # Find the import line for best_stem
    import_line = _find_import_for_stem(tree, best_stem)
    if not import_line:
        return None

    # Build new module content
    extracted_names = [n.name for n in to_extract]
    new_module_content = _build_extracted_module(tree, import_line, to_extract)

    # New file path (same dir as target)
    if target_file:
        t = Path(target_file)
        base = str(t.with_suffix(""))
        new_name = t.stem + extracted_module_stem + ".py"
        new_rel_path = str(t.parent / new_name) if str(t.parent) != "." else new_name
    else:
        base = file_path.stem
        new_name = base + extracted_module_stem + ".py"
        new_rel_path = new_name

    # Build modified original (remove extracted defs, add import)
    modified_original = _build_modified_original(
        tree, to_extract, extracted_names, base, extracted_module_stem
    )

    return (new_rel_path, new_module_content, modified_original)


def _collect_bindings(tree: ast.AST, out: Dict[str, str]) -> None:
    """Populate out: bound_name -> module_stem (e.g. remove_import_from_file -> remove_import)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                stem = alias.name.split(".")[0]
                out[name] = stem
        elif isinstance(node, ast.ImportFrom) and node.module:
            stem = node.module.split(".")[-1]  # last part
            for alias in node.names:
                if alias.name != "*":
                    name = alias.asname or alias.name
                    out[name] = stem


def _used_import_stems(
    node: ast.FunctionDef | ast.ClassDef,
    bindings: Dict[str, str],
) -> Set[str]:
    """Return set of import stems used in node body (via Name/Attribute load)."""
    used: Set[str] = set()
    builtins = {"True", "False", "None", "bool", "int", "str", "list", "dict", "set"}
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            stem = bindings.get(child.id)
            if stem and child.id not in builtins:
                used.add(stem)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            root = _root_name(child.value)
            if root:
                stem = bindings.get(root)
                if stem:
                    used.add(stem)
    return used


def _root_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return None


def _find_import_for_stem(tree: ast.AST, stem: str) -> Optional[str]:
    """Return the import statement string for the given stem."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == stem:
                    return ast.unparse(node)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[-1] == stem:
                return ast.unparse(node)
    return None


def _build_extracted_module(
    tree: ast.AST,
    import_line: str,
    defs: List[ast.FunctionDef | ast.ClassDef],
) -> str:
    """Build content for the new extracted module."""
    lines = [
        '"""Extracted from parent module to reduce complexity."""',
        "",
        import_line,
        "",
    ]
    for d in defs:
        lines.append(ast.unparse(d))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_modified_original(
    tree: ast.AST,
    to_remove: List[ast.FunctionDef | ast.ClassDef],
    extracted_names: List[str],
    base_name: str,
    extracted_stem: str,
) -> str:
    """Remove extracted defs from original and add import from new module."""
    remove_names = {n.name for n in to_remove}
    new_body = [
        n for n in tree.body
        if not (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in remove_names)
    ]
    new_tree = ast.Module(body=new_body, type_ignores=[])
    # base_name: "patch_apply" or "eurika/refactor/remove_import" -> module path
    mod_parts = base_name.replace("\\", "/").split("/")
    new_module_name = ".".join(mod_parts) + extracted_stem
    import_stmt = f"from {new_module_name} import {', '.join(extracted_names)}"
    import_ast = ast.parse(import_stmt).body[0]
    insert_idx = sum(1 for n in new_tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    new_tree.body.insert(insert_idx, import_ast)
    return ast.unparse(new_tree) + "\n"
