"""Patch-operation building helpers for architecture planner (review §2: hints via hints_provider)."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from eurika.reasoning.planner.filter_policy import (
    apply_failure_based_fallback,
    apply_smell_action_filters,
    sort_and_reindex_by_learning,
)
from eurika.storage import (
    get_kind_plan_failure_counts,
    get_recent_failures,
    get_recent_failed_kind_plan_pairs,
    get_recent_failed_plan_hashes,
    plan_hash_from_ops,
)
from eurika.reasoning.planner.energy_ranking import estimated_delta_for_op
from eurika.reasoning.planner.heuristics import (
    EXTRACT_CLASS_SKIP_PATTERNS,
    FACADE_MODULES,
    STEP_KIND_TO_ACTION,
    energy_cap_per_cycle,
    max_ops_per_cycle,
)
from eurika.reasoning.planner.hints_provider import (
    build_hints_and_params,
    default_llm_hints_fn,
)
from eurika.smells.detector import ArchSmell
from patch_plan import PatchOperation

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def _uses_self_attributes(node: ast.FunctionDef) -> bool:
    """True when method body reads self.attr (conservative extract-class gate)."""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load):
            if isinstance(child.value, ast.Name) and child.value.id == 'self':
                return True
    return False

def _suggest_extract_class(file_path: Path, min_methods: int=6) -> Optional[tuple[str, List[str]]]:
    """Planner-local suggestion to avoid L3->L4 dependency on refactor package."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    best: Optional[tuple[str, List[str]]] = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [n for n in ast.iter_child_nodes(node) if isinstance(n, ast.FunctionDef) and (not n.name.startswith('__'))]
        if len(methods) < min_methods:
            continue
        extractable = [m.name for m in methods if not _uses_self_attributes(m)]
        if not extractable:
            continue
        if best is None or len(extractable) > len(best[1]):
            best = (node.name, extractable)
    return best

def _is_thin_reexport_module(file_path: Path) -> bool:
    """Heuristic: facade-like re-export module should not get split_module TODO."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError:
        return False
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False
    if any((isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in tree.body)):
        return False
    has_reexport = False
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            has_reexport = True
            continue
        if isinstance(node, ast.Assign) and any((isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets)):
            has_reexport = True
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Pass):
            continue
        return False
    return has_reexport

def _is_extracted_module_name(path_like: str) -> bool:
    """True for already-extracted modules to avoid repeated split chains."""
    p = Path(path_like)
    stem = p.stem.lower()
    return stem.endswith('_extracted')

def build_patch_operations(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], priorities: List[Dict[str, Any]], smells_by_node: Dict[str, List[ArchSmell]], *, learning_stats: Optional[Dict[str, Dict[str, Any]]]=None, graph: Optional['ProjectGraph']=None, self_map: Optional[Dict[str, Any]]=None, oss_patterns: Optional[Dict[str, Any]]=None) -> List[PatchOperation]:
    """Build patch operations from diagnostics input. ROADMAP 3.0.5.4: oss_patterns enriches hints."""
    operations: List[PatchOperation] = []
    cycles_handled: set[frozenset[str]] = set()
    plan_targets = _build_plan_targets(
        priorities, smells, smells_by_node, summary,
        graph=graph, learning_stats=learning_stats, project_root=project_root,
    )
    oss = oss_patterns or {}
    for idx, target in enumerate(plan_targets, start=1):
        operations.extend(
            _operations_for_target(
                project_root,
                idx,
                target,
                smells_by_node,
                cycles_handled,
                graph=graph,
                self_map=self_map,
                oss_patterns=oss,
                learning_stats=learning_stats,
            )
        )
    operations = apply_smell_action_filters(project_root, operations, learning_stats)
    recent_failures = get_recent_failures(Path(project_root), limit=5)
    failed_plans = get_recent_failed_plan_hashes(Path(project_root), limit=10)
    failed_kind_plan_pairs = get_recent_failed_kind_plan_pairs(Path(project_root), limit=15)
    kind_plan_counts = get_kind_plan_failure_counts(Path(project_root), limit=20)
    plan_sig = plan_hash_from_ops(operations)
    if plan_sig in failed_plans:
        operations = list(reversed(operations))
    operations = apply_failure_based_fallback(operations, kind_plan_counts)
    plan_sig = plan_hash_from_ops(operations)
    operations = sort_and_reindex_by_learning(
        operations,
        learning_stats,
        recent_failures=recent_failures,
        failed_kind_plan_pairs=failed_kind_plan_pairs,
        plan_hash=plan_sig,
        kind_plan_counts=kind_plan_counts,
    )
    ops_cap = max_ops_per_cycle()
    energy_cap = energy_cap_per_cycle()
    root = Path(project_root) if project_root else None
    if energy_cap > 0:
        kept: List[PatchOperation] = []
        total_energy = 0.0
        for op in operations:
            if ops_cap > 0 and len(kept) >= ops_cap:
                break
            delta = estimated_delta_for_op(op, root)
            if total_energy + delta > energy_cap:
                break
            kept.append(op)
            total_energy += delta
        operations = kept
    elif ops_cap > 0 and len(operations) > ops_cap:
        operations = operations[:ops_cap]
    return operations

def _build_plan_targets(priorities: List[Dict[str, Any]], smells: List[ArchSmell], smells_by_node: Dict[str, List[ArchSmell]], summary: Dict[str, Any], *, graph: Optional['ProjectGraph'], learning_stats: Optional[Dict[str, Dict[str, Any]]] = None, project_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build plan targets either from graph or priorities fallback (R5 2.2: learning_stats, decay)."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells, targets_from_graph
    if graph:
        root = Path(project_root) if project_root else None
        return targets_from_graph(graph, smells, summary_risks=summary.get('risks'), top_n=8, learning_stats=learning_stats, project_root=root)
    targets = [{'name': p.get('name') or p.get('module') or '', 'kind': refactor_kind_for_smells([s.type for s in smells_by_node.get(p.get('name') or '', [])]), 'reasons': p.get('reasons') or []} for p in priorities[:8]]
    return [t for t in targets if t['name']]

def _maybe_add_cycle_break_operation(operations: List[PatchOperation], node_smells: List[ArchSmell], name: str, *, graph: Optional['ProjectGraph'], self_map: Optional[Dict[str, Any]], cycles_handled: set[frozenset[str]]) -> bool:
    """Try to add remove_cyclic_import operation. Returns True when TODO op should be skipped."""
    if not (graph and self_map):
        return False
    from eurika.reasoning.graph_ops import resolve_module_for_edge, suggest_cycle_break_edge
    for smell in node_smells:
        if smell.type != 'cyclic_dependency':
            continue
        cycle_key = frozenset(smell.nodes)
        if cycle_key in cycles_handled:
            return False
        edge = suggest_cycle_break_edge(graph, smell.nodes)
        if not edge:
            return False
        src_path, dst_path = edge
        target_module = resolve_module_for_edge(self_map, src_path, dst_path)
        if target_module:
            cycles_handled.add(cycle_key)
            operations.append(PatchOperation(target_file=src_path, kind='remove_cyclic_import', description=f'Remove import of {target_module} from {src_path} to break cycle.', diff='# Removed import to break cyclic dependency.', smell_type='cyclic_dependency', params={'target_module': target_module}))
            return name in smell.nodes
        return False
    return False

def _matches_extract_class_skip(name: str) -> bool:
    """True if file should never get extract_class (known to break, e.g. tool_contract)."""
    from fnmatch import fnmatch
    path = name.replace('\\', '/')
    return any((fnmatch(path, p) for p in EXTRACT_CLASS_SKIP_PATTERNS))

def _maybe_add_extract_class_operation(operations: List[PatchOperation], project_root: str, name: str, idx: int, smell_type: str, action_kind: str) -> None:
    """Add extract_class op for god_module split candidates when possible."""
    if not (smell_type == 'god_module' and action_kind == 'split_module'):
        return
    if _matches_extract_class_skip(name):
        return
    file_path = Path(project_root) / name
    if not (file_path.exists() and file_path.is_file()):
        return
    suggestion = _suggest_extract_class(file_path)
    if not suggestion:
        return
    class_name, methods = suggestion
    if _existing_extracted_class_is_synced(project_root, name, class_name, methods):
        return
    operations.append(PatchOperation(target_file=name, kind='extract_class', description=f'[{idx}] Extract class {class_name} from {name} ({len(methods)} static-like methods).', diff=f"# TODO: Extract class {class_name}\n# Methods to extract: {', '.join(methods[:5])}{('...' if len(methods) > 5 else '')}\n", smell_type='god_class', params={'target_class': class_name, 'methods_to_extract': methods}))

def _is_root_level_module(target: Path) -> bool:
    """True when target is at project root. Matches eurika.refactor.extract_class logic."""
    parent = str(target.parent).replace('\\', '/')
    return parent == '.' or parent == '' or '/' not in str(target).replace('\\', '/')


def _existing_extracted_class_is_synced(project_root: str, target_file: str, target_class: str, methods_to_extract: List[str]) -> bool:
    """
    True when extracted class file already exists with matching class/method signature.

    Uses the same extracted-file naming convention as eurika.refactor.extract_class.
    For root-level sources, checks both extraction_sandbox and same-dir (legacy).
    """
    new_class_name = target_class + 'Extracted'
    t = Path(target_file)
    new_name = t.stem + '_' + new_class_name.lower() + '.py'
    candidates: List[Path] = []
    if _is_root_level_module(t):
        candidates.append(Path(project_root) / f'eurika/extraction_sandbox/{new_name}')
    candidates.append(Path(project_root) / (str(t.parent / new_name) if str(t.parent) != '.' else new_name))
    extracted_path = next((p for p in candidates if p.exists() and p.is_file()), None)
    source_path = Path(project_root) / target_file
    if extracted_path is None:
        return False
    try:
        import ast
        content = extracted_path.read_text(encoding='utf-8')
        tree = ast.parse(content)
        source_tree = ast.parse(source_path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return False
    static_methods_in_source: set[str] = set()
    for src_node in ast.walk(source_tree):
        if not isinstance(src_node, ast.ClassDef) or src_node.name != target_class:
            continue
        for member in src_node.body:
            if not isinstance(member, ast.FunctionDef):
                continue
            if any((isinstance(dec, ast.Name) and dec.id == 'staticmethod' for dec in member.decorator_list)):
                static_methods_in_source.add(member.name)
        break
    required_methods = set(methods_to_extract) - static_methods_in_source
    if not required_methods:
        required_methods = set(methods_to_extract)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == new_class_name:
            existing_methods = {m.name for m in node.body if isinstance(m, ast.FunctionDef)}
            return required_methods.issubset(existing_methods)
    return False

def _append_default_refactor_operation(
    operations: List[PatchOperation],
    project_root: str,
    name: str,
    idx: int,
    desc_lines: List[str],
    smell_type: str,
    action_kind: str,
    node_smells: List[ArchSmell],
    *,
    graph: Optional["ProjectGraph"],
    oss_patterns: Optional[Dict[str, Any]] = None,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """Build and append the default TODO refactor operation (review §2). OSS hints limited by success_rate."""
    hints, split_params = build_hints_and_params(
        project_root,
        smell_type,
        action_kind,
        node_smells,
        name,
        graph=graph,
        oss_patterns=oss_patterns or {},
        learning_stats=learning_stats,
        llm_hints_fn=default_llm_hints_fn,
    )
    hint_lines = '\n'.join((f'# - {hint}' for hint in hints))
    diff_hint = f'# TODO: Refactor {name} ({smell_type} -> {action_kind})\n# Suggested steps:\n{hint_lines}\n'
    operations.append(PatchOperation(target_file=name, kind=action_kind, description=' '.join(desc_lines), diff=diff_hint, smell_type=smell_type, params=split_params))

def _operations_for_target(
    project_root: str,
    idx: int,
    target: Dict[str, Any],
    smells_by_node: Dict[str, List[ArchSmell]],
    cycles_handled: set[frozenset[str]],
    *,
    graph: Optional["ProjectGraph"],
    self_map: Optional[Dict[str, Any]] = None,
    oss_patterns: Optional[Dict[str, Any]] = None,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[PatchOperation]:
    """Build patch operations for a single target module."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells
    name = target.get('name') or ''
    if not name:
        return []
    kind = target.get('kind') or 'refactor_module'
    reasons = target.get('reasons') or []
    node_smells = smells_by_node.get(name, [])
    smell_types = [s.type for s in node_smells]
    if not kind or kind == 'refactor_module':
        kind = refactor_kind_for_smells(smell_types)
    action_kind = STEP_KIND_TO_ACTION.get(kind, 'refactor_module')
    smell_type = max(node_smells, key=lambda s: s.severity).type if node_smells else 'unknown'
    desc_lines = [f'[{idx}] Refactor module {name} based on detected architecture smells.']
    if reasons:
        desc_lines.append('Reasons: ' + ', '.join(reasons))
    operations: List[PatchOperation] = []
    if smell_type == 'cyclic_dependency' and _maybe_add_cycle_break_operation(operations, node_smells, name, graph=graph, self_map=self_map, cycles_handled=cycles_handled):
        return operations
    if name in FACADE_MODULES and action_kind in ('split_module', 'refactor_module'):
        return operations
    if action_kind == 'split_module':
        path = Path(project_root) / name
        if _is_extracted_module_name(name):
            return operations
        if _is_thin_reexport_module(path):
            return operations
    _maybe_add_extract_class_operation(operations, project_root, name, idx, smell_type, action_kind)
    _append_default_refactor_operation(
        operations,
        project_root,
        name,
        idx,
        desc_lines,
        smell_type,
        action_kind,
        node_smells,
        graph=graph,
        oss_patterns=oss_patterns or {},
        learning_stats=learning_stats,
    )
    return operations
