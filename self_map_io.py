from __future__ import annotations

"""
Self-map IO helpers.

Thin layer responsible for:
- reading self_map.json from disk;
- building ProjectGraph from a self_map path.

Keeps file-system concerns separate from ProjectGraph model.
"""

import json
from pathlib import Path
from typing import Dict

from project_graph import ProjectGraph


def load_self_map(path: Path) -> Dict:
    """Load self_map.json from the given path."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_graph_from_self_map(path: Path) -> ProjectGraph:
    """Convenience helper: load self_map and build a ProjectGraph."""
    return ProjectGraph.from_self_map(load_self_map(path))

