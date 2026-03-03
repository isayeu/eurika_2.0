"""
Hints provider: graph + OSS hints; LLM optional (review §2).

Separates hint-building from LLM. LLM called only when llm_hints_fn provided.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from eurika.reasoning.planner.heuristics import diff_hints_for

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph
    from eurika.smells.detector import ArchSmell


def _sanitize_split_params(
    project_root: str, target_file: str, split_params: Dict[str, Any]
) -> Dict[str, Any]:
    """Drop stale graph-driven imports_from when they don't map to file imports."""
    imports_from = split_params.get("imports_from") or []
    if not imports_from:
        return split_params
    stems_in_file = _import_stems_in_file(Path(project_root) / target_file)
    if not stems_in_file:
        return split_params
    hinted_stems = {Path(str(p)).stem for p in imports_from if str(p).strip()}
    file_path = Path(project_root) / target_file
    if hinted_stems and hinted_stems.isdisjoint(stems_in_file):
        adjusted = dict(split_params)
        adjusted["imports_from"] = []
        return adjusted
    if hinted_stems and not _has_split_candidates_for_hinted_stems(file_path, hinted_stems):
        adjusted = dict(split_params)
        adjusted["imports_from"] = []
        return adjusted
    return split_params


def _import_stems_in_file(file_path: Path) -> set[str]:
    """Collect import stems present in a file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()
    stems: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                stems.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            stems.add(node.module.split(".")[-1])
    return stems


def _collect_import_bindings(tree: ast.AST) -> Dict[str, str]:
    """Map bound symbol -> import stem for import usage analysis."""
    out: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                out[name] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            stem = node.module.split(".")[-1]
            for alias in node.names:
                if alias.name != "*":
                    out[alias.asname or alias.name] = stem
    return out


def _root_name(node: Any) -> Optional[str]:
    import ast

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return None


def _used_import_stems_in_def(node: ast.AST, bindings: Dict[str, str]) -> set[str]:
    used: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            stem = bindings.get(child.id)
            if stem:
                used.add(stem)
        elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            root = _root_name(child.value)
            if root and root in bindings:
                used.add(bindings[root])
    return used


def _has_split_candidates_for_hinted_stems(file_path: Path, hinted_stems: set[str]) -> bool:
    """Planner-side preflight: does hinted import set produce any clean split candidate?"""
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False
    bindings = _collect_import_bindings(tree)
    builtins_ = {"True", "False", "None", "bool", "int", "str", "list", "dict", "set", "self"}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        used = _used_import_stems_in_def(node, bindings)
        relevant = used & hinted_stems
        others = used - hinted_stems - builtins_
        if relevant and not others:
            return True
    return False


def build_hints_and_params(
    project_root: str,
    smell_type: str,
    action_kind: str,
    node_smells: List[Any],
    name: str,
    *,
    graph: Optional["ProjectGraph"] = None,
    oss_patterns: Optional[Dict[str, Any]] = None,
    llm_hints_fn: Optional[
        Callable[[str, str, str, Dict[str, Any], str], List[str]]
    ] = None,
) -> tuple[List[str], Optional[Dict[str, Any]]]:
    """
    Build diff hints and optional params (review §2: LLM injectable).

    llm_hints_fn(smell_type, name, project_root, graph_context) -> List[str].
    When None, LLM is not called.
    """
    hints = list(diff_hints_for(smell_type, action_kind))
    oss = oss_patterns or {}
    entries = oss.get(smell_type, [])
    if isinstance(entries, list):
        for e in entries[:3]:
            if isinstance(e, dict):
                proj = e.get("project", "?")
                mod = e.get("module", "?")
                hint = e.get("hint", "")
                if hint:
                    h = f"OSS ({proj}): {mod} — {hint}"
                    if h not in hints:
                        hints.append(h)
    split_params: Optional[Dict[str, Any]] = None
    if not graph:
        return (hints, split_params)
    from eurika.reasoning.graph_ops import (
        graph_hints_for_smell,
        suggest_facade_candidates,
        suggest_god_module_split_hint,
    )

    for smell in node_smells:
        graph_hints = graph_hints_for_smell(graph, smell.type, smell.nodes)
        for graph_hint in graph_hints:
            if graph_hint and graph_hint not in hints:
                hints.append(graph_hint)
    if action_kind == "split_module":
        info = suggest_god_module_split_hint(graph, name, top_n=5)
        split_params = {
            "imports_from": info.get("imports_from", []),
            "imported_by": info.get("imported_by", []),
        }
        split_params = _sanitize_split_params(project_root, name, split_params)
        if llm_hints_fn:
            llm_hints = llm_hints_fn(smell_type, name, project_root, info)
            for h in llm_hints:
                if h and h not in hints:
                    hints.append(h)
    elif action_kind == "introduce_facade":
        callers = suggest_facade_candidates(graph, name, top_n=5)
        split_params = {"callers": callers} if callers else None
        if llm_hints_fn:
            llm_hints = llm_hints_fn(smell_type, name, project_root, {"callers": callers or []})
            for h in llm_hints:
                if h and h not in hints:
                    hints.append(h)
    return (hints, split_params)


def default_llm_hints_fn(
    smell_type: str, name: str, project_root: str, graph_context: Dict[str, Any]
) -> List[str]:
    """Default LLM hints: calls Ollama. Returns [] on failure."""
    try:
        from eurika.reasoning.planner.llm_adapter import ask_ollama_split_hints

        return ask_ollama_split_hints(
            smell_type, name, graph_context, project_root=project_root
        )
    except Exception:
        return []
