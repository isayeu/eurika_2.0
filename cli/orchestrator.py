"""Orchestrator: single entry point for doctor and fix cycles (ROADMAP 2.3.1, 2.3.2).

run_cycle(path, mode="doctor"|"fix", ...) — единая точка входа.
run_doctor_cycle and run_fix_cycle encapsulate scan → diagnose → plan → patch → verify.
EurikaOrchestrator — формальный класс (review.md Part 1), делегирует run_cycle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from cli.orchestration import FixCycleContext, load_fix_cycle_deps
from cli.orchestration.apply_stage import (
    attach_fix_telemetry as _apply_attach_fix_telemetry,
    build_fix_cycle_result as _apply_build_fix_cycle_result,
    execute_fix_apply_stage as _apply_execute_fix_apply_stage,
)
from cli.orchestration.doctor import (
    knowledge_topics_from_env_or_summary as _doctor_knowledge_topics_from_env_or_summary,
    run_doctor_cycle as _doctor_run_doctor_cycle,
)
from cli.orchestration.full_cycle import run_full_cycle as _full_run_full_cycle
from cli.orchestration.prepare import (
    prepare_fix_cycle_operations as _prepare_prepare_fix_cycle_operations,
)


class EurikaOrchestrator:
    """Formal orchestrator (review.md Part 1). Single responsibility for Scan → Diagnose → Plan → Patch → Verify → Log.

    Wraps run_cycle; provides OOP interface. LLM=strategist, PatchEngine=executor, Orchestrator=center.
    """

    def run(
        self,
        target_path: Path,
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
    ) -> dict[str, Any]:
        """Execute cycle. mode: 'doctor' | 'fix' | 'full'."""
        return run_cycle(
            target_path,
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
        )


def _knowledge_topics_from_env_or_summary(summary: Any) -> list:
    """Compatibility wrapper; delegated to orchestration.doctor."""
    return _doctor_knowledge_topics_from_env_or_summary(summary)


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
) -> dict[str, Any]:
    """Единая точка входа: mode='doctor' | 'fix' | 'full'."""
    path = Path(path).resolve()
    if runtime_mode not in {"assist", "hybrid", "auto"}:
        return {"error": f"Unknown runtime_mode: {runtime_mode}. Use 'assist', 'hybrid', or 'auto'."}

    def _run_cycle_impl() -> dict[str, Any]:
        if mode == "doctor":
            return run_doctor_cycle(path, window=window, no_llm=no_llm)
        if mode == "fix":
            return run_fix_cycle(path, runtime_mode=runtime_mode, non_interactive=non_interactive, session_id=session_id, window=window, dry_run=dry_run, quiet=quiet, no_clean_imports=no_clean_imports, no_code_smells=no_code_smells, verify_cmd=verify_cmd)
        if mode == "full":
            return run_full_cycle(path, runtime_mode=runtime_mode, non_interactive=non_interactive, session_id=session_id, window=window, dry_run=dry_run, quiet=quiet, no_llm=no_llm, no_clean_imports=no_clean_imports, no_code_smells=no_code_smells, verify_cmd=verify_cmd)
        return {"error": f"Unknown mode: {mode}. Use 'doctor', 'fix', or 'full'."}

    if runtime_mode == "assist":
        return _run_cycle_impl()

    from eurika.agent.runtime import run_agent_cycle
    from eurika.agent.tools import OrchestratorToolset

    cycle = run_agent_cycle(
        mode=runtime_mode,
        tools=OrchestratorToolset(path=path, mode=mode, cycle_runner=_run_cycle_impl),
    )
    out = cycle.payload if isinstance(cycle.payload, dict) else {"error": "agent runtime returned invalid payload"}
    out.setdefault("agent_runtime", {"mode": runtime_mode, "stages": cycle.stages})
    return out


def run_doctor_cycle(
    path: Path,
    *,
    window: int = 5,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper; delegated to orchestration.doctor."""
    return _doctor_run_doctor_cycle(path, window=window, no_llm=no_llm)


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
        run_doctor_cycle_fn=run_doctor_cycle,
        run_fix_cycle_fn=run_fix_cycle,
    )


def _build_fix_dry_run_result(path: Path, patch_plan: dict[str, Any], operations: list[dict[str, Any]], result: Any) -> dict[str, Any]:
    """Build and persist dry-run report/result payload."""
    report = {"dry_run": True, "patch_plan": patch_plan, "modified": [], "verify": {"success": None}}
    try:
        (path / "eurika_fix_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
    return {
        "return_code": 0,
        "report": report,
        "operations": operations,
        "modified": [],
        "verify_success": None,
        "agent_result": result,
        "dry_run": True,
    }


def _select_hybrid_operations(
    operations: list[dict[str, Any]],
    *,
    quiet: bool,
    non_interactive: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Interactive approval flow for hybrid mode."""
    if non_interactive or not operations or quiet or not sys.stdin.isatty():
        return operations, []
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        kind = op.get("kind", "?")
        target = op.get("target_file", "?")
        risk = (op.get("explainability") or {}).get("risk", "unknown")
        prompt = (
            f"[{idx}/{len(operations)}] {kind} -> {target} (risk={risk}) "
            "[a]pprove/[r]eject/[A]ll approve/[R]eject rest/[s]kip prompt: "
        )
        while True:
            choice = input(prompt).strip() or "a"
            if choice in {"a", "r", "A", "R", "s"}:
                break
            print("Use one of: a, r, A, R, s", file=sys.stderr)
        if choice == "a":
            approved.append(op)
        elif choice == "r":
            rejected.append(op)
        elif choice == "A":
            approved.append(op)
            approved.extend(operations[idx:])
            break
        elif choice == "R":
            rejected.append(op)
            rejected.extend(operations[idx:])
            break
        elif choice == "s":
            approved.append(op)
    return approved, rejected


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
        run_scan=run_scan,
    )


def _fix_cycle_deps() -> dict[str, Any]:
    """Compatibility shim for tests; delegates to orchestration deps loader."""
    return load_fix_cycle_deps()


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
) -> dict[str, Any]:
    """Run full fix cycle: scan → diagnose → plan → patch → verify."""
    return _run_fix_cycle_impl(
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
) -> dict[str, Any]:
    """Implementation for run_fix_cycle. Persists report and memory events."""
    _ = FixCycleContext(
        path=path,
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
    )
    deps = _fix_cycle_deps()
    run_scan = deps["run_scan"]

    early, result, patch_plan, operations = _prepare_fix_cycle_operations(
        path,
        runtime_mode=runtime_mode,
        session_id=session_id,
        window=window,
        quiet=quiet,
        skip_scan=skip_scan,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        run_scan=run_scan,
    )
    if early is not None:
        if isinstance(early, dict) and isinstance(early.get("report"), dict):
            _apply_attach_fix_telemetry(early["report"], early.get("operations", []))
        return early

    approved_ops, rejected_ops = _select_hybrid_operations(
        operations,
        quiet=quiet,
        non_interactive=non_interactive or runtime_mode != "hybrid",
    )
    if rejected_ops and session_id:
        from eurika.storage import SessionMemory

        SessionMemory(path).record(session_id, approved=approved_ops, rejected=rejected_ops)
    operations = approved_ops
    patch_plan = dict(patch_plan, operations=operations)
    if not operations:
        rejected_files = [str(op.get("target_file", "")) for op in rejected_ops if op.get("target_file")]
        report = {
            "message": "All operations rejected by user/policy. Cycle complete.",
            "policy_decisions": result.output.get("policy_decisions", []),
            "operation_explanations": [],
            "skipped": rejected_files,
        }
        _apply_attach_fix_telemetry(report, approved_ops)
        return {
            "return_code": 0,
            "report": report,
            "operations": [],
            "modified": [],
            "verify_success": True,
            "agent_result": result,
            "dry_run": dry_run,
        }

    if dry_run:
        if not quiet:
            print("--- Step 3/3: plan (dry-run, no apply) ---", file=sys.stderr)
        out = _build_fix_dry_run_result(path, patch_plan, operations, result)
        out["report"]["operation_explanations"] = [op.get("explainability", {}) for op in operations]
        out["report"]["policy_decisions"] = result.output.get("policy_decisions", [])
        _apply_attach_fix_telemetry(out["report"], operations)
        return out
    report, modified, verify_success = _apply_execute_fix_apply_stage(
        path, patch_plan, operations,
        quiet=quiet, verify_cmd=verify_cmd, backup_dir=deps["BACKUP_DIR"],
        apply_and_verify=deps["apply_and_verify"], run_scan=run_scan,
        build_snapshot_from_self_map=deps["build_snapshot_from_self_map"],
        diff_architecture_snapshots=deps["diff_architecture_snapshots"],
        metrics_from_graph=deps["metrics_from_graph"], rollback_patch=deps["rollback_patch"],
        result=result,
    )
    return _apply_build_fix_cycle_result(report, operations, modified, verify_success, result)

# TODO: Refactor cli/orchestrator.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: agent_core.py, agent_core_arch_review.py, patch_apply.py.
