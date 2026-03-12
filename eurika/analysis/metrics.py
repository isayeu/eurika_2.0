"""
Graph analysis helpers — summary and metrics.

Implementation moved from graph_analysis.py (v0.9 migration).
RV1: blast_radius, top_blast_radius — direct + transitive dependents.
RV2: dependency_density — edges / (nodes*(nodes-1)).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from eurika.analysis.graph import ProjectGraph


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
