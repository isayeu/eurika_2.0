"""JSON API for future UI (ROADMAP §2.3).

Thin layer over eurika.*: returns JSON-serializable dicts for summary, history, diff.
Use json.dumps() on the return value to serve over HTTP or save to file.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


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


def _build_patch_plan_inputs(
    root: Path,
    window: int,
) -> tuple[Any, Any, Dict[str, Any], Dict[str, Any], Any] | None:
    """Build graph/smells/summary/history/priorities inputs for patch planning."""
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.reasoning.graph_ops import priority_from_graph
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.rules import build_summary
    from eurika.storage import ProjectMemory

    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return None
    try:
        graph = build_graph_from_self_map(self_map_path)
        smells = detect_architecture_smells(graph)
        summary = build_summary(graph, smells)
    except Exception:
        return None

    memory = ProjectMemory(root)
    history = memory.history
    history_info = {
        "trends": history.trend(window=window),
        "regressions": history.detect_regressions(window=window),
        "evolution_report": history.evolution_report(window=window),
    }
    priorities = priority_from_graph(
        graph,
        smells,
        summary_risks=summary.get("risks"),
        top_n=8,
    )
    return graph, smells, summary, history_info, priorities


def _optional_learning_and_self_map(memory: Any, self_map_path: Path) -> tuple[Any, Any]:
    """Load optional learning stats and self_map; swallow parsing errors."""
    from eurika.analysis.self_map import load_self_map

    learning_stats = None
    self_map = None
    try:
        learning_stats = memory.learning.aggregate_by_smell_action()
    except Exception:
        pass
    try:
        self_map = load_self_map(self_map_path)
    except Exception:
        pass
    return learning_stats, self_map


def get_patch_plan(project_root: Path, window: int = 5) -> Dict[str, Any] | None:
    """
    Build patch plan from diagnostics (summary, smells, history, graph).
    Returns operations dict or None on error. Used by architect and explain.
    """
    from architecture_planner import build_patch_plan
    from eurika.storage import ProjectMemory

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    inputs = _build_patch_plan_inputs(root, window)
    if inputs is None:
        return None
    graph, smells, summary, history_info, priorities = inputs
    memory = ProjectMemory(root)
    learning_stats, self_map = _optional_learning_and_self_map(memory, self_map_path)

    plan = build_patch_plan(
        project_root=str(root),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        learning_stats=learning_stats or None,
        graph=graph,
        self_map=self_map,
    )
    return plan.to_dict()


def _should_try_extract_nested(stats: Optional[Dict[str, Dict[str, Any]]]) -> bool:
    """Allow extract_nested_function unless history is clearly unfavorable."""
    if not stats:
        return True
    rec = stats.get("long_function|extract_nested_function", {})
    total = int(rec.get("total", 0) or 0)
    success = int(rec.get("success", 0) or 0)
    if total >= 1 and success == 0:
        return False
    if total >= 3 and (success / total) < 0.25:
        return False
    return True


def _load_smell_action_learning_stats(root: Path) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return smell-action aggregates from memory; None on any storage/parsing error."""
    from eurika.storage import ProjectMemory

    try:
        return ProjectMemory(root).learning.aggregate_by_smell_action()
    except Exception:
        return None


def _build_extract_nested_op(
    rel_path: str,
    location: str,
    nested_name: str,
    line_count: int,
) -> Dict[str, Any]:
    """Build extract_nested_function operation payload."""
    return {
        "target_file": rel_path,
        "kind": "extract_nested_function",
        "description": f"Extract nested function {nested_name} from {rel_path}:{location} ({line_count} lines)",
        "diff": f"# Extracted {nested_name} to module level",
        "smell_type": "long_function",
        "params": {"location": location, "nested_function_name": nested_name},
    }


def _build_refactor_smell_op(rel_path: str, smell: Any) -> Dict[str, Any]:
    """Build fallback TODO operation payload for a code smell."""
    hint = "consider extracting helper" if smell.kind == "long_function" else "consider extracting nested block"
    diff = f"\n# TODO (eurika): refactor {smell.kind} '{smell.location}' — {hint}\n"
    return {
        "target_file": rel_path,
        "kind": "refactor_code_smell",
        "description": f"Refactor {smell.kind} in {rel_path}:{smell.location}",
        "diff": diff,
        "smell_type": smell.kind,
        "params": {"location": smell.location, "metric": smell.metric},
    }


def get_code_smell_operations(project_root: Path) -> List[Dict[str, Any]]:
    """
    Build patch operations for code-level smells (long_function, deep_nesting).

    Uses CodeAwareness.find_smells. For long_function, tries extract_nested_function first;
    if a nested function can be extracted, uses kind="extract_nested_function" (real fix).
    Otherwise kind="refactor_code_smell" (TODO).
    """
    from code_awareness import CodeAwareness
    from eurika.refactor.extract_function import suggest_extract_nested_function

    root = Path(project_root).resolve()
    analyzer = CodeAwareness(root)
    allow_extract_nested = _should_try_extract_nested(_load_smell_action_learning_stats(root))
    ops: List[Dict[str, Any]] = []
    for file_path in analyzer.scan_python_files():
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        for smell in analyzer.find_smells(file_path):
            if smell.kind == "long_function" and allow_extract_nested:
                suggestion = suggest_extract_nested_function(file_path, smell.location)
                if suggestion:
                    nested_name, line_count = suggestion
                    ops.append(_build_extract_nested_op(rel, smell.location, nested_name, line_count))
                    continue
            ops.append(_build_refactor_smell_op(rel, smell))
    return ops


def get_clean_imports_operations(project_root: Path) -> List[Dict[str, Any]]:
    """
    Build patch operations to remove unused imports (ROADMAP 2.4.2).

    Scans Python files (excludes __init__.py, *_api.py, venv, .git).
    Returns list of op dicts for patch_apply (kind="remove_unused_import").
    """
    from eurika.refactor.remove_unused_import import remove_unused_imports

    root = Path(project_root).resolve()
    skip_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", ".eurika_backups"}
    # Facade modules: imports are re-exports; remove_unused_import would break API
    facade_modules = {"patch_engine.py", "patch_apply.py"}
    ops: List[Dict[str, Any]] = []
    for p in sorted(root.rglob("*.py")):
        if any(skip in p.parts for skip in skip_dirs):
            continue
        if p.name == "__init__.py" or p.name.endswith("_api.py"):
            continue
        if p.name in facade_modules:
            continue
        if not p.is_file():
            continue
        if remove_unused_imports(p) is None:
            continue
        rel = str(p.relative_to(root))
        ops.append({
            "target_file": rel,
            "kind": "remove_unused_import",
            "description": f"Remove unused imports from {rel}",
            "diff": "# Removed unused imports.",
            "smell_type": None,
        })
    return ops


def get_recent_events(
    project_root: Path,
    limit: int = 5,
    types: Optional[Sequence[str]] = None,
) -> list:
    """Last N events for architect context (ROADMAP 3.2.3). Returns Event objects."""
    from eurika.storage import ProjectMemory

    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    return memory.events.recent_events(limit=limit, types=types or ("patch", "learn"))


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


# TODO (eurika): refactor long_function 'get_patch_plan' — consider extracting helper


