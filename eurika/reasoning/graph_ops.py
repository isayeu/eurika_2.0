"""
Graph-based operations for patch planning (ROADMAP 2.1 — Граф как инструмент).

Uses ProjectGraph structure to suggest concrete refactoring decisions:
- cyclic_dependency: which edge to break (weakest link heuristic)
- bottleneck: facade candidates (callers that could be grouped)
- god_module: split hints from dependency clusters
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eurika.analysis.graph import ProjectGraph


def resolve_module_for_edge(self_map: Dict[str, Any], src_path: str, dst_path: str) -> Optional[str]:
    """
    Find the module name in deps[src_path] that resolves to dst_path.

    Used to turn (src, dst) file-path edge into the import to remove.

    Returns:
        Module name (e.g. "project_graph") or None if not found.
    """
    modules = self_map.get("modules", [])
    deps = self_map.get("dependencies", {})
    module_to_file: Dict[str, str] = {}
    for m in modules:
        p = Path(m["path"])
        module_to_file[p.stem] = p.as_posix()

    dst_norm = Path(dst_path).as_posix()
    src_deps = deps.get(Path(src_path).as_posix(), deps.get(src_path, []))
    for mod_name in src_deps:
        first = mod_name.split(".")[0]
        resolved = module_to_file.get(first)
        if resolved and Path(resolved).as_posix() == dst_norm:
            return mod_name
    # Fallback: dst path stem (e.g. project_graph.py -> project_graph)
    if Path(dst_path).stem and Path(dst_path).stem != "__init__":
        return Path(dst_path).stem
    return None


def suggest_cycle_break_edge(
    graph: ProjectGraph,
    cycle_nodes: List[str],
) -> Optional[Tuple[str, str]]:
    """
    Suggest one edge (src, dst) in the cycle to break.

    Heuristic: pick the edge with lowest combined fan-in of dst
    (breaking it affects fewer dependents). If tie, pick by edge position.

    Returns:
        (src, dst) where removing import src->dst would break the cycle,
        or None if cycle is empty or not found in graph.
    """
    if not cycle_nodes:
        return None
    fan = graph.fan_in_out()
    cycle_set = set(cycle_nodes)

    # Find edges that are part of this cycle (src, dst both in cycle)
    candidates: List[Tuple[str, str, float]] = []
    for src in cycle_nodes:
        for dst in graph.edges.get(src, []):
            if dst in cycle_set:
                # Score: lower fan_in of dst = prefer breaking this edge
                fi = fan.get(dst, (0, 0))[0]
                score = float(fi)
                candidates.append((src, dst, score))

    if not candidates:
        return None
    # Sort by score ascending (prefer lower fan-in = less impact)
    candidates.sort(key=lambda x: (x[2], x[0]))
    return (candidates[0][0], candidates[0][1])


def suggest_facade_candidates(
    graph: ProjectGraph,
    bottleneck_node: str,
    top_n: int = 5,
) -> List[str]:
    """
    Suggest modules that import the bottleneck (callers).

    For introduce_facade: these are the modules that could use a facade
    instead of importing the bottleneck directly. Returns callers (fan-in sources)
    ordered by their own fan-in (prioritize high-traffic callers for facade).

    Returns:
        List of module paths that depend on bottleneck_node.
    """
    fan = graph.fan_in_out()
    callers: List[Tuple[str, int]] = []
    for src, dsts in graph.edges.items():
        if bottleneck_node in dsts:
            fi, _ = fan.get(src, (0, 0))
            callers.append((src, fi))
    callers.sort(key=lambda x: (-x[1], x[0]))
    return [c[0] for c in callers[:top_n]]


def suggest_god_module_split_hint(
    graph: ProjectGraph,
    god_node: str,
    top_n: int = 5,
) -> Dict[str, Any]:
    """
    Suggest dependency clusters for splitting a god module.

    Returns:
        Dict with:
        - "imports_from": modules that god_node imports (potential extraction targets)
        - "imported_by": modules that import god_node (grouping candidates)
        Both limited to top_n for brevity.
    """
    imports_from = list(graph.edges.get(god_node, []))[:top_n]
    imported_by: List[str] = []
    for src, dsts in graph.edges.items():
        if god_node in dsts:
            imported_by.append(src)
    imported_by = imported_by[:top_n]
    return {
        "imports_from": imports_from,
        "imported_by": imported_by,
    }


def graph_hints_for_smell(
    graph: ProjectGraph,
    smell_type: str,
    nodes: List[str],
) -> List[str]:
    """
    Return concrete, graph-derived hints for a smell.

    Used to enrich patch descriptions with actionable suggestions.
    """
    hints: List[str] = []
    if smell_type == "cyclic_dependency" and nodes:
        edge = suggest_cycle_break_edge(graph, nodes)
        if edge:
            src, dst = edge
            hints.append(f"Break cycle: consider removing or inverting import {src} -> {dst}.")
    if smell_type == "bottleneck" and nodes:
        node = nodes[0]
        callers = suggest_facade_candidates(graph, node, top_n=5)
        if callers:
            hints.append(
                f"Introduce facade for callers: {', '.join(callers[:3])}{'...' if len(callers) > 3 else ''}."
            )
    if smell_type == "god_module" and nodes:
        node = nodes[0]
        info = suggest_god_module_split_hint(graph, node, top_n=5)
        if info.get("imports_from"):
            hints.append(
                f"Extract from imports: {', '.join(info['imports_from'][:3])}."
            )
        if info.get("imported_by"):
            hints.append(
                f"Consider grouping callers: {', '.join(info['imported_by'][:3])}."
            )
    return hints
