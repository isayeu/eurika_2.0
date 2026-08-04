"""
World model — re-exports для целевой структуры v3.x (TARGET_V3_STRUCTURE §4, R6, P7).

Алиас над eurika.analysis.metric_vector и energy_model. Без перемещения файлов.
Импорт: from eurika.world_model import MetricVector, EnergyModel, WeightVector
"""

from __future__ import annotations

from eurika.analysis.energy_model import (
    DEFAULT_WEIGHTS,
    EnergyModel,
    WeightVector,
)
from eurika.analysis.metric_vector import MetricVector

__all__ = [
    "DEFAULT_WEIGHTS",
    "EnergyModel",
    "MetricVector",
    "WeightVector",
]
