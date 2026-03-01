"""JSON API for future UI (ROADMAP §2.3).

Thin layer over eurika.*: returns JSON-serializable dicts for summary, history, diff.
Use json.dumps() on the return value to serve over HTTP or save to file.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from .ops import get_clean_imports_operations, get_code_smell_operations  # noqa: F401

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
    self_map_path = root / 'self_map.json'
    if not self_map_path.exists():
        return {'error': 'self_map.json not found', 'path': str(self_map_path)}
    graph = build_graph_from_self_map(self_map_path)
    fan = graph.fan_in_out()
    nodes = []
    for n in sorted(graph.nodes):
        fi, fo = fan.get(n, (0, 0))
        short = Path(n).name if '/' in n else n
        nodes.append({'id': n, 'label': short, 'title': n + f' (fan-in: {fi}, fan-out: {fo})', 'fan_in': fi, 'fan_out': fo})
    edges = []
    for src, dsts in graph.edges.items():
        for dst in dsts:
            edges.append({'from': src, 'to': dst})
    return {'nodes': nodes, 'edges': edges}

def get_summary(
    project_root: Path,
    *,
    include_plugins: bool = False,
) -> Dict[str, Any]:
    """
    Build architecture summary from project_root/self_map.json.
    Returns dict with keys: system, central_modules, risks, maturity.
    If self_map.json is missing, returns {"error": "...", "path": "..."}.
    R5: include_plugins=True merges plugin smells into summary.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.smells.rules import build_summary
    root = Path(project_root).resolve()
    self_map_path = root / 'self_map.json'
    if not self_map_path.exists():
        return {'error': 'self_map.json not found', 'path': str(self_map_path)}
    graph = build_graph_from_self_map(self_map_path)
    if include_plugins:
        from eurika.plugins import detect_smells_with_plugins, merge_smells_for_report
        eurika_smells, plugin_results = detect_smells_with_plugins(root, include_plugins=True)
        smells = merge_smells_for_report(eurika_smells, plugin_results)
        summary = build_summary(graph, smells)
        summary["_plugin_counts"] = [{"plugin": pid, "count": len(s)} for pid, s in plugin_results]
    else:
        from eurika.smells.detector import detect_architecture_smells
        smells = detect_architecture_smells(graph)
        summary = build_summary(graph, smells)
    return summary


def get_risk_prediction(project_root: Path, top_n: int = 10) -> Dict[str, Any]:
    """R5 2.1: Top modules by regression risk (smells + centrality + trends)."""
    from eurika.reasoning.risk_prediction import predict_module_regression_risk
    root = Path(project_root).resolve()
    predictions = predict_module_regression_risk(root, top_n=top_n)
    return {"predictions": predictions}


def get_smells_with_plugins(
    project_root: Path,
    *,
    include_plugins: bool = True,
) -> Dict[str, Any]:
    """R5 3.3: Eurika smells + plugin smells for unified report."""
    from eurika.plugins import detect_smells_with_plugins, merge_smells_for_report

    root = Path(project_root).resolve()
    eurika, plugin_results = detect_smells_with_plugins(root, include_plugins=include_plugins)
    merged = merge_smells_for_report(eurika, plugin_results)
    return {
        "eurika_smells": [
            {"type": s.type, "nodes": s.nodes, "severity": s.severity, "description": s.description}
            for s in eurika
        ],
        "plugin_smells": [
            {"plugin": pid, "count": len(smells)}
            for pid, smells in plugin_results
        ],
        "merged": [
            {"type": s.type, "nodes": s.nodes, "severity": s.severity, "description": s.description}
            for s in merged
        ],
    }


def get_self_guard(project_root: Path) -> Dict[str, Any]:
    """R5: SELF-GUARD aggregated health gate for GUI/API."""
    from eurika.checks.self_guard import collect_self_guard
    root = Path(project_root).resolve()
    result = collect_self_guard(root)
    return {
        "forbidden_count": result.forbidden_count,
        "layer_viol_count": result.layer_viol_count,
        "subsystem_bypass_count": result.subsystem_bypass_count,
        "must_split_count": result.must_split_count,
        "candidates_count": result.candidates_count,
        "trend_alarms": result.trend_alarms,
        "complexity_budget_alarms": result.complexity_budget_alarms,
        "pass": (
            result.forbidden_count == 0
            and result.layer_viol_count == 0
            and result.subsystem_bypass_count == 0
            and result.must_split_count == 0
        ),
    }


def get_pending_plan(project_root: Path) -> Dict[str, Any]:
    """Load pending plan from .eurika/pending_plan.json for approve UI (ROADMAP 3.5.6)."""
    from cli.orchestration.team_mode import has_pending_plan, load_pending_plan
    root = Path(project_root).resolve()
    if not has_pending_plan(root):
        return {'error': 'no pending plan', 'hint': 'Run eurika fix . --team-mode first'}
    data = load_pending_plan(root)
    if data is None:
        return {'error': 'invalid pending plan', 'hint': 'Check .eurika/pending_plan.json'}
    return data

def save_approvals(project_root: Path, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Update team_decision and approved_by in pending_plan.json (ROADMAP 3.5.6)."""
    from cli.orchestration.team_mode import update_team_decisions
    root = Path(project_root).resolve()
    if not isinstance(operations, list) or any((not isinstance(o, dict) for o in operations)):
        return {'error': 'invalid operations payload', 'hint': 'Expected operations: list[object]'}
    ok, msg = update_team_decisions(root, operations)
    if ok:
        approved = sum((1 for o in operations if str(o.get('team_decision', '')).lower() == 'approve'))
        return {'ok': True, 'saved': len(operations), 'approved': approved}
    return {'error': msg, 'hint': 'Run eurika fix . --team-mode first'}

def get_operational_metrics(project_root: Path, window: int=10) -> Dict[str, Any]:
    """Aggregate apply-rate, rollback-rate, median verify time from patch events (ROADMAP 2.7.8)."""
    from eurika.storage import aggregate_operational_metrics
    root = Path(project_root).resolve()
    metrics = aggregate_operational_metrics(root, window=window)
    return metrics if metrics else {'error': 'no patch events', 'hint': 'run eurika fix . at least once'}

def get_chat_dialog_state(project_root: Path) -> Dict[str, Any]:
    """Read lightweight chat dialog state for UI transparency."""
    root = Path(project_root).resolve()
    path = root / '.eurika' / 'chat_history' / 'dialog_state.json'
    if not path.exists():
        return {'active_goal': {}, 'pending_clarification': {}, 'pending_plan': {}, 'last_execution': {}}
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            return {'active_goal': {}, 'pending_clarification': {}, 'pending_plan': {}, 'last_execution': {}}
        active = raw.get('active_goal')
        pending = raw.get('pending_clarification')
        pending_plan = raw.get('pending_plan')
        last_execution = raw.get('last_execution')
        return {'active_goal': active if isinstance(active, dict) else {}, 'pending_clarification': pending if isinstance(pending, dict) else {}, 'pending_plan': pending_plan if isinstance(pending_plan, dict) else {}, 'last_execution': last_execution if isinstance(last_execution, dict) else {}}
    except (json.JSONDecodeError, OSError):
        return {'active_goal': {}, 'pending_clarification': {}, 'pending_plan': {}, 'last_execution': {}}

def _chat_intent_outcome_from_text(text: str) -> str | None:
    """Resolve chat intent outcome from assistant text: success | fail | None."""
    content = str(text or '').strip()
    if not content:
        return None
    low = content.lower()
    if '[error]' in low or '[request failed]' in low or 'не удалось' in low:
        return 'fail'
    success_markers = ('[сохранено в ', 'создан пустой файл ', 'удалён файл ', 'запустил `eurika fix .`', 'запустил eurika fix')
    if any((marker in low for marker in success_markers)):
        return 'success'
    return None

def _chat_learning_recommendations(project_root: Path, top_n: int) -> Dict[str, List[Dict[str, Any]]]:
    """Derive conservative policy/whitelist hints from chat intent outcomes."""
    from .chat_intent import detect_intent
    root = Path(project_root).resolve()
    path = root / '.eurika' / 'chat_history' / 'chat.jsonl'
    if not path.exists():
        return {'chat_whitelist_hints': [], 'chat_policy_review_hints': []}
    by_key: Dict[str, Dict[str, Any]] = {}
    last_user: str | None = None
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = str(rec.get('role') or '').strip().lower()
            content = str(rec.get('content') or '')
            if role == 'user':
                last_user = content
                continue
            if role != 'assistant' or last_user is None:
                continue
            intent, target = detect_intent(last_user)
            last_user = None
            if intent not in {'save', 'create', 'delete', 'refactor'}:
                continue
            outcome = _chat_intent_outcome_from_text(content)
            if outcome is None:
                continue
            target_str = str(target or '.')
            key = f'{intent}|{target_str}'
            bucket = by_key.setdefault(key, {'intent': intent, 'target': target_str, 'total': 0, 'success': 0, 'fail': 0})
            bucket['total'] += 1
            bucket[outcome] += 1
    except OSError:
        return {'chat_whitelist_hints': [], 'chat_policy_review_hints': []}
    rows: list[Dict[str, Any]] = []
    for row in by_key.values():
        total = max(int(row.get('total', 0)), 1)
        row['success_rate'] = round(float(row.get('success', 0)) / total, 4)
        if row.get('intent') in {'save', 'create', 'delete'}:
            row['suggestion'] = 'consider allowlist review for this chat intent target'
        else:
            row['suggestion'] = 'consider safer canned flow for frequent refactor intent'
        rows.append(row)
    rows.sort(key=lambda item: (float(item.get('success_rate', 0.0)), int(item.get('success', 0)), -int(item.get('fail', 0))), reverse=True)
    whitelist_hints = [r for r in rows if int(r.get('total', 0)) >= 2 and int(r.get('fail', 0)) == 0 and (float(r.get('success_rate', 0.0)) >= 0.7)][:top_n]
    policy_review_hints = [r for r in rows if int(r.get('total', 0)) >= 2 and int(r.get('fail', 0)) >= 1 and (float(r.get('success_rate', 0.0)) < 0.4)][:top_n]
    return {'chat_whitelist_hints': whitelist_hints, 'chat_policy_review_hints': policy_review_hints}

def get_learning_insights(project_root: Path, top_n: int=5, *, polygon_only: bool=False) -> Dict[str, Any]:
    """Learning insights for UI: what worked and policy/whitelist hints.
    polygon_only: filter to eurika/polygon/ targets only (drill view).
    """
    from eurika.storage import ProjectMemory
    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    by_action_kind = memory.learning.aggregate_by_action_kind()
    by_smell_action = memory.learning.aggregate_by_smell_action()
    records = memory.learning.all()
    by_target: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        for op in rec.operations:
            target = str(op.get('target_file') or '').strip()
            if not target:
                continue
            if polygon_only and not target.startswith("eurika/polygon/"):
                continue
            kind = str(op.get('kind') or 'unknown')
            smell = str(op.get('smell_type') or 'unknown')
            key = f'{smell}|{kind}|{target}'
            bucket = by_target.setdefault(key, {'smell_type': smell, 'action_kind': kind, 'target_file': target, 'total': 0, 'verify_success': 0, 'verify_fail': 0, 'not_applied': 0})
            bucket['total'] += 1
            outcome = str(op.get('execution_outcome') or '')
            if outcome == 'verify_success' or (not outcome and rec.verify_success is True):
                bucket['verify_success'] += 1
            elif outcome == 'verify_fail' or (not outcome and rec.verify_success is False):
                bucket['verify_fail'] += 1
            else:
                bucket['not_applied'] += 1
    for stats in by_target.values():
        total = max(int(stats.get('total', 0)), 1)
        stats['verify_success_rate'] = round(float(stats.get('verify_success', 0)) / total, 4)
    ordered_targets = sorted(by_target.values(), key=lambda item: (float(item.get('verify_success_rate', 0.0)), int(item.get('verify_success', 0)), -int(item.get('verify_fail', 0))), reverse=True)
    whitelist_candidates = [item for item in ordered_targets if int(item.get('total', 0)) >= 2 and float(item.get('verify_success_rate', 0.0)) >= 0.6][:top_n]
    deny_candidates = [item for item in ordered_targets if int(item.get('total', 0)) >= 3 and float(item.get('verify_success_rate', 0.0)) < 0.25][:top_n]
    chat_recs = _chat_learning_recommendations(root, top_n=top_n)
    if polygon_only:
        by_smell_action = {}
        for item in ordered_targets:
            k = f"{item.get('smell_type', '?')}|{item.get('action_kind', '?')}"
            if k not in by_smell_action:
                by_smell_action[k] = {'total': 0, 'verify_success': 0, 'verify_fail': 0}
            by_smell_action[k]['total'] += int(item.get('total', 0))
            by_smell_action[k]['verify_success'] += int(item.get('verify_success', 0))
            by_smell_action[k]['verify_fail'] += int(item.get('verify_fail', 0))
    return {'by_action_kind': by_action_kind, 'by_smell_action': by_smell_action, 'by_target': ordered_targets[:max(top_n, 1) * 2], 'what_worked': ordered_targets[:top_n], 'recommendations': {'whitelist_candidates': whitelist_candidates, 'policy_deny_candidates': deny_candidates, 'chat_whitelist_hints': chat_recs.get('chat_whitelist_hints', []), 'chat_policy_review_hints': chat_recs.get('chat_policy_review_hints', [])}}

def get_history(project_root: Path, window: int=5) -> Dict[str, Any]:
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

def get_recent_events(project_root: Path, limit: int=5, types: Optional[Sequence[str]]=None) -> list:
    """Last N events for architect context (ROADMAP 3.2.3). Returns Event objects."""
    from eurika.storage import ProjectMemory
    root = Path(project_root).resolve()
    memory = ProjectMemory(root)
    return memory.events.recent_events(limit=limit, types=types or ('patch', 'learn'))

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
        return {'error': 'old self_map not found', 'path': str(old_path)}
    if not new_path.exists():
        return {'error': 'new self_map not found', 'path': str(new_path)}
    old_snap = build_snapshot(old_path)
    new_snap = build_snapshot(new_path)
    diff = diff_snapshots(old_snap, new_snap)
    return _to_json_safe(diff)


def preview_operation(project_root: Path, op: Dict[str, Any]) -> Dict[str, Any]:
    """
    Preview single-file operation: compute old/new content and unified diff (ROADMAP 3.6.7).

    Supports: remove_unused_import, remove_cyclic_import, extract_block_to_helper,
    extract_nested_function, fix_import. Multi-file ops (split_module, introduce_facade)
    return error.

    Returns: {target_file, old_content, new_content, unified_diff, error?}
    """
    import difflib
    root = Path(project_root).resolve()
    target_file = str(op.get('target_file') or '').strip()
    kind = str(op.get('kind') or '').strip()
    params = op.get('params') or {}
    if not target_file or not kind:
        return {'error': 'target_file and kind required'}
    path = root / target_file
    if not path.exists() or not path.is_file():
        return {'error': f'file not found: {target_file}'}
    supported = {'remove_unused_import', 'remove_cyclic_import', 'extract_block_to_helper',
                 'extract_nested_function', 'fix_import'}
    if kind not in supported:
        return {'error': f'preview not supported for kind={kind} (multi-file or unsupported)'}
    try:
        old_content = path.read_text(encoding='utf-8')
    except OSError as e:
        return {'error': f'read failed: {e}'}
    new_content: str | None = None
    if kind == 'remove_unused_import':
        from eurika.refactor.remove_unused_import import remove_unused_imports
        new_content = remove_unused_imports(path)
    elif kind == 'remove_cyclic_import' and params.get('target_module'):
        from eurika.refactor.remove_import import remove_import_from_file
        new_content = remove_import_from_file(path, params['target_module'])
    elif kind == 'extract_block_to_helper':
        from eurika.refactor.extract_function import extract_block_to_helper
        loc = params.get('location')
        line = params.get('block_start_line')
        helper = params.get('helper_name')
        extra = params.get('extra_params')
        if loc is not None and helper:
            new_content = extract_block_to_helper(
                path, loc, int(line) if line is not None else 0, helper,
                extra_params=extra if isinstance(extra, list) else None,
            )
    elif kind == 'extract_nested_function':
        from eurika.refactor.extract_function import extract_nested_function
        loc = params.get('location')
        nested = params.get('nested_function_name')
        extra = params.get('extra_params')
        if loc and nested:
            new_content = extract_nested_function(
                path, loc, nested,
                extra_params=extra if isinstance(extra, list) else None,
            )
    elif kind == 'fix_import':
        new_content = op.get('diff') or ''
    if new_content is None or (kind == 'fix_import' and not new_content):
        return {
            'target_file': target_file,
            'kind': kind,
            'old_content': old_content,
            'error': 'operation would produce no change or extraction failed',
        }
    unified_lines = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f'a/{target_file}',
        tofile=f'b/{target_file}',
        lineterm='',
    ))
    unified_diff = ''.join(unified_lines) if unified_lines else ''
    return {
        'target_file': target_file,
        'kind': kind,
        'old_content': old_content,
        'new_content': new_content,
        'unified_diff': unified_diff,
    }

def _truncate_on_word_boundary(raw: str, max_len: int=200) -> str:
    """Truncate text by word boundary for readable output."""
    if len(raw) <= max_len:
        return raw
    truncated = raw[:max_len]
    cut = truncated.rfind(' ')
    return (truncated[:cut] if cut >= 0 else truncated) + '...'

def explain_module(project_root: Path, module_arg: str, window: int=5) -> tuple[str | None, str | None]:
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
        return (None, str(exc))
    nodes = list(snapshot.graph.nodes)
    target, resolve_error = _resolve_module_arg(module_arg, root, nodes)
    if resolve_error:
        return (None, resolve_error)
    if not target:
        return (None, f"module '{module_arg}' not in graph")
    graph = snapshot.graph
    summary = snapshot.summary or {}
    fan = graph.fan_in_out()
    fi, fo = fan.get(target, (0, 0))
    central = {c['name'] for c in summary.get('central_modules') or []}
    is_central = target in central
    module_smells = [s for s in snapshot.smells if target in s.nodes]
    risks = summary.get('risks') or []
    module_risks = [r for r in risks if target in r]
    lines: list[str] = []
    lines.append(f'MODULE EXPLANATION: {target}')
    lines.append('')
    lines.append('Role:')
    lines.append(f'- fan-in : {fi}')
    lines.append(f'- fan-out: {fo}')
    lines.append(f"- central: {('yes' if is_central else 'no')}")
    lines.append('')
    lines.append('Smells:')
    if not module_smells:
        lines.append('- none detected for this module')
    else:
        for smell in module_smells:
            level = severity_to_level(smell.severity)
            lines.append(f'- [{smell.type}] ({level}) severity={smell.severity:.2f} — {smell.description}')
            lines.append(f'  → {get_remediation_hint(smell.type)}')
    lines.append('')
    lines.append('Risks (from summary):')
    if not module_risks:
        lines.append('- none highlighted in summary')
    else:
        for risk in module_risks:
            lines.append(f'- {risk}')
    patch_plan = get_patch_plan(root, window=window)
    if patch_plan and patch_plan.get('operations'):
        module_ops = [o for o in patch_plan['operations'] if o.get('target_file') == target]
        if module_ops:
            lines.append('')
            lines.append('Planned operations (from patch-plan):')
            for op in module_ops[:5]:
                kind = op.get('kind', '?')
                desc = _truncate_on_word_boundary(op.get('description', ''))
                lines.append(f'- [{kind}] {desc}')
    fix_path = root / 'eurika_fix_report.json'
    if fix_path.exists():
        try:
            data = json.loads(fix_path.read_text(encoding='utf-8'))
        except Exception:
            pass
        else:
            expls = data.get('operation_explanations') or []
            policy = data.get('policy_decisions') or []
            ops = (data.get('patch_plan') or {}).get('operations') or []
            if policy and len(policy) == len(expls):
                pairs = list(zip([d.get('target_file') for d in policy], expls))
            elif ops and len(ops) == len(expls):
                pairs = list(zip([o.get('target_file') for o in ops], expls))
            else:
                pairs = []
            module_rationales = [(tf, expl) for tf, expl in pairs if tf == target]
            if module_rationales:
                lines.append('')
                lines.append('Runtime rationale (from last fix):')
                for _tf, expl in module_rationales[:5]:
                    why = expl.get('why', '')
                    risk = expl.get('risk', '?')
                    outcome = expl.get('expected_outcome', '')
                    rollback = expl.get('rollback_plan', '')
                    verify_out = expl.get('verify_outcome')
                    verify_str = f'verify={verify_out}' if verify_out is not None else 'verify=not run'
                    lines.append(f'- why: {_truncate_on_word_boundary(why, 120)}')
                    lines.append(f'  risk={risk}, expected_outcome={_truncate_on_word_boundary(outcome, 80)}')
                    lines.append(f'  rollback_plan={_truncate_on_word_boundary(rollback, 80)}, {verify_str}')
    return ('\n'.join(lines), None)

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
        return (mod, None)
    candidates = [n for n in nodes if n.endswith('/' + mod) or n.endswith(mod)]
    if len(candidates) == 1:
        return (candidates[0], None)
    if len(candidates) > 1:
        return (None, f"ambiguous module '{module_arg}'; candidates: {', '.join(candidates)}")
    return (None, f"module '{module_arg}' not in graph (run 'eurika scan .' to refresh self_map.json)")

def get_suggest_plan_text(project_root: Path, window: int=5) -> str:
    """
    Build suggest-plan text (ROADMAP 3.1-arch.5).

    Encapsulates graph/smells/recommendations building; returns formatted plan string.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.reasoning.refactor_plan import suggest_refactor_plan
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.advisor import build_recommendations
    summary = get_summary(project_root)
    if summary.get('error'):
        return f"Error: {summary.get('error', 'unknown')}"
    history = get_history(project_root, window=window)
    recommendations = None
    self_map_path = Path(project_root).resolve() / 'self_map.json'
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