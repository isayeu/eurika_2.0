"""Full-cycle wiring helper for orchestration layer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


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
    run_doctor_cycle_fn: Callable[..., dict[str, Any]],
    run_fix_cycle_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run scan → doctor (full report) → fix. Single command for the full ritual."""
    from eurika.smells.rules import summary_to_text
    from runtime_scan import run_scan

    if not quiet:
        print("eurika cycle: scan → doctor → fix", file=sys.stderr)
    if run_scan(path) != 0:
        return {"return_code": 1, "report": {}, "operations": [], "modified": [], "verify_success": False, "agent_result": None}
    data = run_doctor_cycle_fn(path, window=window, no_llm=no_llm)
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
    )
    out["doctor_report"] = data
    return out


# TODO (eurika): refactor long_function 'run_full_cycle' — consider extracting helper
