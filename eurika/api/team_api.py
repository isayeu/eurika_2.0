"""Team API routes: pending plan, approvals (ROADMAP 3.5.6, R1 public API facade)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def get_pending_plan(project_root: Path) -> Dict[str, Any]:
    """Load pending plan from .eurika/pending_plan.json for approve UI (ROADMAP 3.5.6)."""
    from eurika.orchestration.team_mode import has_pending_plan, load_pending_plan

    root = Path(project_root).resolve()
    if not has_pending_plan(root):
        return {"error": "no pending plan", "hint": "Run eurika fix . --team-mode first"}
    data = load_pending_plan(root)
    if data is None:
        return {"error": "invalid pending plan", "hint": "Check .eurika/pending_plan.json"}
    return data


def save_approvals(project_root: Path, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Update team_decision and approved_by in pending_plan.json (ROADMAP 3.5.6)."""
    from eurika.orchestration.team_mode import update_team_decisions

    root = Path(project_root).resolve()
    if not isinstance(operations, list) or any((not isinstance(o, dict) for o in operations)):
        return {"error": "invalid operations payload", "hint": "Expected operations: list[object]"}
    ok, msg = update_team_decisions(root, operations)
    if ok:
        approved = sum((1 for o in operations if str(o.get("team_decision", "")).lower() == "approve"))
        return {"ok": True, "saved": len(operations), "approved": approved}
    return {"error": msg, "hint": "Run eurika fix . --team-mode first"}
