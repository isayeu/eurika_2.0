"""
AST-based module split for god_module refactoring.

Given a module and params (imports_from, imported_by from suggest_god_module_split_hint),
extracts a subset of top-level definitions that primarily use one of imports_from
into a new submodule, then updates the original to import from it.
"""
from __future__ import annotations
import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

def _infer_import_stems_from_tree(tree: ast.AST) -> Set[str]:
    """Collect import stems from AST (used when imports_from param is empty)."""
    stems: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                stem = alias.name.split(".")[0]
                if stem and stem != "__init__":
                    stems.add(stem)
        elif isinstance(node, ast.ImportFrom) and node.module:
            stem = node.module.split(".")[-1]
            if stem and stem != "__init__":
                stems.add(stem)
    return stems


def split_module_by_import(file_path: Path, imports_from: List[str], extracted_module_stem: str='_extracted', target_file: Optional[str]=None) -> Optional[Tuple[str, str, str]]:
    """
    Attempt to split a Python module by extracting definitions that use one import.

    imports_from: list of module paths (e.g. from graph edges) — we use the
        stem of each to match ImportFrom/Import nodes (e.g. "remove_import").
    If imports_from is empty, infers stems from the file's own imports (ROADMAP 2.6.4).
    extracted_module_stem: suffix for new file (target_stem + extracted_module_stem + .py).

    Returns:
        (new_file_rel_path, new_file_content, modified_original_content) or None.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    bindings: Dict[str, str] = {}
    _collect_bindings(tree, bindings)
    import_stems: Set[str] = set()
    for p in imports_from:
        stem = Path(p).stem
        if stem and stem != '__init__':
            import_stems.add(stem)
    if not import_stems:
        import_stems = _infer_import_stems_from_tree(tree)
    if not import_stems:
        return None
    defs_with_sources: List[Tuple[ast.FunctionDef | ast.ClassDef, Set[str]]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            used_stems = _used_import_stems(node, bindings)
            defs_with_sources.append((node, used_stems))
    _builtins = {'True', 'False', 'None', 'bool', 'int', 'str', 'list', 'dict', 'set', 'type', 'object'}
    candidates_by_stem: Dict[str, List[ast.FunctionDef | ast.ClassDef]] = {}
    for def_node, used in defs_with_sources:
        relevant = used & import_stems
        others = used - import_stems - _builtins
        if not others and relevant:
            stem = list(relevant)[0] if len(relevant) == 1 else min(relevant)
            candidates_by_stem.setdefault(stem, []).append(def_node)
    if not candidates_by_stem:
        return None
    best_stem = max(candidates_by_stem.keys(), key=lambda s: len(candidates_by_stem[s]))
    to_extract = candidates_by_stem[best_stem]
    if len(to_extract) < 1:
        return None
    used_stems = set()
    for d in to_extract:
        used_stems |= _used_import_stems(d, bindings)
    import_lines = _gather_import_lines(tree, used_stems)
    if not import_lines:
        import_lines = ['"""Extracted from parent module."""']
    extracted_names = [n.name for n in to_extract]
    new_module_content = _build_extracted_module_multi(tree, import_lines, to_extract)
    if target_file:
        t = Path(target_file)
        base = str(t.with_suffix(''))
        new_name = t.stem + extracted_module_stem + '.py'
        new_rel_path = str(t.parent / new_name) if str(t.parent) != '.' else new_name
    else:
        base = file_path.stem
        new_name = base + extracted_module_stem + '.py'
        new_rel_path = new_name
    modified_original = _build_modified_original(tree, to_extract, extracted_names, base, extracted_module_stem)
    return (new_rel_path, new_module_content, modified_original)

def split_module_by_function(
    file_path: Path,
    extracted_module_stem: str = "_extracted",
    target_file: Optional[str] = None,
    min_statements: int = 1,
) -> Optional[Tuple[str, str, str]]:
    """
    Fallback: extract the largest self-contained top-level function to a new module.

    Used when split_module_by_import and split_module_by_class return None.
    Picks the largest function that doesn't reference other top-level defs.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    bindings: Dict[str, str] = {}
    _collect_bindings(tree, bindings)
    top_level_names = {
        n.name
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and (not n.name.startswith("_"))
    }
    candidates: List[ast.FunctionDef] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        stmt_count = len(node.body)
        if stmt_count < min_statements:
            continue
        if _def_references_local_names(node, top_level_names - {node.name}, bindings):
            continue
        candidates.append(node)
    if not candidates:
        return None
    to_extract = max(candidates, key=lambda f: sum(1 for _ in ast.walk(f)))
    used_stems = _used_import_stems(to_extract, bindings)
    import_lines = _gather_import_lines(tree, used_stems)
    if not import_lines:
        import_lines = ['"""Extracted from parent module."""']
    if target_file:
        t = Path(target_file)
        base = str(t.with_suffix(""))
        new_name = t.stem + "_" + to_extract.name.lower() + ".py"
        new_rel_path = str(t.parent / new_name) if str(t.parent) != "." else new_name
    else:
        base = file_path.stem
        new_name = base + "_" + to_extract.name.lower() + ".py"
        new_rel_path = new_name
    new_content_lines = ['"""Extracted from parent module to reduce complexity."""', ""]
    new_content_lines.extend(import_lines)
    new_content_lines.append("")
    new_content_lines.append(ast.unparse(to_extract))
    new_content_lines.append("")
    new_module_content = "\n".join(new_content_lines).rstrip() + "\n"
    modified_original = _build_modified_original(
        tree, [to_extract], [to_extract.name], base, "_" + to_extract.name.lower()
    )
    return (new_rel_path, new_module_content, modified_original)


def split_module_by_class(file_path: Path, extracted_module_stem: str='_extracted', target_file: Optional[str]=None, min_class_size: int=3) -> Optional[Tuple[str, str, str]]:
    """
    Fallback: extract the largest self-contained class to a new module.

    Used when split_module_by_import returns None (no defs use only one import).
    Picks the largest class that doesn't reference other top-level defs from
    the same module. Conservative: only classes with >= min_class_size methods.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    bindings: Dict[str, str] = {}
    _collect_bindings(tree, bindings)
    top_level_names = {n.name for n in ast.iter_child_nodes(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and (not n.name.startswith('_'))}
    candidates: List[ast.ClassDef] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef) or node.name.startswith('__'):
            continue
        method_count = sum((1 for n in ast.iter_child_nodes(node) if isinstance(n, ast.FunctionDef) and (not n.name.startswith('__'))))
        if method_count < min_class_size:
            continue
        if _def_references_local_names(node, top_level_names - {node.name}, bindings):
            continue
        candidates.append(node)
    if not candidates:
        return None
    to_extract = max(candidates, key=lambda c: sum((1 for n in ast.iter_child_nodes(c) if isinstance(n, ast.FunctionDef) and (not n.name.startswith('__')))))
    used_stems = _used_import_stems(to_extract, bindings)
    import_lines = _gather_import_lines(tree, used_stems)
    if not import_lines:
        import_lines = ['"""Extracted from parent module."""']
    if target_file:
        t = Path(target_file)
        base = str(t.with_suffix(''))
        new_name = t.stem + '_' + to_extract.name.lower() + '.py'
        new_rel_path = str(t.parent / new_name) if str(t.parent) != '.' else new_name
    else:
        base = file_path.stem
        new_name = base + '_' + to_extract.name.lower() + '.py'
        new_rel_path = new_name
    new_content_lines = ['"""Extracted from parent module to reduce complexity."""', '']
    new_content_lines.extend(import_lines)
    new_content_lines.append('')
    new_content_lines.append(ast.unparse(to_extract))
    new_content_lines.append('')
    new_module_content = '\n'.join(new_content_lines).rstrip() + '\n'
    modified_original = _build_modified_original(tree, [to_extract], [to_extract.name], base, '_' + to_extract.name.lower())
    return (new_rel_path, new_module_content, modified_original)

def _def_references_local_names(node: ast.FunctionDef | ast.ClassDef, local_names: Set[str], bindings: Dict[str, str]) -> bool:
    """True if node body references any of local_names (other top-level defs in same module)."""
    builtins = {'True', 'False', 'None', 'bool', 'int', 'str', 'list', 'dict', 'set', 'self'}
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            if child.id in local_names and child.id not in builtins:
                return True
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            root = _root_name(child.value)
            if root and root in local_names and (root not in builtins):
                return True
    return False

def _gather_import_lines(tree: ast.AST, stems: Set[str]) -> List[str]:
    """Return import statement strings for the given stems."""
    lines: List[str] = []
    seen: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                stem = alias.name.split('.')[0]
                if stem in stems and stem not in seen:
                    lines.append(ast.unparse(node))
                    seen.add(stem)
        elif isinstance(node, ast.ImportFrom) and node.module:
            stem = node.module.split('.')[-1]
            if stem in stems and stem not in seen:
                lines.append(ast.unparse(node))
                seen.add(stem)
    return lines

def _collect_bindings(tree: ast.AST, out: Dict[str, str]) -> None:
    """Populate out: bound_name -> module_stem (e.g. remove_import_from_file -> remove_import)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                stem = alias.name.split('.')[0]
                out[name] = stem
        elif isinstance(node, ast.ImportFrom) and node.module:
            stem = node.module.split('.')[-1]
            for alias in node.names:
                if alias.name != '*':
                    name = alias.asname or alias.name
                    out[name] = stem

def _used_import_stems(node: ast.FunctionDef | ast.ClassDef, bindings: Dict[str, str]) -> Set[str]:
    """Return set of import stems used in node body (via Name/Attribute load)."""
    used: Set[str] = set()
    builtins = {'True', 'False', 'None', 'bool', 'int', 'str', 'list', 'dict', 'set'}
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
                if alias.name.split('.')[0] == stem:
                    return ast.unparse(node)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split('.')[-1] == stem:
                return ast.unparse(node)
    return None

def _build_extracted_module(tree: ast.AST, import_line: str, defs: List[ast.FunctionDef | ast.ClassDef]) -> str:
    """Build content for the new extracted module (single import line)."""
    return _build_extracted_module_multi(tree, [import_line], defs)


def _build_extracted_module_multi(
    tree: ast.AST, import_lines: List[str], defs: List[ast.FunctionDef | ast.ClassDef]
) -> str:
    """Build content for the new extracted module (multiple import lines)."""
    lines = ['"""Extracted from parent module to reduce complexity."""', ""]
    lines.extend(import_lines)
    lines.append("")
    for d in defs:
        lines.append(ast.unparse(d))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def _build_modified_original(tree: ast.AST, to_remove: List[ast.FunctionDef | ast.ClassDef], extracted_names: List[str], base_name: str, extracted_stem: str) -> str:
    """Remove extracted defs from original and add import from new module."""
    remove_names = {n.name for n in to_remove}
    new_body = [n for n in tree.body if not (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in remove_names)]
    new_tree = ast.Module(body=new_body, type_ignores=[])
    mod_parts = base_name.replace('\\', '/').split('/')
    new_module_name = '.'.join(mod_parts) + extracted_stem
    import_stmt = f"from {new_module_name} import {', '.join(extracted_names)}"
    import_ast = ast.parse(import_stmt).body[0]
    insert_idx = sum((1 for n in new_tree.body if isinstance(n, (ast.Import, ast.ImportFrom))))
    new_tree.body.insert(insert_idx, import_ast)
    return ast.unparse(new_tree) + '\n'