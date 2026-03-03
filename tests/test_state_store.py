"""Tests for StateStore (ROADMAP §5.8 Storage 3 layers)."""

from pathlib import Path

import pytest

from eurika.storage import (
    has_checkpoint,
    load_checkpoint,
    save_checkpoint,
    snapshot_from_checkpoint,
)


def test_save_checkpoint_missing_self_map(tmp_path: Path) -> None:
    """save_checkpoint returns False when self_map.json missing."""
    assert save_checkpoint(tmp_path, "test") is False
    assert has_checkpoint(tmp_path, "test") is False


def test_save_and_load_checkpoint(tmp_path: Path) -> None:
    """save_checkpoint copies self_map; load_checkpoint returns dict."""
    self_map = {"modules": [{"path": "a.py"}], "dependencies": {}}
    (tmp_path / "self_map.json").write_text('{"modules":[{"path":"a.py"}],"dependencies":{}}')
    assert save_checkpoint(tmp_path, "v1") is True
    assert has_checkpoint(tmp_path, "v1") is True
    loaded = load_checkpoint(tmp_path, "v1")
    assert loaded is not None
    assert loaded.get("modules") == [{"path": "a.py"}]


def test_load_checkpoint_missing(tmp_path: Path) -> None:
    """load_checkpoint returns None when checkpoint missing."""
    assert load_checkpoint(tmp_path, "nonexistent") is None
    assert has_checkpoint(tmp_path, "nonexistent") is False


def test_snapshot_from_checkpoint_missing(tmp_path: Path) -> None:
    """snapshot_from_checkpoint returns None when checkpoint missing."""
    assert snapshot_from_checkpoint(tmp_path, "nonexistent") is None


def test_snapshot_from_checkpoint_builds_unified(tmp_path: Path) -> None:
    """snapshot_from_checkpoint returns planner.models.ArchitectureSnapshot."""
    from eurika.reasoning.planner.models import ArchitectureSnapshot

    content = '''{"modules":[{"path":"foo/bar.py"}],"dependencies":{"foo.bar":[]}}'''
    (tmp_path / "self_map.json").write_text(content)
    assert save_checkpoint(tmp_path, "latest") is True
    snap = snapshot_from_checkpoint(tmp_path, "latest")
    assert snap is not None
    assert isinstance(snap, ArchitectureSnapshot)
    assert snap.graph is not None
    assert snap.metrics is not None
