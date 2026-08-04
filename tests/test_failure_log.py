"""Tests for failure log / get_recent_failures (Review III самокоррекция)."""

from pathlib import Path

import pytest

from eurika.storage import ProjectMemory, get_recent_failures


def test_get_recent_failures_empty(tmp_path: Path) -> None:
    """When no learn events, returns empty list."""
    assert get_recent_failures(tmp_path) == []


def test_get_recent_failures_extracts_from_learn_events(tmp_path: Path) -> None:
    """Extract (target_file, kind, failure_reason) from failed learn events."""
    mem = ProjectMemory(tmp_path)
    mem.events.append_event(
        type="learn",
        input={
            "project_root": str(tmp_path),
            "modules": ["a.py"],
            "operations": [
                {"target_file": "a.py", "kind": "split_module"},
                {"target_file": "b.py", "kind": "extract_class"},
            ],
            "risks": [],
        },
        output={"failure_reason": "metrics_worsened"},
        result=False,
    )
    failures = get_recent_failures(tmp_path, limit=5)
    assert len(failures) >= 2
    assert ("a.py", "split_module", "metrics_worsened") in failures
    assert ("b.py", "extract_class", "metrics_worsened") in failures


def test_get_recent_failures_skips_success_events(tmp_path: Path) -> None:
    """Successful learn events are ignored."""
    mem = ProjectMemory(tmp_path)
    mem.events.append_event(
        type="learn",
        input={"operations": [{"target_file": "x.py", "kind": "refactor_module"}]},
        output={},
        result=True,
    )
    assert get_recent_failures(tmp_path) == []


def test_failure_log_artifact(tmp_path: Path) -> None:
    """record_outcome with failure_reason writes to EventLog; get_recent_failures reads from it (single source)."""
    from eurika.storage import record_outcome

    record_outcome(
        tmp_path,
        modules=["a.py"],
        operations=[
            {"target_file": "a.py", "kind": "split_module"},
            {"target_file": "b.py", "kind": "extract_class"},
        ],
        risks=[],
        verify_success=False,
        failure_reason="metrics_worsened",
    )
    failures = get_recent_failures(tmp_path, limit=5)
    assert len(failures) >= 2
    targets = set(failures)
    assert ("a.py", "split_module", "metrics_worsened") in targets
    assert ("b.py", "extract_class", "metrics_worsened") in targets


def test_get_recent_failures_from_learn_events(tmp_path: Path) -> None:
    """get_recent_failures reads from EventLog (single source of truth)."""
    from eurika.storage import record_outcome

    record_outcome(
        tmp_path,
        modules=["x.py"],
        operations=[{"target_file": "x.py", "kind": "refactor_module"}],
        risks=[],
        verify_success=False,
        failure_reason="verify_failed",
    )
    failures = get_recent_failures(tmp_path, limit=5)
    assert ("x.py", "refactor_module", "verify_failed") in failures


def test_sort_deprioritizes_recent_failures() -> None:
    """sort_and_reindex_by_learning puts recent-failure ops last (Review III)."""
    from patch_plan import PatchOperation

    from eurika.reasoning.planner.filter_policy import sort_and_reindex_by_learning

    ops = [
        PatchOperation("a.py", "split_module", "desc1", "diff1", smell_type="god_module"),
        PatchOperation("b.py", "extract_class", "desc2", "diff2", smell_type="god_module"),
        PatchOperation("c.py", "split_module", "desc3", "diff3", smell_type="hub"),
    ]
    recent_failures = [
        ("b.py", "extract_class", "metrics_worsened"),
    ]
    result = sort_and_reindex_by_learning(
        ops, None, recent_failures=recent_failures
    )
    # b.py|extract_class should be last (deprioritized)
    assert result[-1].target_file == "b.py" and result[-1].kind == "extract_class"
