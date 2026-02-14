"""
AST-based Extract Class refactoring.

Extracts a subset of methods from a class into a new class (in a new file).
Conservative: only extracts methods that do not use self (except as receiver).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Tuple


def extract_class(
    file_path: Path,
    target_class: str,
    methods_to_extract: List[str],
    extracted_class_suffix: str = "Extracted",
    target_file: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """
    Extract methods from target_class into a new class in a new file.

    Only extracts methods that don't reference self.attr (conservative).
    methods_to_extract: list of method names.

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

    # Find the target class
    target_cls: Optional[ast.ClassDef] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == target_class:
            target_cls = node
            break
    if not target_cls:
        return None

    # Find methods that exist and don't use self
    to_extract: List[ast.FunctionDef] = []
    for m in methods_to_extract:
        for node in ast.iter_child_nodes(target_cls):
            if isinstance(node, ast.FunctionDef) and node.name == m:
                if not _uses_self_attributes(node):
                    to_extract.append(node)
                break

    if not to_extract:
        return None

    # Build new class content
    new_class_name = target_class + extracted_class_suffix
    new_content = _build_extracted_class_module(tree, new_class_name, to_extract)

    # New file path
    if target_file:
        t = Path(target_file)
        new_name = t.stem + "_" + new_class_name.lower() + ".py"
        new_rel_path = str(t.parent / new_name) if str(t.parent) != "." else new_name
    else:
        new_name = file_path.stem + "_" + new_class_name.lower() + ".py"
        new_rel_path = new_name

    # Build modified original
    modified = _build_modified_original(tree, target_cls, to_extract, new_class_name, target_file, file_path)

    return (new_rel_path, new_content, modified)


def _uses_self_attributes(node: ast.FunctionDef) -> bool:
    """True if method body accesses self.attr (excluding self as param)."""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            if isinstance(child.value, ast.Name) and child.value.id == "self":
                return True
    return False


def _build_extracted_class_module(
    tree: ast.AST,
    new_class_name: str,
    methods: List[ast.FunctionDef],
) -> str:
    """Build new module with extracted class (static methods)."""
    # Convert to static: remove self from args
    static_methods = []
    for m in methods:
        new_args = [a for a in m.args.args if getattr(a, "arg", a) != "self"]
        new_node = ast.FunctionDef(
            name=m.name,
            args=ast.arguments(posonlyargs=[], args=new_args, kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=m.body,
            decorator_list=[ast.Name(id="staticmethod", ctx=ast.Load())],
        )
        ast.fix_missing_locations(new_node)
        static_methods.append(ast.unparse(new_node))

    lines = [
        '"""Extracted from parent class to reduce complexity."""',
        "",
        f"class {new_class_name}:",
        '    """Extracted methods (static)."""',
        "",
    ]
    for sm in static_methods:
        for line in sm.split("\n"):
            lines.append("    " + line if line.strip() else "")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_modified_original(
    tree: ast.AST,
    target_cls: ast.ClassDef,
    to_remove: List[ast.FunctionDef],
    new_class_name: str,
    target_file: Optional[str],
    file_path: Path,
) -> str:
    """Remove extracted methods and add delegation + import."""
    remove_names = {m.name for m in to_remove}
    new_class_body = [
        n for n in target_cls.body
        if not (isinstance(n, ast.FunctionDef) and n.name in remove_names)
    ]

    # Add import and delegation stubs
    if target_file:
        base = str(Path(target_file).with_suffix("")).replace("/", ".").replace("\\", ".")
    else:
        base = file_path.stem
    new_module_path = base + "_" + new_class_name.lower()
    import_stmt = f"from {new_module_path} import {new_class_name}"

    # Add delegation methods
    for m in to_remove:
        args = m.args
        self_arg = args.args[0] if args.args else None
        rest_args = [a for a in args.args[1:]] if args.args else []
        arg_names = [getattr(a, "arg", "args") for a in rest_args]
        call_args = ", ".join(arg_names)
        deleg_body = ast.parse(f"return {new_class_name}.{m.name}({call_args})").body[0]
        deleg = ast.FunctionDef(
            name=m.name,
            args=args,
            body=[deleg_body],
            decorator_list=[],
        )
        new_class_body.append(deleg)

    new_cls = ast.ClassDef(
        name=target_cls.name,
        bases=target_cls.bases,
        keywords=target_cls.keywords,
        body=new_class_body,
        decorator_list=target_cls.decorator_list,
    )

    # Rebuild module: replace target_cls with new_cls, add import
    new_body = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == target_cls.name:
            new_body.append(new_cls)
        else:
            new_body.append(node)
    imp = ast.parse(import_stmt).body[0]
    insert_idx = sum(1 for n in new_body if isinstance(n, (ast.Import, ast.ImportFrom)))
    new_body.insert(insert_idx, imp)

    new_tree = ast.Module(body=new_body, type_ignores=[])
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree) + "\n"
