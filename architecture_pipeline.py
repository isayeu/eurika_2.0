"""
Architecture pipeline helpers.

Encapsulates the v0.1 architecture-awareness pipeline:
- build graph from self_map;
- detect smells;
- compute summary;
- compute recommendations;
- append to history and render evolution report.

Used by:
- runtime_scan.run_scan (core scan scenario)
- CLI helpers for arch-summary / arch-history / arch-diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from eurika.smells.rules import build_recommendations
from eurika.evolution.diff import diff_to_text
from eurika.smells.detector import ArchSmell, detect_architecture_smells
from eurika.smells.rules import compute_health, health_summary
from eurika.storage import ProjectMemory
from eurika.smells.rules import build_summary, summary_to_text
from eurika.analysis.graph import NodeMetrics, ProjectGraph
from eurika.analysis.scanner import semantic_summary
from eurika.analysis.self_map import build_graph_from_self_map, load_self_map
from eurika.analysis.topology import central_modules_for_topology, topology_summary


def run_architecture_pipeline(path: Path) -> None:
    """
    Full architecture-awareness pipeline for a given project root.

    Prints:
    - Architecture Smells (top 5)
    - Architecture Summary (text)
    - Architecture Recommendations (top 10)
    - Architecture Evolution Analysis (history.evolution_report)
    """
    graph, smells, summary = _build_graph_and_summary(path)

    _print_smells(smells)

    print("\n" + summary_to_text(summary))

    # Semantic architecture view (heuristic roles + layer violations)
    print("\n" + semantic_summary(graph))

    # System topology view (heuristic clusters around central modules)
    centers = central_modules_for_topology(graph)
    if centers:
        print("\n" + topology_summary(graph, centers))

    recs = build_recommendations(graph, smells)
    if recs:
        print("\nARCHITECTURE RECOMMENDATIONS\n")
        for i, r in enumerate(recs[:10], start=1):
            print(f"{i}. {r}")

    memory = ProjectMemory(path)
    history = memory.history
    history.append(graph, smells, summary)
    trends = history.trend(window=5)
    print("\n" + history.evolution_report(window=5))

    # Architecture health score (high-level index)
    health = compute_health(summary, smells, trends)
    print("\n" + health_summary(health))


def print_arch_summary(path: Path) -> int:
    """Print only architecture summary for the current project state."""
    from core.pipeline import run_full_analysis

    snapshot = run_full_analysis(path, update_artifacts=False)
    print(summary_to_text(snapshot.summary))
    return 0


def print_arch_history(path: Path, window: int = 5) -> int:
    """Print evolution report based on architecture history."""
    memory = ProjectMemory(path)
    print(memory.history.evolution_report(window=window))
    return 0


def print_arch_diff(old_self_map: Path, new_self_map: Path) -> int:
    """Print architecture diff between two self_map snapshots."""
    from core.pipeline import build_snapshot_from_self_map
    from eurika.evolution.diff import diff_architecture_snapshots, diff_to_text

    old = build_snapshot_from_self_map(old_self_map)
    new = build_snapshot_from_self_map(new_self_map)
    diff = diff_architecture_snapshots(old, new)
    print(diff_to_text(diff))
    return 0


def _build_graph_and_summary(path: Path) -> tuple[ProjectGraph, List[ArchSmell], Dict]:
    """Load self_map, build graph, detect smells and compute summary."""
    self_map_path = path / "self_map.json"
    return _build_graph_and_summary_from_self_map(self_map_path)


def _build_graph_and_summary_from_self_map(self_map_path: Path) -> tuple[ProjectGraph, List[ArchSmell], Dict]:
    """Build graph, smells, summary from a self_map.json file (exact path)."""
    _ = load_self_map(self_map_path)
    graph = build_graph_from_self_map(self_map_path)
    smells = detect_architecture_smells(graph)
    summary = build_summary(graph, smells)
    return graph, smells, summary


def _print_smells(smells: List[ArchSmell]) -> None:
    from eurika.smells.detector import get_remediation_hint, severity_to_level

    if not smells:
        return
    print("\nArchitecture Smells:")
    for s in smells[:5]:
        where = ", ".join(s.nodes[:3])
        level = severity_to_level(s.severity)
        print(f"  [{s.type}] ({level}) severity={s.severity:.2f} in {where} — {s.description}")
        print(f"  → {get_remediation_hint(s.type)}")
    if len(smells) > 5:
        print(f"  ... and {len(smells) - 5} more")
