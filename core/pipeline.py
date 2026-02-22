"""Core orchestration pipeline for Eurika (v0.5 skeleton).

The goal of this module is to provide a single entrypoint for
"architecture analysis" over a project root, returning an
ArchitectureSnapshot instead of printing directly.

Over time, CLI and higher layers should call this module instead of
wiring runtime_scan / architecture_* modules manually.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from eurika.storage import ProjectMemory
from architecture_pipeline import _build_graph_and_summary, _build_graph_and_summary_from_self_map
from eurika.core.snapshot import ArchitectureSnapshot

def run_full_analysis(path: Path, *, history_window: int=5, update_artifacts: bool=True) -> ArchitectureSnapshot:
    """Run the full architecture-awareness pipeline and return a snapshot.

    v0.5 skeleton implementation:
    - when update_artifacts=True: ensures self_map.json is up to date, appends to history;
    - when update_artifacts=False: reads existing artifacts only (read-only mode);
    - builds graph, smells, summary using existing helpers;
    - attaches trend info and evolution report to snapshot.
    """
    root = Path(path).resolve()
    if update_artifacts and not (root / "self_map.json").exists():
        raise FileNotFoundError(
            "self_map.json not found. Run scan first (or call run_full_analysis(..., update_artifacts=False))."
        )
    graph, smells, summary = _build_graph_and_summary(root)
    memory = ProjectMemory(root)
    history = memory.history
    if update_artifacts:
        history.append(graph, smells, summary)
    trends = history.trend(window=history_window)
    regressions = history.detect_regressions(window=history_window)
    evolution_report_text = history.evolution_report(window=history_window)
    history_info: Dict[str, Any] = {'trends': trends, 'regressions': regressions, 'evolution_report': evolution_report_text}
    return ArchitectureSnapshot(root=root, graph=graph, smells=smells, summary=summary, history=history_info, diff=None)

def build_snapshot_from_self_map(self_map_path: Path) -> ArchitectureSnapshot:
    """Build ArchitectureSnapshot from an existing self_map.json file (read-only).

    Used for arch-diff and rescan comparison. Does not update history or write artifacts.
    root is set to the parent directory of the self_map file.
    """
    path = Path(self_map_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f'self_map not found: {path}')
    root = path.parent
    graph, smells, summary = _build_graph_and_summary_from_self_map(path)
    return ArchitectureSnapshot(root=root, graph=graph, smells=smells, summary=summary, history=None, diff=None)