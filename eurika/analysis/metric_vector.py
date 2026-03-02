"""
MetricVector — фиксированная размерность (ROADMAP §5.7, review 2026 II).

Пространство состояний архитектуры. Все компоненты в [0, 1].
Не dict — строгий dataclass для EnergyModel (Energy = W · M).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import TYPE_CHECKING, Any, List, Tuple

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


@dataclass(frozen=True)
class MetricVector:
    """
    Fixed-dimension vector for architecture state (review 2026 II).

    All components in [0, 1]. Higher cohesion = better; higher others = worse.
    """

    complexity: float
    coupling: float
    cohesion: float
    instability: float
    layering_violations: float
    entropy: float

    def to_array(self) -> Tuple[float, ...]:
        """Tuple for dot product with weights (Energy = W · M)."""
        return (
            self.complexity,
            self.coupling,
            self.cohesion,
            self.instability,
            self.layering_violations,
            self.entropy,
        )


def compute_metric_vector(graph: "ProjectGraph", smells: List[Any]) -> MetricVector:
    """
    Compute MetricVector from graph and smells.

    All values in [0, 1]. Higher cohesion = better; higher others = structural debt.
    """
    n = len(graph.nodes)
    if n == 0:
        return MetricVector(
            complexity=0.0,
            coupling=0.0,
            cohesion=0.5,
            instability=0.5,
            layering_violations=0.0,
            entropy=0.0,
        )

    fan = graph.fan_in_out()
    degrees = [fan[node][0] + fan[node][1] for node in graph.nodes]
    total_edges = sum(len(graph.edges.get(node, [])) for node in graph.nodes)
    cycles = graph.find_cycles()

    # Coupling: 0=low, 1=high
    max_degree = max(degrees) if degrees else 0
    max_possible = n * (n - 1) if n > 1 else 1
    coupling = min(1.0, total_edges / max_possible * 10) if max_possible else 0.0
    if max_degree > 0:
        avg_degree = mean(degrees)
        coupling = max(coupling, min(1.0, avg_degree / (max_degree + 1)))

    # Complexity: cycles + degree variance. 0=low, 1=high
    cycle_penalty = min(1.0, len(cycles) * 0.2)
    sigma = pstdev(degrees) if len(degrees) > 1 else 0.0
    degree_spread = min(1.0, sigma / (max_degree + 1)) if max_degree else 0.0
    complexity = min(1.0, cycle_penalty * 0.6 + degree_spread * 0.4)

    # Cohesion: inverse of god-module concentration. High = focused modules
    god_count = sum(1 for s in smells if getattr(s, "type", "") == "god_module")
    bottleneck_count = sum(1 for s in smells if getattr(s, "type", "") == "bottleneck")
    cohesion = max(0.0, 1.0 - (god_count + bottleneck_count) / (n + 1))
    low_fanout = sum(1 for fi, fo in fan.values() if fo <= 2)
    cohesion = (cohesion + low_fanout / (n + 1)) / 2 if n else 0.5

    # Instability: I = fan_out/(fan_in+fan_out) per module; 0=stable, 1=unstable
    instabilities = []
    for node in graph.nodes:
        fi, fo = fan[node]
        total = fi + fo
        instabilities.append(fo / total if total > 0 else 0.0)
    instability = mean(instabilities) if instabilities else 0.5

    # Layering violations: cycles break layer discipline (ROADMAP §5.7)
    layering_violations = min(1.0, len(cycles) * 0.15)

    # Entropy: structural diversity of degrees (normalized)
    sigma_deg = pstdev(degrees) if len(degrees) > 1 else 0.0
    entropy = min(1.0, sigma_deg / (max_degree + 1)) if max_degree else 0.0

    return MetricVector(
        complexity=round(complexity, 4),
        coupling=round(coupling, 4),
        cohesion=round(cohesion, 4),
        instability=round(instability, 4),
        layering_violations=round(layering_violations, 4),
        entropy=round(entropy, 4),
    )
