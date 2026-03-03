"""
StateStore — dumb persistence for architecture snapshots (ROADMAP §5.8, review Storage 3 layers).

Save/load snapshot checkpoints. Uses self_map format as storage format; no business logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import STORAGE_DIR, ensure_storage_dir

STATE_DIR = "state"
DEFAULT_LABEL = "latest"


def _state_dir(root: Path) -> Path:
    """Return .eurika/state/ for the project."""
    return Path(root).resolve() / STORAGE_DIR / STATE_DIR


def _checkpoint_path(root: Path, label: str) -> Path:
    """Return path for a named checkpoint: .eurika/state/{label}.json."""
    return _state_dir(root) / f"{label}.json"


def save_checkpoint(project_root: Path, label: str = DEFAULT_LABEL) -> bool:
    """
    Save current self_map as a named checkpoint.

    Copies project_root/self_map.json to .eurika/state/{label}.json.
    Returns True if saved, False if self_map.json missing.
    """
    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return False
    state_dir = _state_dir(root)
    ensure_storage_dir(root)
    state_dir.mkdir(exist_ok=True)
    target = _checkpoint_path(root, label)
    target.write_text(self_map_path.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def load_checkpoint(project_root: Path, label: str = DEFAULT_LABEL) -> dict[str, Any] | None:
    """
    Load checkpoint as raw self_map dict.

    Returns None if checkpoint missing. Dumb load — no snapshot construction.
    """
    path = _checkpoint_path(Path(project_root).resolve(), label)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def has_checkpoint(project_root: Path, label: str = DEFAULT_LABEL) -> bool:
    """Check if checkpoint exists."""
    return _checkpoint_path(Path(project_root).resolve(), label).exists()


def snapshot_from_checkpoint(
    project_root: Path,
    label: str = DEFAULT_LABEL,
) -> Any | None:
    """
    Load checkpoint and build planner.models.ArchitectureSnapshot.

    Returns None if checkpoint missing or build fails. Bridge for consumers that need
    unified ArchitectureSnapshot (not raw self_map).
    """
    path = _checkpoint_path(Path(project_root).resolve(), label)
    if not path.exists():
        return None
    try:
        from eurika.core.pipeline import build_snapshot_from_self_map
        from eurika.reasoning.planner.models import ArchitectureSnapshot

        core_snap = build_snapshot_from_self_map(path)
        return ArchitectureSnapshot.from_core_snapshot(core_snap)
    except Exception:
        return None


__all__ = [
    "save_checkpoint",
    "load_checkpoint",
    "has_checkpoint",
    "snapshot_from_checkpoint",
]
