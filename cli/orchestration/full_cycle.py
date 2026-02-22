"""Full-cycle wiring helper for orchestration layer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


def _build_agent_runtime_payload(mode: str, cycle: Any) -> dict[str, Any]:
    """Normalize agent runtime metadata for API/report surfaces."""
    stage_outputs = (
        cycle.stage_outputs
        if isinstance(getattr(cycle, "stage_outputs", None), dict)
        else {}
    )
    degraded_reasons = [
        str(v.get("message") or f"{k}:error")
        for k, v in stage_outputs.items()
        if isinstance(v, dict) and v.get("status") == "error"
    ]
    state = getattr(cycle, "state", None)
    state_history = getattr(cycle, "state_history", None)
    state_value = str(getattr(state, "value", state)) if state is not None else None
    history_values = []
    if isinstance(state_history, list):
        history_values = [str(getattr(s, "value", s)) for s in state_history]
    return {
        "mode": mode,
        "stages": list(getattr(cycle, "stages", []) or []),
        "state": state_value,
        "state_history": history_values,
        "degraded_mode": bool(state_value == "error"),
        "degraded_reasons": degraded_reasons,
    }


def run_cycle_entry(
    path: Path,
    *,
    mode: str = "fix",
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
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    run_doctor_cycle_fn: Callable[..., dict[str, Any]],
    run_fix_cycle_fn: Callable[..., dict[str, Any]],
    run_full_cycle_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run doctor/fix/full mode with optional agent runtime wrapper."""
    path = Path(path).resolve()
    if runtime_mode not in {"assist", "hybrid", "auto"}:
        return {"error": f"Unknown runtime_mode: {runtime_mode}. Use 'assist', 'hybrid', or 'auto'."}

    def _run_cycle_impl() -> dict[str, Any]:
        if mode == "doctor":
            return run_doctor_cycle_fn(path, window=window, no_llm=no_llm, online=online)
        if mode == "fix":
            return run_fix_cycle_fn(
                path,
                runtime_mode=runtime_mode,
                non_interactive=non_interactive,
                session_id=session_id,
                window=window,
                dry_run=dry_run,
                quiet=quiet,
                no_clean_imports=no_clean_imports,
                no_code_smells=no_code_smells,
                verify_cmd=verify_cmd,
                verify_timeout=verify_timeout,
                team_mode=team_mode,
                apply_approved=apply_approved,
            )
        if mode == "full":
            return run_full_cycle_fn(
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
                online=online,
                team_mode=team_mode,
                apply_approved=apply_approved,
            )
        return {"error": f"Unknown mode: {mode}. Use 'doctor', 'fix', or 'full'."}

    if runtime_mode == "assist":
        return _run_cycle_impl()

    from eurika.agent.runtime import run_agent_cycle
    from eurika.agent.tool_contract import DefaultToolContract
    from eurika.agent.tools import OrchestratorToolset

    contract = DefaultToolContract()
    cycle = run_agent_cycle(
        mode=runtime_mode,
        tools=OrchestratorToolset(
            path=path,
            mode=mode,
            cycle_runner=_run_cycle_impl,
            contract=contract,
        ),
    )
    out = (
        cycle.payload
        if isinstance(cycle.payload, dict)
        else {"error": "agent runtime returned invalid payload"}
    )
    out.setdefault("agent_runtime", _build_agent_runtime_payload(runtime_mode, cycle))
    report = out.get("report")
    if isinstance(report, dict):
        report.setdefault(
            "runtime",
            {
                "degraded_mode": bool(out["agent_runtime"].get("degraded_mode")),
                "degraded_reasons": list(out["agent_runtime"].get("degraded_reasons", [])),
                "state": out["agent_runtime"].get("state"),
                "mode": runtime_mode,
            },
        )
    return out


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
    online: bool = False,
    team_mode: bool = False,
    apply_approved: bool = False,
    run_doctor_cycle_fn: Callable[..., dict[str, Any]],
    run_fix_cycle_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run scan → doctor (full report) → fix. Single command for the full ritual (ROADMAP 3.0.3: --online)."""
    from eurika.smells.rules import summary_to_text
    from runtime_scan import run_scan

    if not quiet:
        print("eurika cycle: scan → doctor → fix", file=sys.stderr)
    if run_scan(path) != 0:
        return {"return_code": 1, "report": {}, "operations": [], "modified": [], "verify_success": False, "agent_result": None}
    data = run_doctor_cycle_fn(path, window=window, no_llm=no_llm, online=online)
    if data.get("error"):
        return {"return_code": 1, "report": data, "operations": [], "modified": [], "verify_success": False, "agent_result": None}
    if not quiet:
        print(summary_to_text(data["summary"]), file=sys.stderr)
        print(file=sys.stderr)
        print(data["history"].get("evolution_report", ""), file=sys.stderr)
        print(file=sys.stderr)
        print(data["architect_text"], file=sys.stderr)
        print(file=sys.stderr)
    out = run_fix_cycle_fn(
        path,
        runtime_mode=runtime_mode,
        non_interactive=non_interactive,
        session_id=session_id,
        window=window,
        dry_run=dry_run,
        quiet=quiet,
        skip_scan=True,
        no_clean_imports=no_clean_imports,
        no_code_smells=no_code_smells,
        verify_cmd=verify_cmd,
        verify_timeout=verify_timeout,
        team_mode=team_mode,
        apply_approved=apply_approved,
    )
    out["doctor_report"] = data
    report = out.get("report")
    doctor_runtime = data.get("runtime")
    if isinstance(report, dict) and isinstance(doctor_runtime, dict):
        report.setdefault(
            "runtime",
            {
                "degraded_mode": bool(doctor_runtime.get("degraded_mode")),
                "degraded_reasons": list(doctor_runtime.get("degraded_reasons", [])),
                "llm_used": doctor_runtime.get("llm_used"),
                "use_llm": doctor_runtime.get("use_llm"),
                "source": "doctor",
            },
        )
    return out


# TODO (eurika): refactor long_function 'run_full_cycle' — consider extracting helper
