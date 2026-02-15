"""Tests for eurika.storage.events and event_engine (unified Event model)."""
from pathlib import Path
from eurika.storage import ProjectMemory, event_engine
from eurika.storage.events import Event, EventStore, EVENTS_FILE

def test_event_to_dict_roundtrip() -> None:
    """Event serializes to dict and back."""
    e = Event(type='scan', input={'path': '/x'}, output={'files': 10}, result=True)
    d = e.to_dict()
    assert d['type'] == 'scan'
    assert d['input']['path'] == '/x'
    assert d['result'] is True
    e2 = Event.from_dict(d)
    assert e2.type == e.type
    assert e2.result == e.result

def test_event_store_append_and_all(tmp_path: Path) -> None:
    """EventStore appends and returns events."""
    store = EventStore(storage_path=tmp_path / EVENTS_FILE)
    store.append_event('scan', {'path': str(tmp_path)}, {'files': 5}, result=True)
    store.append_event('patch', {'n': 1}, {'modified': ['a.py']}, result=False)
    all_events = store.all()
    assert len(all_events) == 2
    assert all_events[0].type == 'scan'
    assert all_events[1].type == 'patch'
    assert all_events[1].result is False
    assert (tmp_path / EVENTS_FILE).exists()

def test_event_store_by_type(tmp_path: Path) -> None:
    """EventStore.by_type filters correctly."""
    store = EventStore(storage_path=tmp_path / EVENTS_FILE)
    store.append_event('scan', {}, {})
    store.append_event('patch', {}, {})
    store.append_event('scan', {}, {})
    scans = store.by_type('scan')
    assert len(scans) == 2
    assert len(store.by_type('patch')) == 1

def test_project_memory_events(tmp_path: Path) -> None:
    """ProjectMemory.events is EventStore and persists to .eurika/events.json."""
    memory = ProjectMemory(tmp_path)
    memory.events.append_event('scan', {'path': str(tmp_path)}, {'files': 3}, result=True)
    events = memory.events.all()
    assert len(events) == 1
    assert events[0].type == 'scan'
    assert (tmp_path / '.eurika' / 'events.json').exists()


def test_event_engine_entry_point(tmp_path: Path) -> None:
    """event_engine(project_root) returns EventStore; same store as ProjectMemory.events."""
    store = event_engine(tmp_path)
    store.append_event('patch', {'n': 1}, {'modified': ['a.py']}, result=True)
    memory = ProjectMemory(tmp_path)
    assert len(memory.events.all()) == 1
    assert memory.events.all()[0].type == 'patch'
    assert (tmp_path / '.eurika' / 'events.json').exists()


def test_event_to_dict_includes_action(tmp_path: Path) -> None:
    """Event.to_dict includes 'action' (review contract: type, input, action, result, timestamp)."""
    e = Event(type='scan', input={'path': '/x'}, output={'files': 10}, result=True)
    d = e.to_dict()
    assert d.get('action') == d.get('output')
    assert 'type' in d and 'input' in d and 'result' in d and 'timestamp' in d


def test_event_from_dict_accepts_action(tmp_path: Path) -> None:
    """Event.from_dict accepts 'action' as synonym for 'output'."""
    d = {'type': 'learn', 'input': {}, 'action': {'ok': True}, 'result': True, 'timestamp': 1.0}
    e = Event.from_dict(d)
    assert e.output == {'ok': True}


def test_event_store_recent_events(tmp_path: Path) -> None:
    """EventStore.recent_events returns last N events, newest first, with optional type filter."""
    store = EventStore(storage_path=tmp_path / EVENTS_FILE)
    store.append_event("scan", {}, {})
    store.append_event("patch", {"n": 1}, {"modified": ["a.py"]}, result=True)
    store.append_event("learn", {"modules": ["a.py"]}, {}, result=True)
    store.append_event("scan", {}, {})

    recent = store.recent_events(limit=3)
    assert len(recent) == 3
    assert recent[0].type == "scan"  # newest
    assert recent[1].type == "learn"
    assert recent[2].type == "patch"

    patch_learn = store.recent_events(limit=5, types=("patch", "learn"))
    assert len(patch_learn) == 2
    assert patch_learn[0].type == "learn"
    assert patch_learn[1].type == "patch"