"""Tests for operational metrics aggregation (ROADMAP 2.7.8)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_aggregate_operational_metrics_empty(tmp_path: Path) -> None:
    """No events → None."""
    from eurika.storage import aggregate_operational_metrics

    (tmp_path / ".eurika").mkdir(exist_ok=True)
    m = aggregate_operational_metrics(tmp_path, window=10)
    assert m is None


def test_aggregate_operational_metrics_from_events(tmp_path: Path) -> None:
    """Patch events → apply_rate, rollback_rate, median."""
    from eurika.storage import aggregate_operational_metrics
    from eurika.storage.event_engine import event_engine

    (tmp_path / ".eurika").mkdir(exist_ok=True)
    store = event_engine(tmp_path)
    store.append_event(
        "patch",
        {"operations_count": 5},
        {"modified": ["a.py", "b.py"], "verify_success": True, "verify_duration_ms": 1000},
        result=True,
    )
    store.append_event(
        "patch",
        {"operations_count": 3},
        {"modified": [], "verify_success": False, "verify_duration_ms": 500},
        result=False,
    )
    store.append_event(
        "patch",
        {"operations_count": 2},
        {"modified": ["c.py"], "verify_success": True, "verify_duration_ms": 2000},
        result=True,
    )
    m = aggregate_operational_metrics(tmp_path, window=10)
    assert m is not None
    assert m["runs_count"] == 3
    assert m["total_ops"] == 10
    assert m["total_modified"] == 3
    assert m["apply_rate"] == pytest.approx(0.3)
    assert m["rollback_rate"] == pytest.approx(1 / 3, rel=0.01)
    assert m["median_verify_time_ms"] == 1000
