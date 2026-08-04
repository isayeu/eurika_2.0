#!/usr/bin/env python3
"""
Record learning outcomes from manual diff review session (2026-03).

All ops below were reviewed and REJECTED — extraction caused NameError or semantic bugs.
Run from project root: python scripts/record_extraction_review_outcomes.py

Planner uses get_recent_failures → deprioritize similar (target_file, kind, failure_reason).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# extract_scope_error: extracted helper uses closure/outer vars without passing as params
EXTRACT_SCOPE_ERROR = [
    {"target_file": "eurika/api/task_executor_patch.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/chat_vector.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/reasoning/architect.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/reasoning/context_sources.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/reasoning/risk_prediction.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/storage/global_memory.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/storage/operational_metrics.py", "kind": "extract_block_to_helper"},
    {"target_file": "cli/core_handlers_doctor.py", "kind": "extract_block_to_helper"},
    {"target_file": "cli/core_handlers_learn.py", "kind": "extract_block_to_helper"},
    {"target_file": "cli/core_handlers_report.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/chat_context.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/chat_handlers.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/chat_rag.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/chat_utils.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/learning_api.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/roadmap_verify.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/checks/dependency_firewall.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/learning/pattern_library.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/apply_stage.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/fix_cycle_impl.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/full_cycle.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/prepare.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/fix_cycle_helpers.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/hybrid_approval.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/reasoning/planner/hints_provider.py", "kind": "extract_block_to_helper"},
]

# extract_operator_precedence_bug: removed parentheses changed semantics (used - assigned & params)
EXTRACT_PRECEDENCE_BUG = [
    {"target_file": "eurika/refactor/extract_function.py", "kind": "extract_block_to_helper"},
]

# extract_qt_slot_signature_mismatch: Qt slot extracted without binding closure args
EXTRACT_QT_SLOT_MISMATCH = [
    {"target_file": "qt_app/ui/tabs/terminal_tab.py", "kind": "extract_block_to_helper"},
    {"target_file": "qt_app/ui/tabs/approve_tab.py", "kind": "extract_block_to_helper"},
]

# extract_missing_return: extracted block computes values but doesn't return/pass to caller
EXTRACT_MISSING_RETURN = [
    {"target_file": "eurika/api/chat_handlers.py", "kind": "extract_block_to_helper"},
]

# extract_delegation_broken: delegation loses args (info not passed) or wrong import path
EXTRACT_DELEGATION_BROKEN = [
    {"target_file": "code_awareness.py", "kind": "extract_block_to_helper"},
]

# human_rejected: user marked reject in Approvals UI (batch 2026-03)
HUMAN_REJECTED = [
    {"target_file": "eurika/api/chat.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/orchestration/apply_stage.py", "kind": "extract_block_to_helper"},
    {"target_file": "eurika/api/task_executor_executors.py", "kind": "extract_block_to_helper"},
]


def main() -> None:
    from eurika.storage import record_outcome

    # Scope errors: NameError on outer vars (kept, op_with_meta, node, out, rejected, etc.)
    record_outcome(
        ROOT,
        [op["target_file"] for op in EXTRACT_SCOPE_ERROR],
        EXTRACT_SCOPE_ERROR,
        [],
        verify_success=False,
        failure_reason="extract_scope_error",
    )
    print(f"Recorded: {len(EXTRACT_SCOPE_ERROR)} extract_scope_error (closure vars not passed)")

    # Precedence: (used - assigned) & params vs used - assigned & params
    record_outcome(
        ROOT,
        [op["target_file"] for op in EXTRACT_PRECEDENCE_BUG],
        EXTRACT_PRECEDENCE_BUG,
        [],
        verify_success=False,
        failure_reason="extract_operator_precedence_bug",
    )
    print(f"Recorded: {len(EXTRACT_PRECEDENCE_BUG)} extract_operator_precedence_bug")

    # Qt slot: readyReadStandardOutput.connect(_on_stdout) — slot needs lambda to bind args
    record_outcome(
        ROOT,
        [op["target_file"] for op in EXTRACT_QT_SLOT_MISMATCH],
        EXTRACT_QT_SLOT_MISMATCH,
        [],
        verify_success=False,
        failure_reason="extract_qt_slot_signature_mismatch",
    )
    print(f"Recorded: {len(EXTRACT_QT_SLOT_MISMATCH)} extract_qt_slot_signature_mismatch")

    # extract_missing_return: block computes output/ok/exit_code but caller never receives them
    record_outcome(
        ROOT,
        [op["target_file"] for op in EXTRACT_MISSING_RETURN],
        EXTRACT_MISSING_RETURN,
        [],
        verify_success=False,
        failure_reason="extract_missing_return",
    )
    print(f"Recorded: {len(EXTRACT_MISSING_RETURN)} extract_missing_return")

    # extract_delegation_broken: delegation loses args (info not passed), wrong import path
    record_outcome(
        ROOT,
        [op["target_file"] for op in EXTRACT_DELEGATION_BROKEN],
        EXTRACT_DELEGATION_BROKEN,
        [],
        verify_success=False,
        failure_reason="extract_delegation_broken",
    )
    print(f"Recorded: {len(EXTRACT_DELEGATION_BROKEN)} extract_delegation_broken")

    # Human rejected in Approvals UI (reject + Run apply-approved)
    record_outcome(
        ROOT,
        [op["target_file"] for op in HUMAN_REJECTED],
        HUMAN_REJECTED,
        [],
        verify_success=False,
        failure_reason="human_rejected",
    )
    print(f"Recorded: {len(HUMAN_REJECTED)} human_rejected")

    total = (
        len(EXTRACT_SCOPE_ERROR)
        + len(EXTRACT_PRECEDENCE_BUG)
        + len(EXTRACT_QT_SLOT_MISMATCH)
        + len(EXTRACT_MISSING_RETURN)
        + len(EXTRACT_DELEGATION_BROKEN)
        + len(HUMAN_REJECTED)
    )
    print(f"Total: {total} extraction failures for planner deprioritization")


if __name__ == "__main__":
    main()
