"""
Architecture Planner v0.3 (draft)

Turns architecture diagnostics (summary + smells + history + priorities)
into a structured, explainable engineering plan.

This is a pure planning layer — no execution, no code changes.

v0.4: graph optional — when ProjectGraph is provided, uses graph_ops
for concrete hints (cycle break edge, facade candidates, split hints).
"""
from __future__ import annotations
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
SMELL_ACTION_SEP = '|'
from eurika.smells.detector import ArchSmell
from eurika.refactor.extract_class import suggest_extract_class
from action_plan import Action, ActionPlan
from patch_plan import PatchOperation, PatchPlan
if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph

@dataclass
class PlanStep:
    """Single step in an architecture plan."""
    id: str
    target: str
    kind: str
    priority: int
    rationale: str
    hints: List[str]
    smell_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ArchitecturePlan:
    """Top-level architecture plan container."""
    project_root: str
    generated_from: Dict[str, Any]
    steps: List[PlanStep]

    def to_dict(self) -> Dict[str, Any]:
        return {'project_root': self.project_root, 'generated_from': self.generated_from, 'steps': [s.to_dict() for s in self.steps]}

def build_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]]) -> ArchitecturePlan:
    """
    Build a minimal architecture plan from diagnostics.

    v0.3 draft:
    - builds a minimal, explainable plan:
      one high-level PlanStep per prioritized module (top-N).
    """
    generated_from = {'summary_risks': list(summary.get('risks', [])), 'history_trends': dict(history_info.get('trends', {})), 'history_regressions': list(history_info.get('regressions', [])), 'priorities_count': len(priorities)}
    smells_by_node = _index_smells_by_node(smells)
    steps = _build_steps_from_priorities(priorities, smells_by_node)
    return ArchitecturePlan(project_root=project_root, generated_from=generated_from, steps=steps)

def build_action_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> ActionPlan:
    """
    Build an ActionPlan directly from diagnostics.

    If learning_stats is provided (e.g. from LearningStore.aggregate_by_action_kind
    with success_rate added), actions whose type has good past success get a small
    expected_benefit bump.
    """
    arch_plan = build_plan(project_root, summary, smells, history_info, priorities)
    return _actions_from_arch_plan(arch_plan, learning_stats=learning_stats)
STEP_KIND_TO_ACTION: Dict[str, str] = {'split_module': 'split_module', 'introduce_facade': 'introduce_facade', 'split_responsibility': 'refactor_module', 'break_cycle': 'refactor_dependencies', 'refactor_module': 'refactor_module'}
FACADE_MODULES = {'patch_engine.py', 'patch_apply.py'}
DIFF_HINTS: Dict[tuple[str, str], List[str]] = {('god_module', 'split_module'): ['Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).', 'Identify distinct concerns and split this module into focused units.', 'Reduce total degree (fan-in + fan-out) via extraction.'], ('god_module', 'refactor_module'): ['Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).', 'Identify distinct concerns and split this module into focused units.', 'Reduce total degree (fan-in + fan-out) via extraction.'], ('bottleneck', 'introduce_facade'): ['Introduce a facade or boundary to reduce direct fan-in.', 'Create a stable public API for this module; let internal structure evolve independently.', 'Limit the number of modules that import this file directly.'], ('hub', 'refactor_module'): ['Split outgoing dependencies across clearer layers or services.', 'Introduce intermediate abstractions to decouple from concrete implementations.', 'Align with semantic roles and system topology.'], ('hub', 'split_module'): ['Split outgoing dependencies across clearer layers or services.', 'Extract coherent sub-graphs by domain or layer.', 'Reduce fan-out via extraction into focused modules.'], ('cyclic_dependency', 'refactor_dependencies'): ['Break import cycles via inversion of dependencies or adapters.', 'Extract shared interfaces; depend on abstractions, not implementations.', 'Consider introducing a shared-core module used by both sides.']}

def _diff_hints_for(smell_type: str, action_kind: str) -> List[str]:
    """Return tailored diff hints for (smell_type, action_kind)."""
    key = (smell_type, action_kind)
    if key in DIFF_HINTS:
        return DIFF_HINTS[key]
    if smell_type != 'unknown':
        for (s, _), hints in DIFF_HINTS.items():
            if s == smell_type:
                return hints
    return ['Split responsibilities or introduce a facade where appropriate.', 'Reduce excessive fan-in/fan-out.', 'Align with semantic roles and system topology.']

def _success_rate_for_op(op: PatchOperation, learning_stats: Optional[Dict[str, Dict[str, Any]]]) -> float:
    """Return success rate for (smell_type, action_kind); 0.0 if no stats."""
    if not learning_stats:
        return 0.0
    key = f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
    d = learning_stats.get(key, {})
    total = d.get('total', 0)
    if total < 1:
        return 0.0
    return (d.get('success', 0) or 0) / total


def _disabled_smell_actions_from_env() -> set[str]:
    """
    Parse disabled smell-action pairs from env.

    Format:
      EURIKA_DISABLE_SMELL_ACTIONS="hub|split_module,long_function|extract_nested_function"
    """
    raw = os.environ.get("EURIKA_DISABLE_SMELL_ACTIONS", "").strip()
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip() and SMELL_ACTION_SEP in item}


def _build_plan_targets(
    priorities: List[Dict[str, Any]],
    smells: List[ArchSmell],
    smells_by_node: Dict[str, List[ArchSmell]],
    summary: Dict[str, Any],
    *,
    graph: Optional['ProjectGraph'],
) -> List[Dict[str, Any]]:
    """Build plan targets either from graph or priorities fallback."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells, targets_from_graph

    if graph:
        return targets_from_graph(graph, smells, summary_risks=summary.get('risks'), top_n=8)
    targets = [{'name': p.get('name') or p.get('module') or '', 'kind': refactor_kind_for_smells([s.type for s in smells_by_node.get(p.get('name') or '', [])]), 'reasons': p.get('reasons') or []} for p in priorities[:8]]
    return [t for t in targets if t['name']]


def _maybe_add_cycle_break_operation(
    operations: List[PatchOperation],
    node_smells: List[ArchSmell],
    name: str,
    *,
    graph: Optional['ProjectGraph'],
    self_map: Optional[Dict[str, Any]],
    cycles_handled: set[frozenset[str]],
) -> bool:
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


def _maybe_add_extract_class_operation(
    operations: List[PatchOperation],
    project_root: str,
    name: str,
    idx: int,
    smell_type: str,
    action_kind: str,
) -> None:
    """Add extract_class op for god_module split candidates when possible."""
    if not (smell_type == 'god_module' and action_kind == 'split_module'):
        return
    file_path = Path(project_root) / name
    if not (file_path.exists() and file_path.is_file()):
        return
    suggestion = suggest_extract_class(file_path)
    if not suggestion:
        return
    class_name, methods = suggestion
    operations.append(PatchOperation(target_file=name, kind='extract_class', description=f'[{idx}] Extract class {class_name} from {name} ({len(methods)} static-like methods).', diff=f"# TODO: Extract class {class_name}\n# Methods to extract: {', '.join(methods[:5])}{('...' if len(methods) > 5 else '')}\n", smell_type='god_class', params={'target_class': class_name, 'methods_to_extract': methods}))


def _build_hints_and_params(
    smell_type: str,
    action_kind: str,
    node_smells: List[ArchSmell],
    name: str,
    *,
    graph: Optional['ProjectGraph'],
) -> tuple[List[str], Optional[Dict[str, Any]]]:
    """Build diff hints and optional params for operation."""
    hints = list(_diff_hints_for(smell_type, action_kind))
    split_params: Optional[Dict[str, Any]] = None
    if not graph:
        return hints, split_params
    from eurika.reasoning.graph_ops import graph_hints_for_smell, suggest_facade_candidates, suggest_god_module_split_hint

    for smell in node_smells:
        graph_hints = graph_hints_for_smell(graph, smell.type, smell.nodes)
        for gh in graph_hints:
            if gh and gh not in hints:
                hints.append(gh)
    if action_kind == 'split_module':
        info = suggest_god_module_split_hint(graph, name, top_n=5)
        split_params = {'imports_from': info.get('imports_from', []), 'imported_by': info.get('imported_by', [])}
    elif action_kind == 'introduce_facade':
        callers = suggest_facade_candidates(graph, name, top_n=5)
        split_params = {'callers': callers} if callers else None
    return hints, split_params


def _operations_for_target(
    project_root: str,
    idx: int,
    target: Dict[str, Any],
    smells_by_node: Dict[str, List[ArchSmell]],
    cycles_handled: set[frozenset[str]],
    *,
    graph: Optional['ProjectGraph'],
    self_map: Optional[Dict[str, Any]],
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

    _maybe_add_extract_class_operation(operations, project_root, name, idx, smell_type, action_kind)
    hints, split_params = _build_hints_and_params(smell_type, action_kind, node_smells, name, graph=graph)
    hint_lines = '\n'.join((f'# - {h}' for h in hints))
    diff_hint = f'# TODO: Refactor {name} ({smell_type} -> {action_kind})\n# Suggested steps:\n{hint_lines}\n'
    operations.append(PatchOperation(target_file=name, kind=action_kind, description=' '.join(desc_lines), diff=diff_hint, smell_type=smell_type, params=split_params))
    return operations


def _should_emit_default_todo_op(project_root: str, target_file: str, kind: str, diff: str) -> bool:
    """
    Return False when default append-style TODO is already present in target file.

    This reduces noisy skipped operations like:
    - "diff already in content"
    - "architectural TODO already present"
    """
    if kind not in ("refactor_module", "split_module", "refactor_code_smell"):
        return True
    path = Path(project_root) / target_file
    if not (path.exists() and path.is_file()):
        return True
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return True
    if diff.strip() and diff.strip() in content:
        return False
    if kind in ("refactor_module", "split_module"):
        marker = f"# TODO: Refactor {target_file}"
        if marker in content:
            return False
    return True


def _fallback_kind_for_low_success(smell_type: str, action_kind: str) -> Optional[str]:
    """Return safer fallback action for low-success smell/action pairs."""
    fallbacks = {
        ("hub", "split_module"): "refactor_module",
    }
    return fallbacks.get((smell_type, action_kind))


def _rebuild_operation_with_kind(op: PatchOperation, new_kind: str) -> PatchOperation:
    """Rebuild operation with a different kind and matching diff hints."""
    smell_type = op.smell_type or "unknown"
    hints = _diff_hints_for(smell_type, new_kind)
    hint_lines = "\n".join((f"# - {h}" for h in hints))
    diff_hint = f"# TODO: Refactor {op.target_file} ({smell_type} -> {new_kind})\n# Suggested steps:\n{hint_lines}\n"
    # split-module specific params are not applicable to generic fallback actions.
    params = op.params if new_kind not in ("refactor_module", "refactor_code_smell") else None
    return PatchOperation(
        target_file=op.target_file,
        kind=new_kind,
        description=op.description,
        diff=diff_hint,
        smell_type=op.smell_type,
        params=params,
    )


def _apply_smell_action_filters(
    project_root: str,
    operations: List[PatchOperation],
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
) -> List[PatchOperation]:
    """Apply env-based disabling and low-success filtering."""
    MIN_TOTAL_FOR_FILTER = 3
    MIN_SUCCESS_RATE = 0.25
    operations = [
        op for op in operations
        if _should_emit_default_todo_op(project_root, op.target_file, op.kind, op.diff)
    ]
    if not learning_stats:
        disabled_smell_actions = _disabled_smell_actions_from_env()
        if disabled_smell_actions:
            operations = [
                op for op in operations
                if f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}" not in disabled_smell_actions
            ]
        return operations
    filtered: List[PatchOperation] = []
    for op in operations:
        key = f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
        d = learning_stats.get(key, {})
        total = d.get('total', 0)
        if total >= MIN_TOTAL_FOR_FILTER:
            rate = (d.get('success', 0) or 0) / total
            if rate < MIN_SUCCESS_RATE:
                fallback = _fallback_kind_for_low_success(op.smell_type or "unknown", op.kind)
                if fallback:
                    op = _rebuild_operation_with_kind(op, fallback)
                else:
                    continue
        filtered.append(op)
    disabled_smell_actions = _disabled_smell_actions_from_env()
    if disabled_smell_actions:
        filtered = [
            op for op in filtered
            if f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}" not in disabled_smell_actions
        ]
    return filtered


def _sort_and_reindex_by_learning(
    operations: List[PatchOperation],
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
) -> List[PatchOperation]:
    """Sort operations by historical success rate and normalize index prefix."""
    if not learning_stats:
        return operations
    ordered = sorted(operations, key=lambda o: _success_rate_for_op(o, learning_stats), reverse=True)
    reindexed: List[PatchOperation] = []
    for i, op in enumerate(ordered, start=1):
        desc = op.description
        if desc.startswith('['):
            rest = desc.split(']', 1)[-1].lstrip()
            reindexed.append(PatchOperation(target_file=op.target_file, kind=op.kind, description=f'[{i}] {rest}', diff=op.diff, smell_type=op.smell_type, params=op.params))
        else:
            reindexed.append(op)
    return reindexed


def build_patch_plan(project_root: str, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priorities: List[Dict[str, Any]], learning_stats: Optional[Dict[str, Dict[str, Any]]]=None, graph: Optional['ProjectGraph']=None, self_map: Optional[Dict[str, Any]]=None) -> PatchPlan:
    """
    Build a first-approximation PatchPlan from diagnostics.

    v0.1: for each top-priority module, create a textual patch operation
    that describes the intended refactor. Uses smell types and step kinds
    to support (smell_type, action_kind) learning aggregation.

    When learning_stats is provided (e.g. from LearningStore.aggregate_by_smell_action),
    operations are sorted by past success rate (higher first) so that
    historically successful (smell_type, action_kind) pairs are applied first.

    When graph is provided (ROADMAP 2.1 — Граф как инструмент), diff hints
    are enriched with graph-derived suggestions (cycle break edge, facade
    candidates, split hints).
    """
    operations: List[PatchOperation] = []
    smells_by_node = _index_smells_by_node(smells)
    cycles_handled: set[frozenset[str]] = set()
    plan_targets = _build_plan_targets(priorities, smells, smells_by_node, summary, graph=graph)
    for idx, t in enumerate(plan_targets, start=1):
        operations.extend(_operations_for_target(project_root, idx, t, smells_by_node, cycles_handled, graph=graph, self_map=self_map))
    operations = _apply_smell_action_filters(project_root, operations, learning_stats)
    operations = _sort_and_reindex_by_learning(operations, learning_stats)
    return PatchPlan(project_root=project_root, operations=operations)

def _index_smells_by_node(smells: List[ArchSmell]) -> Dict[str, List[ArchSmell]]:
    """Build mapping node -> list[ArchSmell]."""
    smells_by_node: Dict[str, List[ArchSmell]] = {}
    for s in smells:
        for n in s.nodes:
            smells_by_node.setdefault(n, []).append(s)
    return smells_by_node

def _decide_step_kind(node_smells: List[ArchSmell]) -> str:
    """Choose plan step kind from smell types (delegates to refactor_kind_for_smells, ROADMAP 3.1.2)."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells
    types = [s.type for s in node_smells]
    return refactor_kind_for_smells(types)

def _build_step_for_module(name: str, node_smells: List[ArchSmell], priority_idx: int, counter: int) -> PlanStep:
    """Create a single PlanStep for a module."""
    kind = _decide_step_kind(node_smells)
    smell_descriptions = [f'{s.type} (severity={s.severity:.2f})' for s in node_smells]
    rationale = f'Module {name} is prioritized due to: ' + ', '.join(smell_descriptions)
    hints: List[str] = []
    if kind == 'split_module':
        hints.append('Extract coherent sub-responsibilities into separate modules.')
    if kind == 'introduce_facade':
        hints.append('Introduce a facade or boundary to reduce direct fan-in.')
    if kind == 'split_responsibility':
        hints.append('Split outgoing dependencies across clearer layers or services.')
    if kind == 'break_cycle':
        hints.append('Break import cycles via inversion of dependencies or adapters.')
    smell_type = max(node_smells, key=lambda s: s.severity).type if node_smells else None
    return PlanStep(id=f'STEP-{counter:03d}', target=name, kind=kind, priority=priority_idx, rationale=rationale, hints=hints, smell_type=smell_type)

def _build_steps_from_priorities(priorities: List[Dict[str, Any]], smells_by_node: Dict[str, List[ArchSmell]], top_n: int=5) -> List[PlanStep]:
    """Generate plan steps from prioritized modules and smells index."""
    steps: List[PlanStep] = []
    counter = 1
    for idx, p in enumerate(priorities[:top_n], start=1):
        name = p.get('name') or p.get('module') or ''
        if not name:
            continue
        node_smells = smells_by_node.get(name, [])
        if not node_smells:
            continue
        step = _build_step_for_module(name, node_smells, idx, counter)
        steps.append(step)
        counter += 1
    return steps

def _actions_from_arch_plan(plan: ArchitecturePlan, learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> ActionPlan:
    """Convert an ArchitecturePlan into an ActionPlan."""
    actions: List[Action] = []
    total_risk = 0.0
    total_gain = 0.0
    for step in plan.steps:
        action = _step_to_action(step, learning_stats=learning_stats)
        actions.append(action)
        total_risk += action.risk
        total_gain += action.expected_benefit
    priority = list(range(len(actions)))
    return ActionPlan(actions=actions, priority=priority, total_risk=round(total_risk, 3), expected_gain=round(total_gain, 3))

def _apply_learning_bump(stats: Dict[str, Any], expected_benefit: float) -> float:
    """Return bumped expected_benefit if stats show success rate >= 0.5."""
    total = stats.get('total', 0)
    success = stats.get('success', 0)
    if total >= 1:
        rate = success / total
        if rate >= 0.5:
            return min(1.0, round(expected_benefit + 0.05, 3))
    return expected_benefit


def _step_to_action(step: PlanStep, learning_stats: Optional[Dict[str, Dict[str, Any]]]=None) -> Action:
    """
    Map a PlanStep to a single high-level Action.

    If learning_stats is provided and the action type has past success rate >= 0.5
    with at least one run, expected_benefit is increased slightly (learned signal).
    """
    type_mapping = {'split_module': 'refactor_module', 'introduce_facade': 'introduce_facade', 'split_responsibility': 'refactor_module', 'break_cycle': 'refactor_dependencies', 'refactor_module': 'refactor_module'}
    action_type = type_mapping.get(step.kind, 'refactor_module')
    description = f'{step.kind} on {step.target}: {step.rationale}'
    base_risk = 0.3
    if step.kind in {'split_module', 'break_cycle'}:
        base_risk = 0.5
    if step.kind == 'introduce_facade':
        base_risk = 0.4
    expected_benefit = max(0.3, 1.0 - 0.1 * (step.priority - 1))
    if learning_stats:
        smell_type = getattr(step, 'smell_type', None) or 'unknown'
        pair_key = f'{smell_type}{SMELL_ACTION_SEP}{action_type}'
        if pair_key in learning_stats:
            expected_benefit = _apply_learning_bump(learning_stats[pair_key], expected_benefit)
        elif action_type in learning_stats:
            expected_benefit = _apply_learning_bump(learning_stats[action_type], expected_benefit)
    return Action(type=action_type, target=step.target, description=description, risk=round(base_risk, 3), expected_benefit=round(expected_benefit, 3))


# TODO: Refactor architecture_planner.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: action_plan.py, patch_plan.py.
# - Consider grouping callers: tests/test_graph_ops.py, agent_core_arch_review_archreviewagentcore.py, eurika/reasoning/planner.py.
