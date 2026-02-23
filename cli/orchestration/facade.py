"""OOP facade for orchestrator entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class EurikaOrchestrator:
    """Formal orchestrator facade that delegates to run_cycle."""

    def __init__(self, run_cycle_fn: Callable[..., dict[str, Any]] | None = None) -> None:
        self._run_cycle_fn = run_cycle_fn

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
        team_mode: bool = False,
        apply_approved: bool = False,
    ) -> dict[str, Any]:
        """Execute cycle. mode: 'doctor' | 'fix' | 'full'."""
        resolved_run_cycle = self._run_cycle_fn
        if resolved_run_cycle is None:
            # Lazy import avoids circular dependency with cli.orchestrator.
            from cli.orchestrator import run_cycle as imported_run_cycle

            resolved_run_cycle = imported_run_cycle
        return resolved_run_cycle(
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
            team_mode=team_mode,
            apply_approved=apply_approved,
        )
