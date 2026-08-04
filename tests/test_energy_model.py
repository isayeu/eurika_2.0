"""Tests for eurika.analysis.energy_model (ROADMAP §5.7, review 2026 II)."""

from __future__ import annotations

import pytest

from eurika.analysis.energy_model import DEFAULT_WEIGHTS, EnergyModel, WeightVector
from eurika.analysis.metric_vector import MetricVector


def test_weight_vector_default() -> None:
    w = WeightVector.default()
    assert len(w.to_array()) == 6
    assert w.cohesion < 0


def test_energy_model_compute() -> None:
    model = EnergyModel()
    mv = MetricVector(
        complexity=0.5,
        coupling=0.5,
        cohesion=0.5,
        instability=0.5,
        layering_violations=0.5,
        entropy=0.5,
    )
    e = model.compute(mv)
    assert isinstance(e, float)


def test_energy_model_lower_cohesion_higher_energy() -> None:
    """Higher cohesion (good) → lower energy."""
    model = EnergyModel()
    bad = MetricVector(0.5, 0.5, 0.2, 0.5, 0.5, 0.5)  # low cohesion
    good = MetricVector(0.5, 0.5, 0.9, 0.5, 0.5, 0.5)  # high cohesion
    assert model.compute(good) < model.compute(bad)


def test_energy_model_higher_complexity_higher_energy() -> None:
    """Higher complexity (bad) → higher energy."""
    model = EnergyModel()
    low = MetricVector(0.1, 0.5, 0.5, 0.5, 0.5, 0.5)
    high = MetricVector(0.9, 0.5, 0.5, 0.5, 0.5, 0.5)
    assert model.compute(high) > model.compute(low)


def test_energy_model_delta_negative_improvement() -> None:
    """ΔEnergy < 0 means architecture improved."""
    model = EnergyModel()
    before = MetricVector(0.8, 0.7, 0.3, 0.6, 0.5, 0.4)
    after = MetricVector(0.3, 0.4, 0.8, 0.3, 0.2, 0.2)  # better on all
    delta = model.delta(before, after)
    assert delta < 0


def test_energy_model_custom_weights() -> None:
    w = WeightVector(1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    model = EnergyModel(weights=w)
    mv = MetricVector(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    assert model.compute(mv) == pytest.approx(0.5)


def test_default_weights_length() -> None:
    assert len(DEFAULT_WEIGHTS) == 6


def test_energy_model_with_real_metric_vector() -> None:
    """Integration: compute_metric_vector → EnergyModel.compute."""
    from eurika.analysis.graph import ProjectGraph
    from eurika.analysis.metric_vector import compute_metric_vector

    g = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py"], "b.py": ["c.py"]})
    mv = compute_metric_vector(g, [])
    model = EnergyModel()
    e = model.compute(mv)
    assert isinstance(e, float)
    assert e >= -1.0 and e <= 1.0
