import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.smells.detector import ArchSmell
from eurika.smells.health import compute_health


def test_compute_health_basic_levels():
    # No smells, stable trends -> high health.
    summary = {"system": {"modules": 5, "dependencies": 4, "cycles": 0}}
    smells: list[ArchSmell] = []
    trends = {"complexity": "stable", "smells": "stable", "centralization": "stable"}
    h = compute_health(summary, smells, trends)
    assert h["level"] == "high"

    # With smells and bad trends -> lower score and medium/low level.
    smells = [
        ArchSmell(type="god_module", nodes=["a.py"], severity=10.0, description=""),
        ArchSmell(type="bottleneck", nodes=["b.py"], severity=8.0, description=""),
    ]
    trends = {"complexity": "increasing", "smells": "increasing", "centralization": "increasing"}
    h2 = compute_health(summary, smells, trends)
    assert h2["score"] < h["score"]
    assert h2["level"] in {"medium", "low"}

