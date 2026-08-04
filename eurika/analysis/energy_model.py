"""
EnergyModel — Energy = W · MetricVector (ROADMAP §5.7, review 2026 II).

Линейная формула. Веса фиксированы (адаптация — позже).
Минимизация Energy = улучшение архитектуры.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .metric_vector import MetricVector

# Weights: complexity, coupling, cohesion, instability, layering_violations, entropy
# Positive = higher metric → more energy (worse). Negative cohesion = higher cohesion → less energy (better).
DEFAULT_WEIGHTS: Tuple[float, ...] = (0.2, 0.2, -0.2, 0.15, 0.15, 0.1)


@dataclass(frozen=True)
class WeightVector:
    """Fixed 6-dimensional weight vector for EnergyModel."""

    complexity: float
    coupling: float
    cohesion: float  # negative: higher cohesion → lower energy
    instability: float
    layering_violations: float
    entropy: float

    def to_array(self) -> Tuple[float, ...]:
        return (
            self.complexity,
            self.coupling,
            self.cohesion,
            self.instability,
            self.layering_violations,
            self.entropy,
        )

    @classmethod
    def default(cls) -> "WeightVector":
        return cls(
            complexity=DEFAULT_WEIGHTS[0],
            coupling=DEFAULT_WEIGHTS[1],
            cohesion=DEFAULT_WEIGHTS[2],
            instability=DEFAULT_WEIGHTS[3],
            layering_violations=DEFAULT_WEIGHTS[4],
            entropy=DEFAULT_WEIGHTS[5],
        )


class EnergyModel:
    """
    Energy = W · M. Simple linear formula (review 2026 II).

    Lower energy = better architecture. Weights fixed for now.
    """

    def __init__(self, weights: WeightVector | None = None):
        self.weights = weights or WeightVector.default()

    def compute(self, metrics: MetricVector) -> float:
        """Energy = dot(weights, metrics). Lower is better."""
        w = self.weights.to_array()
        m = metrics.to_array()
        return sum(wi * mi for wi, mi in zip(w, m))

    def delta(self, before: MetricVector, after: MetricVector) -> float:
        """ΔEnergy = E_after - E_before. Negative = improvement."""
        return self.compute(after) - self.compute(before)
