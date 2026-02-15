"""
Consolidated storage paths (ROADMAP 3.2.1).

All memory artifacts live under project_root/.eurika/ with unified naming.
"""

from __future__ import annotations

import shutil
from pathlib import Path

STORAGE_DIR = ".eurika"

# Consolidated filenames under .eurika/
FILES = {
    "events": "events.json",
    "learning": "learning.json",
    "feedback": "feedback.json",
    "observations": "observations.json",
    "history": "history.json",
}

# Legacy filenames in project root (for migration)
LEGACY_FILES = {
    "events": "eurika_events.json",
    "learning": "architecture_learning.json",
    "feedback": "architecture_feedback.json",
    "observations": "eurika_observations.json",
    "history": "architecture_history.json",
}


def storage_path(root: Path, name: str) -> Path:
    """Return consolidated path for a store: root/.eurika/<filename>."""
    root = Path(root).resolve()
    return root / STORAGE_DIR / FILES[name]


def ensure_storage_dir(root: Path) -> None:
    """Create .eurika/ if it does not exist. Call before first write."""
    (Path(root).resolve() / STORAGE_DIR).mkdir(parents=True, exist_ok=True)


def migrate_if_needed(root: Path, name: str) -> None:
    """
    If consolidated path does not exist but legacy path does, copy legacy -> consolidated.
    Ensures .eurika/ directory exists.
    """
    root = Path(root).resolve()
    new_path = storage_path(root, name)
    legacy_path = root / LEGACY_FILES[name]
    if not new_path.exists() and legacy_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, new_path)
