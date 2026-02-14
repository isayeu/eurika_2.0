"""JSON API for future UI (ROADMAP §2.3).

Thin layer over eurika.*: returns JSON-serializable dicts for summary, history, diff.
Use json.dumps() on the return value to serve over HTTP or save to file.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List


def _to_json_safe(obj: Any) -> Any:
    """Convert objects to JSON-serializable form: tuple->list, Path->str."""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return obj


def get_summary(project_root: Path) -> Dict[str, Any]:
    """
    Build architecture summary from project_root/self_map.json.
    Returns dict with keys: system, central_modules, risks, maturity.
    If self_map.json is missing, returns {"error": "...", "path": "..."}.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.rules import build_summary

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {"error": "self_map.json not found", "path": str(self_map_path)}

    graph = build_graph_from_self_map(self_map_path)
    smells = detect_architecture_smells(graph)
    summary = build_summary(graph, smells)
    return summary


def get_history(project_root: Path, window: int = 5) -> Dict[str, Any]:
    """
    Read architecture history from project_root/architecture_history.json.
    Returns dict with keys: trends, regressions, evolution_report, points.
    points are the last `window` history points (each as dict).
    """
    from eurika.evolution.history import HistoryPoint
    from eurika.storage import ProjectMemory

    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    history = memory.history
    points: List[HistoryPoint] = history._window(window)
    return {
        "trends": history.trend(window=window),
        "regressions": history.detect_regressions(window=window),
        "evolution_report": history.evolution_report(window=window),
        "points": [asdict(p) for p in points],
    }


def get_diff(old_self_map_path: Path, new_self_map_path: Path) -> Dict[str, Any]:
    """
    Compare two self_map snapshots; paths can be absolute or relative.
    Returns dict with keys: structures, centrality_shifts, smells, maturity,
    system, recommended_actions, bottleneck_modules.
    All values are JSON-serializable (tuples converted to lists).
    """
    from eurika.evolution.diff import build_snapshot, diff_snapshots

    old_path = Path(old_self_map_path).resolve()
    new_path = Path(new_self_map_path).resolve()
    if not old_path.exists():
        return {"error": "old self_map not found", "path": str(old_path)}
    if not new_path.exists():
        return {"error": "new self_map not found", "path": str(new_path)}

    old_snap = build_snapshot(old_path)
    new_snap = build_snapshot(new_path)
    diff = diff_snapshots(old_snap, new_snap)
    return _to_json_safe(diff)
