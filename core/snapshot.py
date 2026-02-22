"""Core architecture snapshot model.

This module defines ArchitectureSnapshot, a central in-memory
representation of the current architectural state of a project.

v0.5 skeleton: used by core.pipeline and gradually by higher-level
modules (history, diff, reporting).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from project_graph_api import ProjectGraph


@dataclass
class ArchitectureSnapshot:
    """Single architecture snapshot for a project.

    This is intentionally minimal for v0.5: it only captures what we
    already compute today via the v0.1 pipeline, but in a single
    structured object.
    """

    root: Path
    graph: ProjectGraph
    smells: List[Any]
    summary: Dict[str, object]
    history: Optional[Dict[str, object]] = None
    diff: Optional[Dict[str, object]] = None

