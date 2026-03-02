"""JSON API for future UI (ROADMAP §2.3).

Thin layer over eurika.*: returns JSON-serializable dicts for summary, history, diff.
Use json.dumps() on the return value to serve over HTTP or save to file.

R1 Structural Hardening: API split into submodules (architecture, learning_api, team_api,
diff_api, explain_api) to meet file size budget (<600 LOC).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .architecture import get_firewall_violations_detail, get_graph, get_risk_prediction, get_self_guard, get_smells_with_plugins, get_summary
from .diff_api import get_diff, preview_operation
from .explain_api import get_explain_data
from .learning_api import get_chat_dialog_state, get_learning_insights, get_operational_metrics
from .ops import get_clean_imports_operations, get_code_smell_operations  # noqa: F401
from .team_api import get_pending_plan, save_approvals


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
    return {'trends': history.trend(window=window), 'regressions': history.detect_regressions(window=window), 'evolution_report': history.evolution_report(window=window), 'points': [asdict(p) for p in points]}

def _build_patch_plan_inputs(root: Path, window: int) -> tuple[Any, Any, Dict[str, Any], Dict[str, Any], Any] | None:
    """Build graph/smells/summary/history/priorities inputs for patch planning (R5 2.2: learning_stats in priorities)."""
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.reasoning.graph_ops import priority_from_graph
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.rules import build_summary
    from eurika.storage import ProjectMemory
    from eurika.storage.global_memory import get_merged_learning_stats
    self_map_path = root / 'self_map.json'
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
    history_info = {'trends': history.trend(window=window), 'regressions': history.detect_regressions(window=window), 'evolution_report': history.evolution_report(window=window)}
    learning_stats = None
    try:
        learning_stats = get_merged_learning_stats(root)
    except Exception:
        pass
    priorities = priority_from_graph(
        graph, smells,
        summary_risks=summary.get('risks'),
        top_n=8,
        learning_stats=learning_stats,
    )
    return (graph, smells, summary, history_info, priorities)

def _optional_learning_and_self_map(memory: Any, self_map_path: Path) -> tuple[Any, Any]:
    """Load optional learning stats (local + global merged, ROADMAP 3.0.2) and self_map."""
    from eurika.analysis.self_map import load_self_map
    from eurika.storage.global_memory import get_merged_learning_stats
    learning_stats = None
    self_map = None
    try:
        learning_stats = get_merged_learning_stats(Path(self_map_path).parent)
    except Exception:
        pass
    try:
        self_map = load_self_map(self_map_path)
    except Exception:
        pass
    return (learning_stats, self_map)

def _trace_api(msg: str) -> None:
    import logging
    logging.getLogger("eurika.api").info(f"eurika: doctor — {msg}")


def get_patch_plan(project_root: Path, window: int=5) -> Dict[str, Any] | None:
    """
    Build patch plan from diagnostics (summary, smells, history, graph).
    Returns operations dict or None on error. Used by architect and explain.
    """
    from architecture_planner import build_patch_plan
    from eurika.storage import ProjectMemory
    root = Path(project_root).resolve()
    self_map_path = root / 'self_map.json'
    _trace_api("patch plan: building inputs (graph, smells)...")
    inputs = _build_patch_plan_inputs(root, window)
    if inputs is None:
        return None
    graph, smells, summary, history_info, priorities = inputs
    memory = ProjectMemory(root)
    _trace_api("patch plan: loading learning stats...")
    learning_stats, self_map = _optional_learning_and_self_map(memory, self_map_path)
    _trace_api("patch plan: building operations (may call LLM for split hints)...")
    plan = build_patch_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priorities, learning_stats=learning_stats or None, graph=graph, self_map=self_map)
    payload = plan.to_dict()
    try:
        _trace_api("patch plan: building context sources...")
        from eurika.reasoning.architect import build_context_sources
        payload['context_sources'] = build_context_sources(root, payload.get('operations') or [])
    except Exception:
        pass
    return payload

def get_recent_events(project_root: Path, limit: int = 5, types: Optional[Sequence[str]] = None) -> list:
    """Last N events for architect context (ROADMAP 3.2.3). Returns Event objects."""
    from eurika.storage import ProjectMemory

    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    return memory.events.recent_events(limit=limit, types=types or ("patch", "learn"))


def get_suggest_plan_data(project_root: Path, window: int = 5) -> dict[str, Any]:
    """
    Build suggest-plan data (summary, recommendations, history). Domain layer (R1).
    """
    summary = get_summary(project_root)
    if summary.get("error"):
        return {"error": summary.get("error", "unknown")}
    history = get_history(project_root, window=window)
    recommendations = None
    self_map_path = Path(project_root).resolve() / "self_map.json"
    if self_map_path.exists():
        try:
            from eurika.analysis.self_map import build_graph_from_self_map
            from eurika.smells.detector import detect_architecture_smells
            from eurika.smells.advisor import build_recommendations

            graph = build_graph_from_self_map(self_map_path)
            smells = detect_architecture_smells(graph)
            recommendations = build_recommendations(graph, smells)
        except Exception:
            pass
    return {"summary": summary, "recommendations": recommendations, "history": history}


def clean_imports_scan_apply(project_root: Path, apply_changes: bool) -> list[str]:
    """
    Scan for unused imports, optionally apply (ROADMAP 3.1-arch.5).

    Returns list of modified file paths (relative to project_root).
    """
    from code_awareness import CodeAwareness
    from eurika.refactor.remove_unused_import import remove_unused_imports
    root = Path(project_root).resolve()
    aw = CodeAwareness(root=root)
    files = aw.scan_python_files()
    files = [f for f in files if f.name != '__init__.py' and (not f.name.endswith('_api.py'))]
    modified: list[str] = []
    for fpath in files:
        new_content = remove_unused_imports(fpath)
        if new_content is None:
            continue
        rel = str(fpath.relative_to(root)) if root in fpath.parents else fpath.name
        modified.append(rel)
        if apply_changes:
            try:
                fpath.write_text(new_content, encoding='utf-8')
            except OSError:
                pass
    return modified