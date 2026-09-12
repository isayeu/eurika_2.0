"""Read-only, best-effort static call graph for Python projects.

Only calls that can be resolved to a function defined in the current project
are emitted. Dynamic dispatch, callbacks and external libraries intentionally
remain unresolved: this graph is evidence for inspection, never an apply gate.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Set


_SKIP_DIRS = frozenset({".git", ".venv", "venv", "__pycache__", ".eurika", ".eurika_backups", "node_modules"})


@dataclass(frozen=True)
class CallNode:
    """A statically discovered top-level function or method."""

    id: str
    file: str
    qualname: str
    line: int


@dataclass
class DataFlowGraph:
    """Conservative edges between function parameters, returns and locals."""

    edges: Set[tuple[str, str, str]] = field(default_factory=set)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_format": "<file>:<function>:param|local:<name> or <file>:<function>:return",
            "edges": [
                {"from": source, "to": target, "kind": kind}
                for source, target, kind in sorted(self.edges)
            ],
        }


@dataclass
class CallGraph:
    """Project-local function nodes and resolved caller → callee edges."""

    nodes: Dict[str, CallNode]
    edges: Set[tuple[str, str]]
    parse_errors: list[str]
    data_flow: DataFlowGraph = field(default_factory=DataFlowGraph)

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [
                {"id": n.id, "file": n.file, "qualname": n.qualname, "line": n.line}
                for n in sorted(self.nodes.values(), key=lambda item: item.id)
            ],
            "edges": [
                {"from": source, "to": target}
                for source, target in sorted(self.edges)
            ],
            "parse_errors": sorted(self.parse_errors),
            "data_flow": self.data_flow.to_dict(),
        }


def _python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _module_name(relative: Path) -> str:
    no_suffix = relative.with_suffix("")
    parts = no_suffix.parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_from_module(current_module: str, level: int, module: str | None) -> str:
    """Resolve an ``ImportFrom`` module name without importing project code."""
    if level <= 0:
        return module or ""
    package = current_module.split(".")[:-1]
    parents = max(level - 1, 0)
    if parents:
        package = package[:-parents]
    prefix = ".".join(package)
    suffix = module or ""
    return ".".join(part for part in (prefix, suffix) if part)


def _function_nodes(relative: Path, tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[item.name] = item
        elif isinstance(item, ast.ClassDef):
            for member in item.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[f"{item.name}.{member.name}"] = member
    return result


class _CallsInFunction(ast.NodeVisitor):
    def __init__(self, root: ast.AST) -> None:
        self._root = root
        self.calls: list[ast.Call] = []
        self.assignments: list[tuple[ast.Call, list[str]]] = []
        self.returns: list[ast.expr] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Lambdas have no stable project-level node, so do not attribute calls.
        return

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if names:
                self.assignments.append((node.value, names))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Call) and isinstance(node.target, ast.Name):
            self.assignments.append((node.value, [node.target.id]))
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self.returns.append(node.value)
        self.generic_visit(node)


def build_call_graph(project_root: str | Path) -> CallGraph:
    """Build a conservative call graph without executing or importing project code."""
    root = Path(project_root).resolve()
    parsed: dict[str, ast.Module] = {}
    modules: dict[str, str] = {}
    errors: list[str] = []
    for path in sorted(_python_files(root)):
        relative = path.relative_to(root)
        rel = relative.as_posix()
        try:
            parsed[rel] = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"{rel}: {exc.__class__.__name__}")
            continue
        module = _module_name(relative)
        if module:
            modules[module] = rel

    nodes: dict[str, CallNode] = {}
    definitions: dict[str, dict[str, str]] = {}
    for rel, tree in parsed.items():
        per_file: dict[str, str] = {}
        for qualname, node in _function_nodes(Path(rel), tree).items():
            node_id = f"{rel}:{qualname}"
            nodes[node_id] = CallNode(node_id, rel, qualname, int(getattr(node, "lineno", 0)))
            per_file[qualname] = node_id
        definitions[rel] = per_file

    function_definitions = _function_definitions(parsed)
    edges: set[tuple[str, str]] = set()
    data_flow = DataFlowGraph()
    for rel, tree in parsed.items():
        current_module = _module_name(Path(rel))
        module_aliases, symbol_aliases = _import_aliases(tree, current_module, modules)
        for qualname, function in _function_nodes(Path(rel), tree).items():
            caller = definitions[rel].get(qualname)
            if not caller:
                continue
            class_name = qualname.split(".", 1)[0] if "." in qualname else None
            visitor = _CallsInFunction(function)
            visitor.visit(function)
            for call in visitor.calls:
                callee = _resolve_call(
                    call.func, rel, definitions, module_aliases, symbol_aliases, class_name
                )
                if callee:
                    edges.add((caller, callee))
            _add_data_flow_edges(
                visitor,
                caller,
                function,
                rel,
                definitions,
                module_aliases,
                symbol_aliases,
                class_name,
                function_definitions,
                data_flow,
            )
    return CallGraph(nodes=nodes, edges=edges, parse_errors=errors, data_flow=data_flow)


def _function_definitions(parsed: Dict[str, ast.Module]) -> Dict[str, Dict[str, ast.AST]]:
    return {rel: _function_nodes(Path(rel), tree) for rel, tree in parsed.items()}


def _parameter_names(function: ast.AST, qualname: str) -> list[str]:
    if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    names = [arg.arg for arg in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)]
    if "." in qualname and names and names[0] in {"self", "cls"}:
        return names[1:]
    return names


def _flow_node(function_id: str, name: str, parameters: set[str]) -> str:
    scope = "param" if name in parameters else "local"
    return f"{function_id}:{scope}:{name}"


def _add_data_flow_edges(
    visitor: _CallsInFunction,
    caller: str,
    function: ast.AST,
    source_file: str,
    definitions: Dict[str, Dict[str, str]],
    module_aliases: Dict[str, str],
    symbol_aliases: Dict[str, tuple[str, str]],
    class_name: str | None,
    function_definitions: Dict[str, Dict[str, ast.AST]],
    data_flow: DataFlowGraph,
) -> None:
    """Add only direct Name-based value flow around resolved local calls."""
    caller_qualname = caller.split(":", 1)[1]
    caller_params = set(_parameter_names(function, caller_qualname))
    calls: dict[int, str] = {}
    for call in visitor.calls:
        callee = _resolve_call(call.func, source_file, definitions, module_aliases, symbol_aliases, class_name)
        if not callee:
            continue
        calls[id(call)] = callee
        callee_file, callee_qualname = callee.split(":", 1)
        callee_def = function_definitions.get(callee_file, {}).get(callee_qualname)
        params = _parameter_names(callee_def, callee_qualname) if callee_def else []
        for index, argument in enumerate(call.args):
            if index >= len(params) or not isinstance(argument, ast.Name):
                continue
            data_flow.edges.add(
                (_flow_node(caller, argument.id, caller_params), f"{callee}:param:{params[index]}", "argument")
            )
        for keyword in call.keywords:
            if keyword.arg in params and isinstance(keyword.value, ast.Name):
                data_flow.edges.add(
                    (_flow_node(caller, keyword.value.id, caller_params), f"{callee}:param:{keyword.arg}", "argument")
                )
    for call, targets in visitor.assignments:
        callee = calls.get(id(call))
        if callee:
            for target in targets:
                data_flow.edges.add((f"{callee}:return", _flow_node(caller, target, caller_params), "assignment"))
    for value in visitor.returns:
        if isinstance(value, ast.Name):
            data_flow.edges.add((_flow_node(caller, value.id, caller_params), f"{caller}:return", "return"))
        elif isinstance(value, ast.Call) and (callee := calls.get(id(value))):
            data_flow.edges.add((f"{callee}:return", f"{caller}:return", "return"))


def _import_aliases(
    tree: ast.Module, current_module: str, modules: Dict[str, str]
) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    module_aliases: dict[str, str] = {}
    symbol_aliases: dict[str, tuple[str, str]] = {}
    for item in tree.body:
        if isinstance(item, ast.Import):
            for alias in item.names:
                if alias.name in modules:
                    module_aliases[alias.asname or alias.name.split(".")[0]] = modules[alias.name]
        elif isinstance(item, ast.ImportFrom):
            source_module = _resolve_from_module(current_module, item.level, item.module)
            source_file = modules.get(source_module)
            if not source_file:
                continue
            for alias in item.names:
                if alias.name != "*":
                    symbol_aliases[alias.asname or alias.name] = (source_file, alias.name)
    return module_aliases, symbol_aliases


def _resolve_call(
    target: ast.expr,
    source_file: str,
    definitions: Dict[str, Dict[str, str]],
    module_aliases: Dict[str, str],
    symbol_aliases: Dict[str, tuple[str, str]],
    class_name: str | None,
) -> str | None:
    if isinstance(target, ast.Name):
        local = definitions.get(source_file, {}).get(target.id)
        if local:
            return local
        imported = symbol_aliases.get(target.id)
        if imported:
            return definitions.get(imported[0], {}).get(imported[1])
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        owner = target.value.id
        if owner == "self" and class_name:
            return definitions.get(source_file, {}).get(f"{class_name}.{target.attr}")
        imported_file = module_aliases.get(owner)
        if imported_file:
            return definitions.get(imported_file, {}).get(target.attr)
    return None


__all__ = ["CallGraph", "CallNode", "build_call_graph"]
