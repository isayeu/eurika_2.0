"""
Graph-based operations for patch planning (ROADMAP 2.1, 3.1 — Граф как инструмент).

Uses ProjectGraph structure to suggest concrete refactoring decisions:
- refactor_kind_for_smells: smell_type → refactor_kind (ROADMAP 3.1.2)
- priority_from_graph: ordered list of modules for refactoring (degree, severity, fan-in/out)
- cyclic_dependency: which edge to break (weakest link heuristic)
- bottleneck: facade candidates (callers that could be grouped)
- god_module: split hints from dependency clusters
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eurika.analysis.graph import ProjectGraph


# ROADMAP 3.1.2 — Canonical smell_type → refactor_kind mapping.
# Used by architecture_planner to trigger operations in patch_plan.
SMELL_TYPE_TO_REFACTOR_KIND: Dict[str, str] = {
    "god_module": "split_module",
    "hub": "split_module",
    "bottleneck": "introduce_facade",
    "cyclic_dependency": "break_cycle",
}


def centrality_from_graph(graph: ProjectGraph, top_n: int = 10) -> Dict[str, Any]:
    """
    Compute centrality metrics from graph (ROADMAP 3.1.3).

    Returns:
        {max_degree, top_by_degree: [(node, degree), ...]}
    """
    fan = graph.fan_in_out()
    degrees = [(n, fi + fo) for n, (fi, fo) in fan.items()]
    degrees.sort(key=lambda x: -x[1])
    max_d = max((d for _, d in degrees), default=0)
    return {
        "max_degree": max_d,
        "top_by_degree": degrees[:top_n],
    }


def metrics_from_graph(
    graph: ProjectGraph,
    smells: List[Any],
    trends: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Compute health/risk and centrality from graph (ROADMAP 3.1.3).

    Graph is the single source; no duplication with other metric paths.
    Returns dict with: score, risk_score, level, factors, centrality.
    """
    from eurika.smells.rules import compute_health

    trends = trends or {}
    health = compute_health({}, smells, trends)
    centrality = centrality_from_graph(graph)
    return {
        **health,
        "risk_score": health["score"],
        "centrality": centrality,
    }


def refactor_kind_for_smells(smell_types: List[str]) -> str:
    """
    Map smell types to refactor kind (ROADMAP 3.1.2).

    Priority: god_module > bottleneck > hub > cyclic_dependency.
    Returns first match or "refactor_module" as fallback.
    """
    for st in ("god_module", "bottleneck", "hub", "cyclic_dependency"):
        if st in smell_types:
            return SMELL_TYPE_TO_REFACTOR_KIND[st]
    return "refactor_module"


def targets_from_graph(
    graph: ProjectGraph,
    smells: List[Any],
    summary_risks: Optional[List[str]] = None,
    top_n: int = 8,
) -> List[Dict[str, Any]]:
    """
    Build explicit targets (target_file, kind) from graph structure (ROADMAP 3.1.4).

    Uses graph.nodes and graph.edges: only nodes present in the graph,
    kind derived from smells, ordering from priority_from_graph.
    Planner uses this to initiate operations from graph structure.
    """
    priorities = priority_from_graph(graph, smells, summary_risks, top_n)
    smells_by_node: Dict[str, List[str]] = {}
    for s in smells:
        for node in s.nodes:
            smells_by_node.setdefault(node, []).append(s.type)
    graph_nodes = graph.nodes
    targets: List[Dict[str, Any]] = []
    for p in priorities:
        name = p.get("name") or ""
        if not name or name not in graph_nodes:
            continue
        reasons = p.get("reasons") or []
        smell_types = smells_by_node.get(name, [])
        kind = refactor_kind_for_smells(smell_types)
        targets.append({"name": name, "kind": kind, "reasons": reasons})
    return targets


def priority_from_graph(
    graph: ProjectGraph,
    smells: List[Any],
    summary_risks: Optional[List[str]] = None,
    top_n: int = 8,
) -> List[Dict[str, Any]]:
    """
    Return ordered list of modules for refactoring (ROADMAP 3.1.1).

    Combines severity (from smells), graph structure (degree, fan-in, fan-out),
    and summary risks. Higher degree modules that appear in smells are prioritized
    (more impactful to fix). Hub/bottleneck get extra weight.

    Returns:
        List of {"name": node_path, "reasons": [smell_type, ...]} sorted by priority.
    """
    fan = graph.fan_in_out()
    scores: Dict[str, float] = {}
    reasons: Dict[str, List[str]] = {}

    for s in smells:
        for node in s.nodes:
            severity = float(getattr(s, "severity", 0) or 0)
            scores[node] = scores.get(node, 0.0) + severity
            reasons.setdefault(node, []).append(s.type)

    if summary_risks:
        for risk in summary_risks:
            if "@ " in risk:
                _, rest = risk.split("@ ", 1)
                target = rest.split(" ", 1)[0]
                scores[target] = scores.get(target, 0.0) + 1.0
                if "mentioned_in_summary_risks" not in (reasons.get(target) or []):
                    reasons.setdefault(target, []).append("mentioned_in_summary_risks")

    for node in list(scores.keys()):
        fi, fo = fan.get(node, (0, 0))
        degree = fi + fo
        smell_types = reasons.get(node, [])
        degree_bonus = degree * 0.1
        if "god_module" in smell_types or "hub" in smell_types:
            degree_bonus += fo * 0.2
        if "bottleneck" in smell_types:
            degree_bonus += fi * 0.2
        scores[node] = scores[node] + degree_bonus

    ordered = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
    return [
        {"name": name, "reasons": reasons.get(name, [])}
        for name, _ in ordered
    ]


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


# TODO (eurika): refactor long_function 'priority_from_graph' — consider extracting helper
