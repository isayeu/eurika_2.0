"""
Executor Sandbox v0.4 (draft)

Receives an ActionPlan and can simulate (dry_run) or execute (apply) it.

Responsibilities:
- accept ActionPlan instances;
- dry_run: simulate without modifying code, log to JSONL;
- execute: apply minimal changes (append TODO blocks per action) via patch_apply.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from action_plan import Action, ActionPlan
from patch_apply import apply_patch_plan


@dataclass
class ExecutionLogEntry:
    """Single sandbox execution record for one action."""

    action: Dict[str, Any]
    status: str
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": dict(self.action),
            "status": self.status,
            "notes": self.notes,
        }


def _action_plan_to_patch_plan(plan: ActionPlan) -> Dict[str, Any]:
    """Convert ActionPlan to a minimal patch plan dict for apply_patch_plan."""
    operations: List[Dict[str, Any]] = []
    for action in plan.actions:
        desc_one_line = (action.description or "").replace("\n", " ").strip()
        diff = f"# TODO: [{action.type}] {desc_one_line}\n"
        operations.append({
            "target_file": action.target,
            "kind": action.type,
            "description": action.description,
            "diff": diff,
        })
    return {"operations": operations}


class ExecutorSandbox:
    """
    Executor for ActionPlan: dry_run (simulate + log) or execute (apply via patch_apply).

    dry_run: read-only, logs what would be done.
    execute: appends a TODO comment block per action to the target file; uses
    .eurika_backups when backup=True.
    """

    def __init__(self, project_root: Path, log_path: Optional[Path] = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.log_path = log_path or (self.project_root / "architecture_actions_log.jsonl")

    def execute(
        self,
        plan: ActionPlan,
        backup: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute the ActionPlan: append a TODO block per action to target files.

        Uses patch_apply under the hood; backup in .eurika_backups when backup=True.
        Returns the same shape as apply_patch_plan plus "actions" with per-action status.
        """
        patch = _action_plan_to_patch_plan(plan)
        report = apply_patch_plan(
            self.project_root,
            patch,
            dry_run=False,
            backup=backup,
        )
        modified_set = set(report.get("modified", []))
        entries: List[ExecutionLogEntry] = []
        for action in plan.actions:
            status = "applied" if action.target in modified_set else "skipped"
            notes = (
                "applied (diff appended)" if status == "applied"
                else "skipped (missing or already present)"
            )
            entries.append(ExecutionLogEntry(
                action=asdict(action),
                status=status,
                notes=notes,
            ))
        self._append_log(entries)
        report["actions"] = [e.to_dict() for e in entries]
        report["total_risk"] = plan.total_risk
        report["expected_gain"] = plan.expected_gain
        return report

    def dry_run(self, plan: ActionPlan) -> Dict[str, Any]:
        """
        Simulate execution of the given ActionPlan.

        Returns:
            A summary dict with:
            - "actions": list of ExecutionLogEntry dicts;
            - "total_risk": float (copied from plan);
            - "expected_gain": float (copied from plan).
        """
        entries: List[ExecutionLogEntry] = []

        for action in plan.actions:
            entry = self._simulate_action(action)
            entries.append(entry)

        self._append_log(entries)

        return {
            "actions": [e.to_dict() for e in entries],
            "total_risk": plan.total_risk,
            "expected_gain": plan.expected_gain,
        }

    def _simulate_action(self, action: Action) -> ExecutionLogEntry:
        """
        Produce a conservative simulation record for a single action.

        Today this only records intent. Future versions may:
        - inspect files,
        - compute diffs,
        - run static checks in a temporary workspace, etc.
        """
        notes = (
            "planned only (sandbox dry-run); "
            f"no changes applied to {self.project_root}"
        )
        return ExecutionLogEntry(
            action=asdict(action),
            status="planned",
            notes=notes,
        )

    def _append_log(self, entries: Iterable[ExecutionLogEntry]) -> None:
        """Append execution entries to a JSONL log file."""
        if not entries:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
