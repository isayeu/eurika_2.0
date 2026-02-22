"""Orchestrator: single entry point for doctor and fix cycles (ROADMAP 2.3.1, 2.3.2).

run_cycle(path, mode="doctor"|"fix", ...) — единая точка входа.
run_doctor_cycle and run_fix_cycle encapsulate scan → diagnose → plan → patch → verify.
EurikaOrchestrator — формальный класс (review.md Part 1), делегирует run_cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.orchestration import load_fix_cycle_deps
from cli.orchestration.apply_stage import (
    build_fix_dry_run_result as _apply_build_fix_dry_run_result,
    attach_fix_telemetry as _apply_attach_fix_telemetry,
    build_fix_cycle_result as _apply_build_fix_cycle_result,
    execute_fix_apply_stage as _apply_execute_fix_apply_stage,
)
from cli.orchestration.doctor import (
    knowledge_topics_from_env_or_summary as _doctor_knowledge_topics_from_env_or_summary,
    run_doctor_cycle as _doctor_run_doctor_cycle,
)
from cli.orchestration.full_cycle import (
    run_cycle_entry as _full_run_cycle_entry,
    run_full_cycle as _full_run_full_cycle,
)
from cli.orchestration.fix_cycle_impl import run_fix_cycle_impl as _fix_impl_run_fix_cycle_impl
from cli.orchestration.facade import EurikaOrchestrator
from cli.orchestration.hybrid_approval import (
    select_hybrid_operations as _hybrid_select_hybrid_operations,
)
from cli.orchestration.prepare import (
    prepare_fix_cycle_operations as _prepare_fix_cycle_operations_impl,
)

# Public API exports (also protects re-exports from unused-import cleanup).
__all__ = [
    "EurikaOrchestrator",
    "run_cycle",
    "run_doctor_cycle",
    "run_full_cycle",
    "run_fix_cycle",
]

# Backward-compatible aliases for tests/monkeypatch hooks.
_prepare_prepare_fix_cycle_operations = _prepare_fix_cycle_operations_impl
_knowledge_topics_from_env_or_summary = _doctor_knowledge_topics_from_env_or_summary
_build_fix_dry_run_result = _apply_build_fix_dry_run_result
_select_hybrid_operations = _hybrid_select_hybrid_operations
_fix_cycle_deps = load_fix_cycle_deps


def run_cycle(
    path: Path,
    mode: str = "fix",
    *,
    runtime_mode: str = "assist",
    non_interactive: bool = False,
    session_id: str | None = None,
    window: int = 5,
    dry_run: bool = False,
    quiet: bool = False,
    no_llm: bool = False,
    no_clean_imports: bool = False,
    no_code_smells: bool = False,
    verify_cmd: str | None = None,
    verify_timeout: int | None = None,
    allow_campaign_retry: bool = False,
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    """Единая точка входа: mode='doctor' | 'fix' | 'full'."""
    return _full_run_cycle_entry(
        path,
        mode=mode,
        runtime_mode=runtime_mode,
        non_interactive=non_interactive,
        session_id=session_id,
        window=window,
        dry_run=dry_run,
        quiet=quiet,
        no_llm=no_llm,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        allow_campaign_retry=allow_campaign_retry,
        online=online,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
        run_doctor_cycle_fn=run_doctor_cycle,
        run_fix_cycle_fn=run_fix_cycle,
        run_full_cycle_fn=run_full_cycle,
    )


def run_doctor_cycle(
    path: Path,
    *,
    window: int = 5,
    no_llm: bool = False,
    online: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper; delegated to orchestration.doctor."""
    return _doctor_run_doctor_cycle(path, window=window, no_llm=no_llm, online=online)


def run_full_cycle(
    path: Path,
    *,
    runtime_mode: str = "assist",
    non_interactive: bool = False,
    session_id: str | None = None,
    window: int = 5,
    dry_run: bool = False,
    quiet: bool = False,
    no_llm: bool = False,
    no_clean_imports: bool = False,
    no_code_smells: bool = False,
    verify_cmd: str | None = None,
    verify_timeout: int | None = None,
    allow_campaign_retry: bool = False,
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper; delegated to orchestration.full_cycle."""
    return _full_run_full_cycle(
        path,
        runtime_mode=runtime_mode,
        non_interactive=non_interactive,
        session_id=session_id,
        window=window,
        dry_run=dry_run,
        quiet=quiet,
        no_llm=no_llm,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        allow_campaign_retry=allow_campaign_retry,
        online=online,
        run_doctor_cycle_fn=run_doctor_cycle,
        run_fix_cycle_fn=run_fix_cycle,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
    )


def _prepare_fix_cycle_operations(
    path: Path,
    *,
    runtime_mode: str,
    session_id: str | None,
    window: int,
    quiet: bool,
    skip_scan: bool,
    no_clean_imports: bool,
    no_code_smells: bool,
    allow_campaign_retry: bool = False,
    run_scan: Any,
) -> tuple[dict[str, Any] | None, Any, dict[str, Any] | None, list[dict[str, Any]]]:
    """Compatibility wrapper; delegated to orchestration.prepare."""
    return _prepare_prepare_fix_cycle_operations(
        path,
        runtime_mode=runtime_mode,
        session_id=session_id,
        window=window,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        allow_campaign_retry=allow_campaign_retry,
        run_scan=run_scan,
    )


def _run_fix_cycle_impl(
    path: Path,
    *,
    runtime_mode: str = "assist",
    non_interactive: bool = False,
    session_id: str | None = None,
    window: int = 5,
    dry_run: bool = False,
    quiet: bool = False,
    skip_scan: bool = False,
    no_clean_imports: bool = False,
    no_code_smells: bool = False,
    verify_cmd: str | None = None,
    verify_timeout: int | None = None,
    allow_campaign_retry: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    """Implementation for run_fix_cycle. Persists report and memory events."""
    return _fix_impl_run_fix_cycle_impl(
        path,
        runtime_mode=runtime_mode,
        non_interactive=non_interactive,
        session_id=session_id,
        window=window,
        dry_run=dry_run,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        allow_campaign_retry=allow_campaign_retry,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
        fix_cycle_deps=_fix_cycle_deps,
        prepare_fix_cycle_operations=_prepare_fix_cycle_operations,
        select_hybrid_operations=_select_hybrid_operations,
        build_fix_dry_run_result=_build_fix_dry_run_result,
        attach_fix_telemetry=_apply_attach_fix_telemetry,
        build_fix_cycle_result=_apply_build_fix_cycle_result,
        execute_fix_apply_stage=_apply_execute_fix_apply_stage,
    )


# Public compatibility alias.
run_fix_cycle = _run_fix_cycle_impl

