"""
Architecture Scoring Model (ROADMAP v3.0 Stage 2, §5.5).

Computes cohesion, coupling, complexity, modularity from ProjectGraph and smells.
All scores in [0, 1]; higher cohesion/modularity = better, higher coupling/complexity = worse.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

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

    coupling = _compute_coupling(n, total_edges, degrees)
    complexity = _compute_complexity(cycles, degrees)
    cohesion = _compute_cohesion(smells, n, fan)
    modularity = _compute_modularity(graph, n)

    return {"cohesion": cohesion, "coupling": coupling, "complexity": complexity, "modularity": modularity}


def _compute_coupling(n: int, total_edges: int, degrees: List[int]) -> float:
    max_degree = max(degrees) if degrees else 0
    max_possible = n * (n - 1) if n > 1 else 1
    coupling = min(1.0, total_edges / max_possible * 10) if max_possible else 0.0
    if max_degree > 0:
        avg_degree = mean(degrees)
        coupling = max(coupling, min(1.0, avg_degree / (max_degree + 1)))
    return coupling


def _compute_complexity(cycles: List[Any], degrees: List[int]) -> float:
    cycle_penalty = min(1.0, len(cycles) * 0.2)
    sigma = pstdev(degrees) if len(degrees) > 1 else 0.0
    degree_spread = min(1.0, sigma / (max(degrees) + 1)) if max(degrees) else 0.0
    complexity = min(1.0, cycle_penalty * 0.6 + degree_spread * 0.4)
    return complexity


def _compute_cohesion(smells: List[Any], n: int, fan: Dict[Any, Tuple[int, int]]) -> float:
    god_count = sum(1 for s in smells if getattr(s, "type", "") == "god_module")
    bottleneck_count = sum(1 for s in smells if getattr(s, "type", "") == "bottleneck")
    cohesion = max(0.0, 1.0 - (god_count + bottleneck_count) / (n + 1))
    low_fanout = sum(1 for fi, fo in fan.values() if fo <= 2)
    cohesion = (cohesion + low_fanout / (n + 1)) / 2 if n else 0.5
    return cohesion


def _compute_modularity(graph: "ProjectGraph", n: int) -> float:
    layers_dict = graph.layers()
    if not layers_dict or n == 0:
        return 0.5
    max_layer = max(layers_dict.values())
    if max_layer == 0:
        return 0.5
    layer_spread = len(set(layers_dict.values())) / (max_layer + 1)
    modularity = min(1.0, layer_spread)
    return modularity