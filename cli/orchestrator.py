"""CLI orchestrator: thin re-export from eurika.orchestration (P0.2)."""

from __future__ import annotations

from eurika.orchestration.entry import run_cycle, run_doctor_cycle, run_fix_cycle, run_full_cycle
from eurika.orchestration.facade import EurikaOrchestrator
from eurika.orchestration import load_fix_cycle_deps
from eurika.orchestration.contracts import OperationRecord, PatchPlan
from eurika.orchestration.deps import FixCycleDeps

__all__ = [
    "EurikaOrchestrator",
    "run_cycle",
    "run_doctor_cycle",
    "run_full_cycle",
    "run_fix_cycle",
    "OperationRecord",
    "PatchPlan",
    "FixCycleDeps",
    "load_fix_cycle_deps",
]

# Backward-compatible aliases for tests/monkeypatch (import paths).
from eurika.orchestration.prepare import prepare_fix_cycle_operations as _prepare_prepare_fix_cycle_operations
from eurika.orchestration.doctor import (
    knowledge_topics_from_env_or_summary as _knowledge_topics_from_env_or_summary,
    load_suggested_policy_for_apply,
)
from eurika.orchestration.apply_stage import (
    build_fix_dry_run_result as _build_fix_dry_run_result,
    attach_fix_telemetry as _apply_attach_fix_telemetry,
    build_fix_cycle_result as _apply_build_fix_cycle_result,
    append_fix_cycle_memory,
)
from eurika.orchestration.hybrid_approval import select_hybrid_operations as _select_hybrid_operations

_prepare_prepare_fix_cycle_operations = _prepare_prepare_fix_cycle_operations
_knowledge_topics_from_env_or_summary = _knowledge_topics_from_env_or_summary
_build_fix_dry_run_result = _build_fix_dry_run_result
_select_hybrid_operations = _select_hybrid_operations
_fix_cycle_deps = load_fix_cycle_deps
