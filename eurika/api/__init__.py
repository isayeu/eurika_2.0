"""JSON API for future UI (ROADMAP §2.3).

Thin layer over eurika.*: returns JSON-serializable dicts for summary, history, diff.
Use json.dumps() on the return value to serve over HTTP or save to file.
"""

from __future__ import annotations

import json
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


def get_graph(project_root: Path) -> Dict[str, Any]:
    """
    Build dependency graph for UI (ROADMAP 3.5.7).
    Returns { nodes, edges } for vis-network format.
    nodes: [{ id, label, title, fan_in, fan_out }]
    edges: [{ from, to }]
    """
    from eurika.analysis.self_map import build_graph_from_self_map

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {"error": "self_map.json not found", "path": str(self_map_path)}

    graph = build_graph_from_self_map(self_map_path)
    fan = graph.fan_in_out()
    nodes = []
    for n in sorted(graph.nodes):
        fi, fo = fan.get(n, (0, 0))
        short = Path(n).name if "/" in n else n
        nodes.append({
            "id": n,
            "label": short,
            "title": n + f" (fan-in: {fi}, fan-out: {fo})",
            "fan_in": fi,
            "fan_out": fo,
        })
    edges = []
    for src, dsts in graph.edges.items():
        for dst in dsts:
            edges.append({"from": src, "to": dst})
    return {"nodes": nodes, "edges": edges}


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


def get_pending_plan(project_root: Path) -> Dict[str, Any]:
    """Load pending plan from .eurika/pending_plan.json for approve UI (ROADMAP 3.5.6)."""
    from cli.orchestration.team_mode import has_pending_plan, load_pending_plan

    root = Path(project_root).resolve()
    if not has_pending_plan(root):
        return {"error": "no pending plan", "hint": "Run eurika fix . --team-mode first"}
    data = load_pending_plan(root)
    if data is None:
        return {"error": "invalid pending plan", "hint": "Check .eurika/pending_plan.json"}
    return data


def save_approvals(project_root: Path, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Update team_decision and approved_by in pending_plan.json (ROADMAP 3.5.6)."""
    from cli.orchestration.team_mode import update_team_decisions

    root = Path(project_root).resolve()
    ok, msg = update_team_decisions(root, operations)
    if ok:
        approved = sum(1 for o in operations if str(o.get("team_decision", "")).lower() == "approve")
        return {"ok": True, "saved": len(operations), "approved": approved}
    return {"error": msg, "hint": "Run eurika fix . --team-mode first"}


def get_operational_metrics(project_root: Path, window: int = 10) -> Dict[str, Any]:
    """Aggregate apply-rate, rollback-rate, median verify time from patch events (ROADMAP 2.7.8)."""
    from eurika.storage import aggregate_operational_metrics

    root = Path(project_root).resolve()
    metrics = aggregate_operational_metrics(root, window=window)
    return metrics if metrics else {"error": "no patch events", "hint": "run eurika fix . at least once"}


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
    """Return smell-action aggregates (local + global merged, ROADMAP 3.0.2); None on error."""
    from eurika.storage.global_memory import get_merged_learning_stats

    try:
        return get_merged_learning_stats(root)
    except Exception:
        return None


def _build_extract_nested_op(
    rel_path: str,
    location: str,
    nested_name: str,
    line_count: int,
    extra_params: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build extract_nested_function operation payload."""
    params: Dict[str, Any] = {"location": location, "nested_function_name": nested_name}
    if extra_params:
        params["extra_params"] = extra_params
    return {
        "target_file": rel_path,
        "kind": "extract_nested_function",
        "description": f"Extract nested function {nested_name} from {rel_path}:{location} ({line_count} lines)",
        "diff": f"# Extracted {nested_name} to module level",
        "smell_type": "long_function",
        "params": params,
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


def _should_emit_refactor_smell_op(
    root: Path,
    rel_path: str,
    diff: str,
    location: str,
    smell_type: str,
) -> bool:
    """Skip noisy refactor_code_smell ops that are likely no-op."""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("tests/"):
        return False
    path = root / rel_path
    if not (path.exists() and path.is_file()):
        return True
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return True
    if diff.strip() and diff.strip() in content:
        return False
    # Do not stack code-smell TODOs on modules already marked for architectural split.
    if f"# TODO: Refactor {rel_path}" in content:
        return False
    # Skip duplicate location-targeted TODOs even if wording varies.
    if location and f"'{location}'" in content and "# TODO (eurika): refactor " in content:
        return False
    # Keep at most one TODO per smell type per file to avoid TODO churn.
    if smell_type and f"# TODO (eurika): refactor {smell_type} " in content:
        return False
    return True


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
                    nested_name, line_count, extra_params = suggestion[0], suggestion[1], (suggestion[2] if len(suggestion) > 2 else [])
                    ops.append(_build_extract_nested_op(rel, smell.location, nested_name, line_count, extra_params or None))
                    continue
            op = _build_refactor_smell_op(rel, smell)
            if _should_emit_refactor_smell_op(root, rel, op["diff"], smell.location, smell.kind):
                ops.append(op)
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


def _truncate_on_word_boundary(raw: str, max_len: int = 200) -> str:
    """Truncate text by word boundary for readable output."""
    if len(raw) <= max_len:
        return raw
    truncated = raw[:max_len]
    cut = truncated.rfind(" ")
    return (truncated[:cut] if cut >= 0 else truncated) + "..."


def explain_module(project_root: Path, module_arg: str, window: int = 5) -> tuple[str | None, str | None]:
    """
    Explain role and risks of a module (ROADMAP 3.1-arch.5).

    Returns (formatted_text, error_message). If error_message is not None, use it for stderr and return 1.
    """
    from eurika.core.pipeline import run_full_analysis
    from eurika.smells.detector import get_remediation_hint, severity_to_level

    root = Path(project_root).resolve()
    try:
        snapshot = run_full_analysis(root, update_artifacts=False)
    except Exception as exc:
        return None, str(exc)
    nodes = list(snapshot.graph.nodes)
    target, resolve_error = _resolve_module_arg(module_arg, root, nodes)
    if resolve_error:
        return None, resolve_error
    if not target:
        return None, f"module '{module_arg}' not in graph"

    graph = snapshot.graph
    summary = snapshot.summary or {}
    fan = graph.fan_in_out()
    fi, fo = fan.get(target, (0, 0))
    central = {c["name"] for c in summary.get("central_modules") or []}
    is_central = target in central
    module_smells = [s for s in snapshot.smells if target in s.nodes]
    risks = summary.get("risks") or []
    module_risks = [r for r in risks if target in r]

    lines: list[str] = []
    lines.append(f"MODULE EXPLANATION: {target}")
    lines.append("")
    lines.append("Role:")
    lines.append(f"- fan-in : {fi}")
    lines.append(f"- fan-out: {fo}")
    lines.append(f"- central: {'yes' if is_central else 'no'}")
    lines.append("")
    lines.append("Smells:")
    if not module_smells:
        lines.append("- none detected for this module")
    else:
        for smell in module_smells:
            level = severity_to_level(smell.severity)
            lines.append(f"- [{smell.type}] ({level}) severity={smell.severity:.2f} — {smell.description}")
            lines.append(f"  → {get_remediation_hint(smell.type)}")
    lines.append("")
    lines.append("Risks (from summary):")
    if not module_risks:
        lines.append("- none highlighted in summary")
    else:
        for risk in module_risks:
            lines.append(f"- {risk}")

    patch_plan = get_patch_plan(root, window=window)
    if patch_plan and patch_plan.get("operations"):
        module_ops = [o for o in patch_plan["operations"] if o.get("target_file") == target]
        if module_ops:
            lines.append("")
            lines.append("Planned operations (from patch-plan):")
            for op in module_ops[:5]:
                kind = op.get("kind", "?")
                desc = _truncate_on_word_boundary(op.get("description", ""))
                lines.append(f"- [{kind}] {desc}")

    fix_path = root / "eurika_fix_report.json"
    if fix_path.exists():
        try:
            data = json.loads(fix_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        else:
            expls = data.get("operation_explanations") or []
            policy = data.get("policy_decisions") or []
            ops = (data.get("patch_plan") or {}).get("operations") or []
            if policy and len(policy) == len(expls):
                pairs = list(zip([d.get("target_file") for d in policy], expls))
            elif ops and len(ops) == len(expls):
                pairs = list(zip([o.get("target_file") for o in ops], expls))
            else:
                pairs = []
            module_rationales = [(tf, expl) for tf, expl in pairs if tf == target]
            if module_rationales:
                lines.append("")
                lines.append("Runtime rationale (from last fix):")
                for _tf, expl in module_rationales[:5]:
                    why = expl.get("why", "")
                    risk = expl.get("risk", "?")
                    outcome = expl.get("expected_outcome", "")
                    rollback = expl.get("rollback_plan", "")
                    verify_out = expl.get("verify_outcome")
                    verify_str = f"verify={verify_out}" if verify_out is not None else "verify=not run"
                    lines.append(f"- why: {_truncate_on_word_boundary(why, 120)}")
                    lines.append(f"  risk={risk}, expected_outcome={_truncate_on_word_boundary(outcome, 80)}")
                    lines.append(f"  rollback_plan={_truncate_on_word_boundary(rollback, 80)}, {verify_str}")

    return "\n".join(lines), None


def _resolve_module_arg(module_arg: str, path: Path, nodes: list[str]) -> tuple[str | None, str | None]:
    """Resolve user module argument to a graph node. Returns (target, error)."""
    mod = module_arg
    m_path = Path(module_arg)
    if m_path.is_absolute():
        try:
            mod = str(m_path.relative_to(path))
        except ValueError:
            mod = m_path.name
    if mod in nodes:
        return mod, None
    candidates = [n for n in nodes if n.endswith("/" + mod) or n.endswith(mod)]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, f"ambiguous module '{module_arg}'; candidates: {', '.join(candidates)}"
    return None, f"module '{module_arg}' not in graph (run 'eurika scan .' to refresh self_map.json)"


def get_suggest_plan_text(project_root: Path, window: int = 5) -> str:
    """
    Build suggest-plan text (ROADMAP 3.1-arch.5).

    Encapsulates graph/smells/recommendations building; returns formatted plan string.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.reasoning.refactor_plan import suggest_refactor_plan
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.advisor import build_recommendations

    summary = get_summary(project_root)
    if summary.get("error"):
        return f"Error: {summary.get('error', 'unknown')}"
    history = get_history(project_root, window=window)
    recommendations = None
    self_map_path = Path(project_root).resolve() / "self_map.json"
    if self_map_path.exists():
        try:
            graph = build_graph_from_self_map(self_map_path)
            smells = detect_architecture_smells(graph)
            recommendations = build_recommendations(graph, smells)
        except Exception:
            pass
    return suggest_refactor_plan(summary, recommendations=recommendations, history_info=history)


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
    files = [f for f in files if f.name != "__init__.py" and not f.name.endswith("_api.py")]
    modified: list[str] = []
    for fpath in files:
        new_content = remove_unused_imports(fpath)
        if new_content is None:
            continue
        rel = str(fpath.relative_to(root)) if root in fpath.parents else fpath.name
        modified.append(rel)
        if apply_changes:
            try:
                fpath.write_text(new_content, encoding="utf-8")
            except OSError:
                pass  # Caller handles reporting
    return modified


# TODO (eurika): refactor long_function 'get_patch_plan' — consider extracting helper


