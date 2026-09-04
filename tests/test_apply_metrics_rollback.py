"""Regression: metrics_worsened must not undo polygon-only / float-noise applies."""

from __future__ import annotations

from eurika.orchestration.apply_stage import (
    _METRICS_WORSEN_EPS,
    polygon_only_modified,
    should_rollback_for_metrics,
)


def test_polygon_only_modified_true_for_drill() -> None:
    assert polygon_only_modified({"modified": ["eurika/polygon/imports_ok.py"]})
    assert polygon_only_modified(
        {"modified": ["./eurika/polygon/a.py", "eurika/polygon/b.py"]}
    )
    assert not polygon_only_modified({"modified": ["eurika/api/chat.py"]})
    assert not polygon_only_modified(
        {"modified": ["eurika/polygon/imports_ok.py", "eurika/api/chat.py"]}
    )
    assert not polygon_only_modified({"modified": []})


def test_should_not_rollback_float_epsilon() -> None:
    report = {"modified": ["eurika/api/chat.py"]}
    before = 0.16049607998610227
    after = 0.16047992510336478
    assert before - after < _METRICS_WORSEN_EPS
    assert should_rollback_for_metrics(report, before, after) is False


def test_should_not_rollback_polygon_even_on_large_drop() -> None:
    report = {"modified": ["eurika/polygon/imports_ok.py"]}
    assert should_rollback_for_metrics(report, 0.5, 0.1) is False


def test_should_rollback_non_polygon_meaningful_drop() -> None:
    report = {"modified": ["eurika/api/chat.py"]}
    assert should_rollback_for_metrics(report, 0.5, 0.4) is True
