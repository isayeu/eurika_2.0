"""Application layer entry: run_cycle, run_doctor_cycle, run_fix_cycle, run_full_cycle (P0.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import load_fix_cycle_deps
from .contracts import OperationRecord, PatchPlan
from .deps import FixCycleDeps
from .apply_stage import (
    build_fix_dry_run_result,
    attach_fix_telemetry,
    build_fix_cycle_result,
    execute_fix_apply_stage,
)
from .doctor import knowledge_topics_from_env_or_summary, run_doctor_cycle as _run_doctor_cycle
from .full_cycle import run_cycle_entry, run_full_cycle as _run_full_cycle_impl
from .fix_cycle_impl import run_fix_cycle_impl
from .hybrid_approval import select_hybrid_operations
from .prepare import prepare_fix_cycle_operations

__all__ = ["run_cycle", "run_doctor_cycle", "run_fix_cycle", "run_full_cycle"]


def run_doctor_cycle(path: Path, *, window: int = 5, no_llm: bool = False, online: bool = False, quiet: bool = False) -> dict[str, Any]:
    return _run_doctor_cycle(path, window=window, no_llm=no_llm, online=online, quiet=quiet)


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
    allow_low_risk_campaign: bool = False,
    run_scan: Any,
) -> tuple[dict[str, Any] | None, Any, PatchPlan | None, list[OperationRecord]]:
    return prepare_fix_cycle_operations(
        path,
        runtime_mode=runtime_mode,
        session_id=session_id,
        window=window,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        allow_campaign_retry=allow_campaign_retry,
        allow_low_risk_campaign=allow_low_risk_campaign,
        run_scan=run_scan,
    )


def run_fix_cycle(
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
    allow_low_risk_campaign: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    deps: Callable[[], FixCycleDeps] = load_fix_cycle_deps
    return run_fix_cycle_impl(
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
        allow_low_risk_campaign=allow_low_risk_campaign,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
        fix_cycle_deps=deps,
        prepare_fix_cycle_operations=_prepare_fix_cycle_operations,
        select_hybrid_operations=select_hybrid_operations,
        build_fix_dry_run_result=build_fix_dry_run_result,
        attach_fix_telemetry=attach_fix_telemetry,
        build_fix_cycle_result=build_fix_cycle_result,
        execute_fix_apply_stage=execute_fix_apply_stage,
    )


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
    allow_low_risk_campaign: bool = False,
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    return _run_full_cycle_impl(
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
        allow_low_risk_campaign=allow_low_risk_campaign,
        online=online,
        run_doctor_cycle_fn=run_doctor_cycle,
        run_fix_cycle_fn=run_fix_cycle,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
    )


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
    allow_low_risk_campaign: bool = False,
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    approve_ops: str | None = None,
    reject_ops: str | None = None,
) -> dict[str, Any]:
    return run_cycle_entry(
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
        allow_low_risk_campaign=allow_low_risk_campaign,
        online=online,
        team_mode=team_mode,
        apply_approved=apply_approved,
        approve_ops=approve_ops,
        reject_ops=reject_ops,
        run_doctor_cycle_fn=run_doctor_cycle,
        run_fix_cycle_fn=run_fix_cycle,
        run_full_cycle_fn=run_full_cycle,
    )
