"""Public API for C.14 polygon propose (keeps chat_handlers off orchestration internals)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_polygon_propose(
    root: Path,
    *,
    drill: str,
    require_llm: bool = False,
    sandbox: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    from eurika.orchestration.prove_cycle import run_prove_propose

    return run_prove_propose(
        root,
        dry_run=dry_run,
        drill=drill,
        require_llm=require_llm,
        sandbox=sandbox,
    )


def format_polygon_propose_summary(payload: dict[str, Any]) -> str:
    from eurika.orchestration.prove_cycle import format_prove_cycle_summary

    return format_prove_cycle_summary(payload)


def polygon_pending_plan_ready(root: Path) -> bool:
    from eurika.orchestration.team_mode import has_pending_plan

    return bool(has_pending_plan(root))
