"""Patch-operation building helpers for architecture planner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from eurika.refactor.extract_class import suggest_extract_class
from eurika.reasoning.planner_rules import (
    FACADE_MODULES,
    SMELL_ACTION_SEP,
    STEP_KIND_TO_ACTION,
    diff_hints_for,
    disabled_smell_actions_from_env,
    fallback_kind_for_low_success,
)
from eurika.smells.detector import ArchSmell
from patch_plan import PatchOperation

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def build_patch_operations(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    priorities: List[Dict[str, Any]],
    smells_by_node: Dict[str, List[ArchSmell]],
    *,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    graph: Optional["ProjectGraph"] = None,
    self_map: Optional[Dict[str, Any]] = None,
    oss_patterns: Optional[Dict[str, Any]] = None,
) -> List[PatchOperation]:
    """Build patch operations from diagnostics input. ROADMAP 3.0.5.4: oss_patterns enriches hints."""
    operations: List[PatchOperation] = []
    cycles_handled: set[frozenset[str]] = set()
    plan_targets = _build_plan_targets(
        priorities, smells, smells_by_node, summary, graph=graph
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
            )
        )
    operations = _apply_smell_action_filters(project_root, operations, learning_stats)
    operations = _sort_and_reindex_by_learning(operations, learning_stats)
    return operations


def _success_rate_for_op(
    op: PatchOperation, learning_stats: Optional[Dict[str, Dict[str, Any]]]
) -> float:
    """Return success rate for (smell_type, action_kind); 0.0 if no stats."""
    if not learning_stats:
        return 0.0
    key = f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
    d = learning_stats.get(key, {})
    total = d.get("total", 0)
    if total < 1:
        return 0.0
    return (d.get("success", 0) or 0) / total


def _build_plan_targets(
    priorities: List[Dict[str, Any]],
    smells: List[ArchSmell],
    smells_by_node: Dict[str, List[ArchSmell]],
    summary: Dict[str, Any],
    *,
    graph: Optional["ProjectGraph"],
) -> List[Dict[str, Any]]:
    """Build plan targets either from graph or priorities fallback."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells, targets_from_graph

    if graph:
        return targets_from_graph(
            graph, smells, summary_risks=summary.get("risks"), top_n=8
        )
    targets = [
        {
            "name": p.get("name") or p.get("module") or "",
            "kind": refactor_kind_for_smells(
                [s.type for s in smells_by_node.get(p.get("name") or "", [])]
            ),
            "reasons": p.get("reasons") or [],
        }
        for p in priorities[:8]
    ]
    return [t for t in targets if t["name"]]


def _maybe_add_cycle_break_operation(
    operations: List[PatchOperation],
    node_smells: List[ArchSmell],
    name: str,
    *,
    graph: Optional["ProjectGraph"],
    self_map: Optional[Dict[str, Any]],
    cycles_handled: set[frozenset[str]],
) -> bool:
    """Try to add remove_cyclic_import operation. Returns True when TODO op should be skipped."""
    if not (graph and self_map):
        return False
    from eurika.reasoning.graph_ops import resolve_module_for_edge, suggest_cycle_break_edge

    for smell in node_smells:
        if smell.type != "cyclic_dependency":
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
            operations.append(
                PatchOperation(
                    target_file=src_path,
                    kind="remove_cyclic_import",
                    description=(
                        f"Remove import of {target_module} from {src_path} "
                        "to break cycle."
                    ),
                    diff="# Removed import to break cyclic dependency.",
                    smell_type="cyclic_dependency",
                    params={"target_module": target_module},
                )
            )
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
    if not (smell_type == "god_module" and action_kind == "split_module"):
        return
    file_path = Path(project_root) / name
    if not (file_path.exists() and file_path.is_file()):
        return
    suggestion = suggest_extract_class(file_path)
    if not suggestion:
        return
    class_name, methods = suggestion
    if _existing_extracted_class_is_synced(project_root, name, class_name, methods):
        return
    operations.append(
        PatchOperation(
            target_file=name,
            kind="extract_class",
            description=(
                f"[{idx}] Extract class {class_name} from {name} "
                f"({len(methods)} static-like methods)."
            ),
            diff=(
                f"# TODO: Extract class {class_name}\n"
                "# Methods to extract: "
                f"{', '.join(methods[:5])}{('...' if len(methods) > 5 else '')}\n"
            ),
            smell_type="god_class",
            params={"target_class": class_name, "methods_to_extract": methods},
        )
    )


def _existing_extracted_class_is_synced(
    project_root: str,
    target_file: str,
    target_class: str,
    methods_to_extract: List[str],
) -> bool:
    """
    True when extracted class file already exists with matching class/method signature.

    Uses the same extracted-file naming convention as eurika.refactor.extract_class.
    """
    new_class_name = target_class + "Extracted"
    t = Path(target_file)
    new_name = t.stem + "_" + new_class_name.lower() + ".py"
    new_rel_path = str(t.parent / new_name) if str(t.parent) != "." else new_name
    extracted_path = Path(project_root) / new_rel_path
    source_path = Path(project_root) / target_file
    if not (extracted_path.exists() and extracted_path.is_file()):
        return False
    try:
        import ast

        content = extracted_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        source_tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    static_methods_in_source: set[str] = set()
    for src_node in ast.walk(source_tree):
        if not isinstance(src_node, ast.ClassDef) or src_node.name != target_class:
            continue
        for member in src_node.body:
            if not isinstance(member, ast.FunctionDef):
                continue
            if any(
                isinstance(dec, ast.Name) and dec.id == "staticmethod"
                for dec in member.decorator_list
            ):
                static_methods_in_source.add(member.name)
        break
    required_methods = set(methods_to_extract) - static_methods_in_source
    if not required_methods:
        required_methods = set(methods_to_extract)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == new_class_name:
            existing_methods = {
                m.name for m in node.body if isinstance(m, ast.FunctionDef)
            }
            return required_methods.issubset(existing_methods)
    return False


def _build_hints_and_params(
    smell_type: str,
    action_kind: str,
    node_smells: List[ArchSmell],
    name: str,
    *,
    graph: Optional["ProjectGraph"],
    oss_patterns: Optional[Dict[str, Any]] = None,
) -> tuple[List[str], Optional[Dict[str, Any]]]:
    """Build diff hints and optional params. ROADMAP 2.9.2: LLM hints. ROADMAP 3.0.5.4: OSS examples."""
    hints = list(diff_hints_for(smell_type, action_kind))
    oss = oss_patterns or {}
    entries = oss.get(smell_type, [])
    if isinstance(entries, list):
        for e in entries[:3]:
            if isinstance(e, dict):
                proj = e.get("project", "?")
                mod = e.get("module", "?")
                hint = e.get("hint", "")
                if hint:
                    h = f"OSS ({proj}): {mod} — {hint}"
                    if h not in hints:
                        hints.append(h)
    split_params: Optional[Dict[str, Any]] = None
    if not graph:
        return hints, split_params
    from eurika.reasoning.graph_ops import (
        graph_hints_for_smell,
        suggest_facade_candidates,
        suggest_god_module_split_hint,
    )

    for smell in node_smells:
        graph_hints = graph_hints_for_smell(graph, smell.type, smell.nodes)
        for graph_hint in graph_hints:
            if graph_hint and graph_hint not in hints:
                hints.append(graph_hint)
    if action_kind == "split_module":
        info = suggest_god_module_split_hint(graph, name, top_n=5)
        split_params = {
            "imports_from": info.get("imports_from", []),
            "imported_by": info.get("imported_by", []),
        }
        llm_hints = _llm_split_hints(smell_type, name, info)
        for h in llm_hints:
            if h and h not in hints:
                hints.append(h)
    elif action_kind == "introduce_facade":
        callers = suggest_facade_candidates(graph, name, top_n=5)
        split_params = {"callers": callers} if callers else None
        llm_hints = _llm_split_hints(smell_type, name, {"callers": callers or []})
        for h in llm_hints:
            if h and h not in hints:
                hints.append(h)
    return hints, split_params


def _llm_split_hints(
    smell_type: str,
    name: str,
    graph_context: Dict[str, Any],
) -> List[str]:
    """Call Ollama for split hints when smell is god_module/hub/bottleneck (ROADMAP 2.9.2). Returns [] on failure."""
    try:
        from eurika.reasoning.planner_llm import ask_ollama_split_hints

        return ask_ollama_split_hints(smell_type, name, graph_context)
    except Exception:
        return []


def _append_default_refactor_operation(
    operations: List[PatchOperation],
    name: str,
    idx: int,
    desc_lines: List[str],
    smell_type: str,
    action_kind: str,
    node_smells: List[ArchSmell],
    *,
    graph: Optional["ProjectGraph"],
    oss_patterns: Optional[Dict[str, Any]] = None,
) -> None:
    """Build and append the default TODO refactor operation for a target."""
    hints, split_params = _build_hints_and_params(
        smell_type, action_kind, node_smells, name,
        graph=graph,
        oss_patterns=oss_patterns or {},
    )
    hint_lines = "\n".join((f"# - {hint}" for hint in hints))
    diff_hint = (
        f"# TODO: Refactor {name} ({smell_type} -> {action_kind})\n"
        f"# Suggested steps:\n{hint_lines}\n"
    )
    operations.append(
        PatchOperation(
            target_file=name,
            kind=action_kind,
            description=" ".join(desc_lines),
            diff=diff_hint,
            smell_type=smell_type,
            params=split_params,
        )
    )


def _operations_for_target(
    project_root: str,
    idx: int,
    target: Dict[str, Any],
    smells_by_node: Dict[str, List[ArchSmell]],
    cycles_handled: set[frozenset[str]],
    *,
    graph: Optional["ProjectGraph"],
    self_map: Optional[Dict[str, Any]],
    oss_patterns: Optional[Dict[str, Any]] = None,
) -> List[PatchOperation]:
    """Build patch operations for a single target module."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells

    name = target.get("name") or ""
    if not name:
        return []
    kind = target.get("kind") or "refactor_module"
    reasons = target.get("reasons") or []
    node_smells = smells_by_node.get(name, [])
    smell_types = [s.type for s in node_smells]
    if not kind or kind == "refactor_module":
        kind = refactor_kind_for_smells(smell_types)
    action_kind = STEP_KIND_TO_ACTION.get(kind, "refactor_module")
    smell_type = max(node_smells, key=lambda s: s.severity).type if node_smells else "unknown"
    desc_lines = [f"[{idx}] Refactor module {name} based on detected architecture smells."]
    if reasons:
        desc_lines.append("Reasons: " + ", ".join(reasons))

    operations: List[PatchOperation] = []
    if smell_type == "cyclic_dependency" and _maybe_add_cycle_break_operation(
        operations,
        node_smells,
        name,
        graph=graph,
        self_map=self_map,
        cycles_handled=cycles_handled,
    ):
        return operations
    if name in FACADE_MODULES and action_kind in ("split_module", "refactor_module"):
        return operations

    _maybe_add_extract_class_operation(
        operations, project_root, name, idx, smell_type, action_kind
    )
    _append_default_refactor_operation(
        operations, name, idx, desc_lines, smell_type, action_kind, node_smells,
        graph=graph,
        oss_patterns=oss_patterns or {},
    )
    return operations


def _should_emit_default_todo_op(
    project_root: str, target_file: str, kind: str, diff: str
) -> bool:
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


def _rebuild_operation_with_kind(op: PatchOperation, new_kind: str) -> PatchOperation:
    """Rebuild operation with a different kind and matching diff hints."""
    smell_type = op.smell_type or "unknown"
    hints = diff_hints_for(smell_type, new_kind)
    hint_lines = "\n".join((f"# - {hint}" for hint in hints))
    diff_hint = (
        f"# TODO: Refactor {op.target_file} ({smell_type} -> {new_kind})\n"
        f"# Suggested steps:\n{hint_lines}\n"
    )
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
    min_total_for_filter = 3
    min_success_rate = 0.25
    operations = [
        op
        for op in operations
        if _should_emit_default_todo_op(project_root, op.target_file, op.kind, op.diff)
    ]
    if not learning_stats:
        disabled_smell_actions = disabled_smell_actions_from_env()
        if disabled_smell_actions:
            operations = [
                op
                for op in operations
                if f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
                not in disabled_smell_actions
            ]
        return operations
    filtered: List[PatchOperation] = []
    for op in operations:
        key = f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
        stats = learning_stats.get(key, {})
        total = stats.get("total", 0)
        if total >= min_total_for_filter:
            rate = (stats.get("success", 0) or 0) / total
            if rate < min_success_rate:
                fallback = fallback_kind_for_low_success(op.smell_type or "unknown", op.kind)
                if fallback:
                    op = _rebuild_operation_with_kind(op, fallback)
                else:
                    continue
        filtered.append(op)
    disabled_smell_actions = disabled_smell_actions_from_env()
    if disabled_smell_actions:
        filtered = [
            op
            for op in filtered
            if f"{op.smell_type or 'unknown'}{SMELL_ACTION_SEP}{op.kind}"
            not in disabled_smell_actions
        ]
    return filtered


def _sort_and_reindex_by_learning(
    operations: List[PatchOperation],
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
) -> List[PatchOperation]:
    """Sort operations by historical success rate and normalize index prefix."""
    if not learning_stats:
        return operations
    ordered = sorted(
        operations, key=lambda op: _success_rate_for_op(op, learning_stats), reverse=True
    )
    reindexed: List[PatchOperation] = []
    for idx, op in enumerate(ordered, start=1):
        desc = op.description
        if desc.startswith("["):
            rest = desc.split("]", 1)[-1].lstrip()
            reindexed.append(
                PatchOperation(
                    target_file=op.target_file,
                    kind=op.kind,
                    description=f"[{idx}] {rest}",
                    diff=op.diff,
                    smell_type=op.smell_type,
                    params=op.params,
                )
            )
        else:
            reindexed.append(op)
    return reindexed


# TODO (eurika): refactor long_function '_build_hints_and_params' — consider extracting helper


# TODO (eurika): refactor deep_nesting '_build_hints_and_params' — consider extracting nested block
