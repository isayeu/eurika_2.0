"""
Filter policy: learning_stats, env disabled, low-success fallback (review §2).

Separate service for filtering and sorting operations before output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from eurika.reasoning.planner.heuristics import (
    SMELL_ACTION_SEP,
    diff_hints_for,
    disabled_smell_actions_from_env,
    fallback_kind_for_low_success,
)
from patch_plan import PatchOperation


def _success_rate_for_op(
    op: PatchOperation,
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
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


def _rebuild_operation_with_kind(op: PatchOperation, new_kind: str) -> PatchOperation:
    """Rebuild operation with a different kind and matching diff hints."""
    smell_type = op.smell_type or "unknown"
    hints = diff_hints_for(smell_type, new_kind)
    hint_lines = "\n".join((f"# - {hint}" for hint in hints))
    diff_hint = (
        f"# TODO: Refactor {op.target_file} ({smell_type} -> {new_kind})\n"
        f"# Suggested steps:\n{hint_lines}\n"
    )
    params = (
        op.params
        if new_kind not in ("refactor_module", "refactor_code_smell")
        else None
    )
    return PatchOperation(
        target_file=op.target_file,
        kind=new_kind,
        description=op.description,
        diff=diff_hint,
        smell_type=op.smell_type,
        params=params,
    )


def _should_emit_default_todo_op(
    project_root: str, target_file: str, kind: str, diff: str
) -> bool:
    """
    Return False when default append-style TODO is already present in target file.
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


def apply_failure_based_fallback(
    operations: List[PatchOperation],
    kind_plan_counts: dict[tuple[str, str], int],
    min_failures_for_fallback: int = 2,
) -> List[PatchOperation]:
    """When (kind, plan_hash) failed min_failures_for_fallback+ times, swap to fallback kind."""
    result: List[PatchOperation] = []
    for op in operations:
        k = op.kind or ""
        fail_count = sum(c for (kk, _), c in kind_plan_counts.items() if kk == k)
        if fail_count >= min_failures_for_fallback:
            fallback = fallback_kind_for_low_success(op.smell_type or "unknown", k)
            if fallback:
                op = _rebuild_operation_with_kind(op, fallback)
        result.append(op)
    return result


def apply_smell_action_filters(
    project_root: str,
    operations: List[PatchOperation],
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
) -> List[PatchOperation]:
    """Apply env-based disabling and low-success filtering (review §2)."""
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
                fallback = fallback_kind_for_low_success(
                    op.smell_type or "unknown", op.kind
                )
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


_DEPRIORITIZE_REASONS = frozenset((
    "metrics_worsened",
    "simulation_errors",
    "verify_failed",
    # Extraction review reject 2026-03 — planner deprioritize (extraction-lessons.mdc)
    "extract_scope_error",
    "extract_block_broken_scope",
    "extract_operator_precedence_bug",
    "extract_qt_slot_signature_mismatch",
    "extract_missing_return",
    "extract_delegation_broken",
    "extract_top_level_module",
    "human_rejected",
))


def _is_recent_failure(
    op: PatchOperation,
    recent_failures: Sequence[Tuple[str, str, str]],
) -> bool:
    """True if (target_file, kind) matches a recent failure with deprioritize reason."""
    if not recent_failures:
        return False
    fail_set = {
        (tf, k)
        for tf, k, reason in recent_failures
        if reason in _DEPRIORITIZE_REASONS
    }
    return (op.target_file or "", op.kind or "") in fail_set


def _is_recent_failure_by_kind_plan(
    op: PatchOperation,
    plan_hash: str,
    failed_kind_plan_pairs: frozenset[tuple[str, str]],
) -> bool:
    """True if (kind, plan_hash) failed — deprioritize when retrying same plan."""
    if not plan_hash or not failed_kind_plan_pairs:
        return False
    return (op.kind or "", plan_hash) in failed_kind_plan_pairs


def _failure_penalty_weight(
    op: PatchOperation,
    plan_hash: str,
    kind_plan_counts: Optional[dict[tuple[str, str], int]],
) -> int:
    """0 = no penalty, 1 = single failure, 2 = repeated (count >= 2)."""
    if not kind_plan_counts:
        return 0
    count = kind_plan_counts.get((op.kind or "", plan_hash), 0)
    return 2 if count >= 2 else (1 if count >= 1 else 0)


def sort_and_reindex_by_learning(
    operations: List[PatchOperation],
    learning_stats: Optional[Dict[str, Dict[str, Any]]],
    *,
    recent_failures: Optional[Sequence[Tuple[str, str, str]]] = None,
    failed_kind_plan_pairs: Optional[frozenset[tuple[str, str]]] = None,
    plan_hash: Optional[str] = None,
    kind_plan_counts: Optional[dict[tuple[str, str], int]] = None,
) -> List[PatchOperation]:
    """Sort operations by historical success rate; deprioritize by (target_file,kind) and (kind,plan_hash)."""
    recent_failures = recent_failures or ()
    failed_kind_plan_pairs = failed_kind_plan_pairs or frozenset()
    plan_hash = plan_hash or ""
    kind_plan_counts = kind_plan_counts or {}
    if not learning_stats and not recent_failures and not failed_kind_plan_pairs:
        return operations
    has_tf_kind_fail = _is_recent_failure

    def has_kind_plan_fail(op: PatchOperation) -> bool:
        return _is_recent_failure_by_kind_plan(op, plan_hash, failed_kind_plan_pairs)

    def penalty(op: PatchOperation) -> float:
        return _failure_penalty_weight(op, plan_hash, kind_plan_counts)

    ordered = sorted(
        operations,
        key=lambda op: (
            penalty(op),
            has_tf_kind_fail(op, recent_failures),
            has_kind_plan_fail(op),
            -_success_rate_for_op(op, learning_stats),
        ),
        reverse=False,
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
