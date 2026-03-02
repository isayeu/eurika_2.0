"""
Architecture Scoring Model (ROADMAP v3.0 Stage 2, §5.5).

Computes cohesion, coupling, complexity, modularity from ProjectGraph and smells.
All scores in [0, 1]; higher cohesion/modularity = better, higher coupling/complexity = worse.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def compute_architecture_scores(
    graph: "ProjectGraph",
    smells: List[Any],
) -> Dict[str, float]:
    """
    Compute architecture scoring dimensions.

    Returns:
        Dict with keys: cohesion, coupling, complexity, modularity.
        Each in [0, 1]. Higher cohesion/modularity = better architecture.
        Higher coupling/complexity = worse (structural debt).
    """
    n = len(graph.nodes)
    if n == 0:
        return {"cohesion": 0.5, "coupling": 0.0, "complexity": 0.0, "modularity": 0.5}

    fan = graph.fan_in_out()
    degrees = [fan[node][0] + fan[node][1] for node in graph.nodes]
    total_edges = sum(len(graph.edges.get(node, [])) for node in graph.nodes)
    cycles = graph.find_cycles()

    # Coupling: edges / (n * max_out) or degree concentration. 0=low, 1=high.
    max_degree = max(degrees) if degrees else 0
    max_possible = n * (n - 1) if n > 1 else 1
    coupling = min(1.0, total_edges / max_possible * 10) if max_possible else 0.0
    if max_degree > 0:
        avg_degree = mean(degrees)
        coupling = max(coupling, min(1.0, avg_degree / (max_degree + 1)))

    # Complexity: cycles + degree variance. 0=low, 1=high.
    cycle_penalty = min(1.0, len(cycles) * 0.2)
    sigma = pstdev(degrees) if len(degrees) > 1 else 0.0
    degree_spread = min(1.0, sigma / (max_degree + 1)) if max_degree else 0.0
    complexity = min(1.0, cycle_penalty * 0.6 + degree_spread * 0.4)

    # Cohesion: inverse of god-module concentration. High = modules are focused.
    god_count = sum(1 for s in smells if getattr(s, "type", "") == "god_module")
    bottleneck_count = sum(1 for s in smells if getattr(s, "type", "") == "bottleneck")
    cohesion = max(0.0, 1.0 - (god_count + bottleneck_count) / (n + 1))
    low_fanout = sum(1 for fi, fo in fan.values() if fo <= 2)
    cohesion = (cohesion + low_fanout / (n + 1)) / 2 if n else 0.5

    # Modularity: layer compliance, few cycles. High = good separation.
    layers_dict = graph.layers()
    max_layer = max(layers_dict.values()) if layers_dict else 0
    layer_spread = max_layer / (n + 1) if n else 0
    cycle_ok = max(0.0, 1.0 - len(cycles) * 0.15)
    modularity = min(1.0, (layer_spread * 0.3 + cycle_ok * 0.7))

    return {
        "cohesion": round(cohesion, 4),
        "coupling": round(coupling, 4),
        "complexity": round(complexity, 4),
        "modularity": round(modularity, 4),
    }
