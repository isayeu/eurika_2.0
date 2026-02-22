"""Team mode: propose → approve → apply (ROADMAP 3.0.4).

Workflow:
1. eurika fix . --team-mode — scan, build plan, save to .eurika/pending_plan.json, exit.
2. Reviewer edits pending_plan.json: set team_decision="approve" and approved_by="name" on desired ops.
3. eurika fix . --apply-approved — load approved ops, apply and verify.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PENDING_PLAN_FILE = ".eurika/pending_plan.json"


def _pending_path(project_root: Path) -> Path:
    """Path to pending plan; overridable via EURIKA_APPROVALS_FILE."""
    override = os.environ.get("EURIKA_APPROVALS_FILE", "").strip()
    if override:
        p = Path(override)
        return p if p.is_absolute() else (Path(project_root) / p).resolve()
    return Path(project_root).resolve() / PENDING_PLAN_FILE


def save_pending_plan(
    project_root: Path,
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
    policy_decisions: list[dict[str, Any]],
    session_id: str | None = None,
) -> Path:
    """Save plan for team approval. Returns path to saved file."""
    path = _pending_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    dec_by_idx = {d.get("index"): d for d in policy_decisions if d.get("index")}
    ops_with_team: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        dec = dec_by_idx.get(idx, {})
        op_copy = dict(op)
        op_copy["policy_decision"] = dec.get("decision", "allow")
        op_copy["approval_state"] = "pending"
        op_copy["critic_verdict"] = str(op_copy.get("critic_verdict") or "pending").lower()
        op_copy["team_decision"] = "pending"
        op_copy["approved_by"] = None
        ops_with_team.append(op_copy)

    payload = {
        "session_id": session_id or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root.resolve()),
        "patch_plan": dict(patch_plan, operations=ops_with_team),
        "operations": ops_with_team,
        "instructions": (
            "Edit 'team_decision' to 'approve' and set 'approved_by' for ops to apply. "
            "Then run: eurika fix . --apply-approved"
        ),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_approved_operations(project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load operations with team_decision=approve. Returns (approved_ops, full_payload) or ([], None) if missing/invalid."""
    path = _pending_path(project_root)
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], None
    if not isinstance(data, dict):
        return [], None

    ops = data.get("operations")
    if not isinstance(ops, list):
        return [], None
    approved: list[dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, dict):
            return [], None
        team_decision = str(op.get("team_decision", "")).lower()
        approval_state = str(op.get("approval_state", "")).lower()
        if team_decision == "approve" or approval_state == "approved":
            approved.append(dict(op))
    # Strip team-specific fields from ops before apply
    for op in approved:
        op["approval_state"] = "approved"
        op["decision_source"] = "team"
        op.pop("team_decision", None)
        op.pop("approved_by", None)
        op.pop("policy_decision", None)
    return approved, data


def has_pending_plan(project_root: Path) -> bool:
    """True if pending plan exists."""
    return _pending_path(project_root).exists()


def load_pending_plan(project_root: Path) -> dict[str, Any] | None:
    """Load full pending plan for UI. Returns None if missing/invalid."""
    path = _pending_path(project_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    ops = data.get("operations")
    if ops is None:
        return data
    if not isinstance(ops, list):
        return None
    if any(not isinstance(op, dict) for op in ops):
        return None
    return data


def update_team_decisions(
    project_root: Path,
    operations: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Update team_decision and approved_by in pending_plan. Returns (success, message)."""
    path = _pending_path(project_root)
    if not path.exists():
        return False, "no pending plan"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False, "invalid pending plan"
        existing = data.get("operations")
        if not isinstance(existing, list):
            return False, "invalid pending plan"
        if len(operations) != len(existing):
            return False, f"count mismatch: expected {len(existing)}, got {len(operations)}"
        merged = []
        for old, new in zip(existing, operations):
            if not isinstance(old, dict):
                return False, "invalid pending plan"
            if not isinstance(new, dict):
                return False, "invalid operations payload"
            m = dict(old)
            approval_state = new.get("approval_state")
            if approval_state is not None:
                state = str(approval_state).lower()
                if state not in {"approved", "rejected", "pending"}:
                    return False, "invalid approval_state"
                m["approval_state"] = state
                m["team_decision"] = "approve" if state == "approved" else ("reject" if state == "rejected" else "pending")
            else:
                m["team_decision"] = str(new.get("team_decision", m.get("team_decision", "pending"))).lower()
                m["approval_state"] = "approved" if m["team_decision"] == "approve" else ("rejected" if m["team_decision"] == "reject" else "pending")
            m["approved_by"] = new.get("approved_by")
            if m.get("approval_state") != "approved":
                m["approved_by"] = None
            merged.append(m)
        data["operations"] = merged
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True, "saved"
    except Exception as e:
        return False, str(e)
