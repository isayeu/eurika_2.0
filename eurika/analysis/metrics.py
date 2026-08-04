"""
Graph analysis helpers — summary and metrics.

Implementation moved from graph_analysis.py (v0.9 migration).
RV1: blast_radius, top_blast_radius — direct + transitive dependents.
RV2: dependency_density — edges / (nodes*(nodes-1)).
RV10: propagation_depth, fragility_zone, fragility_heatmap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from eurika.analysis.graph import ProjectGraph

# RV10: thresholds for green/yellow/red (blast_radius)
FRAGILITY_GREEN_MAX = 9
FRAGILITY_YELLOW_MAX = 29


def propagation_depth(graph: ProjectGraph, module: str) -> int:
    """
    RV10: Max depth of dependent chain.

    When module M changes, impact propagates: direct dependents (depth 1),
    their dependents (depth 2), etc. Returns max depth.
    """
    module_norm = Path(module).as_posix()
    if module_norm not in graph.nodes:
        return 0
    rev = graph._reverse_edges()
    depths: Dict[str, int] = {module_norm: 0}
    queue: List[str] = [module_norm]
    max_depth = 0
    while queue:
        n = queue.pop(0)
        d = depths[n]
        for src in rev.get(n, []):
            if src not in depths:
                depths[src] = d + 1
                max_depth = max(max_depth, d + 1)
                queue.append(src)
    return max_depth


def fragility_zone(blast_radius: int) -> str:
    """RV10: green/yellow/red by blast_radius thresholds."""
    if blast_radius <= FRAGILITY_GREEN_MAX:
        return "green"
    if blast_radius <= FRAGILITY_YELLOW_MAX:
        return "yellow"
    return "red"


def fragility_heatmap(
    graph: ProjectGraph, n: int = 15
) -> List[Tuple[str, int, int, str]]:
    """
    RV10: Top N modules by blast_radius with propagation_depth and zone.

    Returns [(module, blast_radius, propagation_depth, zone), ...] sorted by br desc.
    zone: green|yellow|red.
    """
    pairs: List[Tuple[str, int, int, str]] = []
    for node in graph.nodes:
        br = graph.blast_radius(node)
        depth = propagation_depth(graph, node)
        zone = fragility_zone(br)
        pairs.append((node, br, depth, zone))
    pairs.sort(key=lambda x: -x[1])
    return pairs[:n]


def dependency_density(graph: ProjectGraph) -> float:
    """
    RV2: edges / (nodes * (nodes - 1)).

    Ratio of actual edges to max possible in a directed graph. 0 = sparse, 1 = fully connected.
    Returns 0.0 for n < 2.
    """
    n = len(graph.nodes)
    if n < 2:
        return 0.0
    edges = sum(len(v) for v in graph.edges.values())
    max_edges = n * (n - 1)
    return round(edges / max_edges, 4) if max_edges > 0 else 0.0


def top_blast_radius(graph: ProjectGraph, n: int = 10) -> List[Tuple[str, int]]:
    """
    Top N modules by blast radius (RV1).

    blast_radius(module) = |direct + transitive dependents|.
    Returns [(module, count), ...] sorted descending by count.
    """
    pairs: List[Tuple[str, int]] = []
    for node in graph.nodes:
        br = graph.blast_radius(node)
        pairs.append((node, br))
    pairs.sort(key=lambda x: -x[1])
    return pairs[:n]


def summarize_graph(graph: ProjectGraph) -> Dict:
    """
    Build a summary dict for a ProjectGraph.

    Shape matches the previous ProjectGraph.summary() output:
      {
        "nodes": int,
        "edges": int,
        "cycles_count": int,
        "cycles": list[list[str]],
        "metrics": { name: {fan_in, fan_out, layer}, ... }
      }
    """
    cycles = graph.find_cycles()
    metrics = graph.metrics()
    top_blast = top_blast_radius(graph, n=10)
    edges_count = sum(len(v) for v in graph.edges.values())
    return {
        "nodes": len(graph.nodes),
        "edges": edges_count,
        "dependency_density": dependency_density(graph),
        "cycles_count": len(cycles),
        "cycles": cycles,
        "metrics": {
            name: {
                "fan_in": m.fan_in,
                "fan_out": m.fan_out,
                "layer": m.layer,
            }
            for name, m in metrics.items()
        },
        "top_blast_radius": [(m, c) for m, c in top_blast],
        "fragility_heatmap": [
            {"module": m, "blast_radius": br, "propagation_depth": depth, "zone": zone}
            for m, br, depth, zone in fragility_heatmap(graph, n=15)
        ],
    }


def blast_radius_for_project(root: Path) -> List[Tuple[str, int]]:
    """Load self_map, build graph, return top_blast_radius (RV1)."""
    self_map_path = Path(root).resolve() / "self_map.json"
    if not self_map_path.exists():
        return []
    try:
        import json

        data = json.loads(self_map_path.read_text(encoding="utf-8"))
        graph = ProjectGraph.from_self_map(data)
        return top_blast_radius(graph, n=10)
    except Exception:
        return []
