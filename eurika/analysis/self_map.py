"""Self-map I/O exposed through package-level analysis API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .graph import ProjectGraph


def load_self_map(path: Path) -> Dict[str, Any]:
    """Load self_map.json from the given path."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_graph_from_self_map(path: Path) -> ProjectGraph:
    """Convenience helper: load self_map and build a ProjectGraph."""
    return ProjectGraph.from_self_map(load_self_map(path))


__all__ = ["load_self_map", "build_graph_from_self_map"]
