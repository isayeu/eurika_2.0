"""Tests for priority decay (Review III decay v1.1)."""

from pathlib import Path

import pytest

from eurika.reasoning.priority_decay import apply_decay


def _kind_fn(node: str) -> str:
    return "split_module" if "god" in node else "refactor_module"


def test_apply_decay_no_project_root() -> None:
    """apply_decay is no-op when project_root is None."""
    scores = {"a.py": 10.0, "b.py": 5.0}
    reasons = {"a.py": ["god_module"], "b.py": ["hub"]}
    apply_decay(scores, reasons, _kind_fn, None)
    assert scores["a.py"] == 10.0
    assert scores["b.py"] == 5.0


def test_apply_decay_reduces_score_for_recent_failures(tmp_path: Path) -> None:
    """Targets with failures in EventLog get penalty."""
    from eurika.polygon.decay_polygon import inject_failures

    inject_failures(tmp_path, "a.py", "split_module", 2, failure_reason="metrics_worsened")
    scores = {"a.py": 10.0, "b.py": 8.0}
    reasons = {"a.py": ["god_module"], "b.py": ["hub"]}
    apply_decay(scores, reasons, lambda n: "split_module" if n == "a.py" else "refactor_module", tmp_path)
    assert scores["a.py"] < scores["b.py"]
    assert scores["b.py"] == 8.0


def test_apply_decay_archive_after_n_failures(tmp_path: Path) -> None:
    """Targets with 5+ failures get heavy deprioritization."""
    from eurika.polygon.decay_polygon import inject_failures

    inject_failures(tmp_path, "stuck.py", "extract_class", 6)
    scores = {"stuck.py": 10.0, "fresh.py": 5.0}
    reasons = {"stuck.py": ["god_module"], "fresh.py": ["hub"]}
    apply_decay(scores, reasons, lambda n: "extract_class" if n == "stuck.py" else "refactor_module", tmp_path)
    assert scores["stuck.py"] < 2.0
    assert scores["fresh.py"] == 5.0
