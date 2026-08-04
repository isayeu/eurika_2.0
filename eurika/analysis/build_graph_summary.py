"""
Build graph, smells, summary from self_map.json (R2 consolidation).

Extracted from architecture_pipeline to break core↔architecture_pipeline cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from eurika.analysis.self_map import build_graph_from_self_map, load_self_map
from eurika.smells.detector import ArchSmell, detect_architecture_smells
from eurika.smells.rules import build_summary

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def build_graph_and_summary_from_self_map(
    self_map_path: Path,
) -> tuple["ProjectGraph", List[ArchSmell], Dict[str, Any]]:
    """Build graph, smells, summary from a self_map.json file."""
    _ = load_self_map(self_map_path)
    graph = build_graph_from_self_map(self_map_path)
    smells = detect_architecture_smells(graph)
    summary = build_summary(graph, smells)
    return (graph, smells, summary)


def build_graph_and_summary(path: Path) -> tuple["ProjectGraph", List[ArchSmell], Dict[str, Any]]:
    """Build graph, smells, summary for project root (self_map at path/self_map.json)."""
    self_map_path = path / "self_map.json"
    return build_graph_and_summary_from_self_map(self_map_path)
