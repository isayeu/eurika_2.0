"""
Graph analysis helpers — summary and metrics.

Implementation moved from graph_analysis.py (v0.9 migration).
"""

from __future__ import annotations

from typing import Dict

from eurika.analysis.graph import ProjectGraph


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
    return {
        "nodes": len(graph.nodes),
        "edges": sum(len(v) for v in graph.edges.values()),
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
    }
