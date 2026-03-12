"""Tests for ExperienceStore (ROADMAP §5.7 этап 6)."""

import os
from pathlib import Path

import pytest

from eurika.storage import ExperienceStore, get_statistics, record_outcome


def _isolate_global_store(tmp_path: Path) -> None:
    """Use tmp dir for global store so tests don't see user's ~/.eurika and avoid double-count."""
    os.environ["EURIKA_GLOBAL_MEMORY"] = str(tmp_path / "global")
    (tmp_path / "global").mkdir(parents=True, exist_ok=True)


def _disable_global_store() -> None:
    """Disable global store for tests that need local-only counts."""
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"


def _restore_global_store() -> None:
    """Restore env after test."""
    for key in ("EURIKA_GLOBAL_MEMORY", "EURIKA_DISABLE_GLOBAL_MEMORY"):
        if key in os.environ:
            del os.environ[key]


def test_record_outcome_empty_operations_noop(tmp_path: Path) -> None:
    """record_outcome with empty operations does nothing."""
    _isolate_global_store(tmp_path)
    try:
        record_outcome(tmp_path, [], [], [], True)
        store = ExperienceStore(tmp_path)
        assert store.get_statistics() == {}
    finally:
        _restore_global_store()


def test_record_outcome_and_get_statistics(tmp_path: Path) -> None:
    """record_outcome writes to local store; get_statistics returns aggregates."""
    _disable_global_store()
    try:
        record_outcome(
            tmp_path,
            ["foo.py"],
            [{"kind": "refactor_module", "smell_type": "god_module"}],
            [],
            True,
        )
        stats = get_statistics(tmp_path)
        assert "god_module|refactor_module" in stats
        rec = stats["god_module|refactor_module"]
        assert rec["total"] == 1
        assert rec["success"] == 1
    finally:
        _restore_global_store()


def test_record_outcome_verify_fail(tmp_path: Path) -> None:
    """record_outcome with verify_success=False increments fail."""
    _disable_global_store()
    try:
        record_outcome(
            tmp_path,
            ["a.py"],
            [{"kind": "remove_unused_import", "smell_type": "unused_import"}],
            [],
            False,
        )
        stats = get_statistics(tmp_path)
        key = "unused_import|remove_unused_import"
        assert key in stats
        assert stats[key]["total"] == 1
        assert stats[key]["fail"] == 1
    finally:
        _restore_global_store()


def test_record_outcome_s5_context(tmp_path: Path) -> None:
    """S5: project_size, module_size, context stored in learn event."""
    _disable_global_store()
    try:
        record_outcome(
            tmp_path,
            ["a.py"],
            [{"kind": "refactor_module", "target_file": "a.py"}],
            [],
            True,
            project_size=1000,
            module_size=150,
            context="god_module refactor",
        )
        from eurika.storage.memory import ProjectMemory
        memory = ProjectMemory(tmp_path)
        events = memory.events.recent_events(limit=5, types=("learn",))
        assert len(events) >= 1
        inp = events[0].input or {}
        assert inp.get("project_size") == 1000
        assert inp.get("module_size") == 150
        assert inp.get("context") == "god_module refactor"
    finally:
        _restore_global_store()


def test_experience_store_class(tmp_path: Path) -> None:
    """ExperienceStore.record_outcome and get_statistics work."""
    _disable_global_store()
    try:
        store = ExperienceStore(tmp_path)
        store.record_outcome(
            ["m.py"],
            [{"kind": "refactor_code_smell", "smell_type": "deep_nesting"}],
            [],
            True,
        )
        stats = store.get_statistics()
        assert "deep_nesting|refactor_code_smell" in stats
        filtered = store.get_statistics(action_type="refactor_code_smell")
        assert "deep_nesting|refactor_code_smell" in filtered
        assert len(filtered) == 1
        assert store.get_statistics(action_type="other_kind") == {}
    finally:
        _restore_global_store()
