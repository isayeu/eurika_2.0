"""Public API for C.14 v1.5 bug-hunt propose (chat_handlers stay off orchestration)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_bug_hunt_propose_api(
    root: Path,
    *,
    sandbox: bool = True,
    web: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    from eurika.orchestration.bug_hunt import run_bug_hunt_propose

    return run_bug_hunt_propose(
        root,
        dry_run=dry_run,
        sandbox=sandbox,
        web=web if web else None,
    )


def format_bug_hunt_propose_summary(payload: dict[str, Any]) -> str:
    from eurika.orchestration.bug_hunt import format_bug_hunt_summary

    return format_bug_hunt_summary(payload)


def bug_hunt_pending_plan_ready(root: Path) -> bool:
    from eurika.orchestration.team_mode import has_pending_plan

    return bool(has_pending_plan(root))
