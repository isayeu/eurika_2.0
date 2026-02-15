"""Tests for eurika.storage.ProjectMemory facade."""
from pathlib import Path

import pytest

from eurika.storage import ProjectMemory
from eurika.storage.paths import LEGACY_FILES, storage_path

def test_project_memory_feedback(tmp_path: Path) -> None:
    """ProjectMemory(path).feedback is appendable and readable (view over events)."""
    memory = ProjectMemory(tmp_path)
    memory.feedback.append(project_root=tmp_path, action='explain_risk', outcome='accepted', target='foo.py')
    records = memory.feedback.all()
    assert len(records) == 1
    assert records[0].action == 'explain_risk'
    assert records[0].outcome == 'accepted'
    assert (tmp_path / '.eurika' / 'events.json').exists()
    assert len(memory.events.by_type('feedback')) == 1

def test_project_memory_learning(tmp_path: Path) -> None:
    """ProjectMemory(path).learning is appendable and aggregatable (view over events)."""
    memory = ProjectMemory(tmp_path)
    memory.learning.append(project_root=tmp_path, modules=['a.py'], operations=[{'kind': 'refactor_module', 'smell_type': 'god_module'}], risks=[], verify_success=True)
    by_kind = memory.learning.aggregate_by_action_kind()
    assert 'refactor_module' in by_kind
    assert (tmp_path / '.eurika' / 'events.json').exists()
    assert len(memory.events.by_type('learn')) == 1

def test_project_memory_observations(tmp_path: Path) -> None:
    """ProjectMemory(path).observations records and snapshots."""
    memory = ProjectMemory(tmp_path)
    memory.observations.record_observation('scan', {'modules': 5})
    snap = memory.observations.snapshot()
    assert len(snap) == 1
    assert snap[0].trigger == 'scan'
    assert (tmp_path / '.eurika' / 'observations.json').exists()

def test_project_memory_history(tmp_path: Path) -> None:
    """ProjectMemory(path).history exposes ArchitectureHistory API."""
    memory = ProjectMemory(tmp_path)
    trend = memory.history.trend(window=5)
    assert isinstance(trend, dict)
    report = memory.history.evolution_report(window=5)
    assert isinstance(report, str)


@pytest.mark.parametrize("store_name", ["feedback", "learning", "observations", "events"])
def test_migration_from_legacy_path(tmp_path: Path, store_name: str) -> None:
    """Legacy file in project root is migrated; feedback/learning become events."""
    legacy = tmp_path / LEGACY_FILES[store_name]
    legacy.parent.mkdir(parents=True, exist_ok=True)
    # Use valid legacy format so store can merge/overwrite correctly
    if store_name == "feedback":
        legacy.write_text('{"feedback": [{"timestamp": 1, "project_root": "", "action": "old", "outcome": "ok"}]}', encoding="utf-8")
    elif store_name == "learning":
        legacy.write_text('{"learning": [{"timestamp": 1, "project_root": "", "modules": [], "operations": [], "risks": [], "verify_success": True}]}', encoding="utf-8")
    elif store_name == "observations":
        legacy.write_text('{"records": [{"trigger": "scan", "observation": {"old": 1}, "timestamp": 1}]}', encoding="utf-8")
    else:
        legacy.write_text('{"events": [{"type": "scan", "input": {}, "output": {}, "result": True, "timestamp": 1}]}', encoding="utf-8")

    memory = ProjectMemory(tmp_path)
    consolidated = storage_path(tmp_path, store_name)
    events_path = tmp_path / ".eurika" / "events.json"

    if store_name == "feedback":
        memory.feedback.append(project_root=tmp_path, action="new", outcome="y")
        assert len(memory.feedback.all()) >= 1
        # feedback is now in events (3.2.2); legacy migrated and removed
        assert events_path.exists()
        assert len(memory.events.by_type("feedback")) >= 1
    elif store_name == "learning":
        memory.learning.append(tmp_path, ["a.py"], [{"kind": "x"}], [], True)
        assert "x" in memory.learning.aggregate_by_action_kind()
        # learning is now in events (3.2.2); legacy migrated and removed
        assert events_path.exists()
        assert len(memory.events.by_type("learn")) >= 1
    elif store_name == "observations":
        memory.observations.record_observation("scan", {"n": 1})
        assert len(memory.observations.snapshot()) >= 1
        assert consolidated.exists()
    else:
        memory.events.append_event("scan", {}, {}, result=True)
        assert len(memory.events.all()) >= 1
        assert consolidated.exists()