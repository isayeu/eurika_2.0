"""Tests for Team Mode (ROADMAP 3.0.4).

Import team_mode directly to avoid cli -> handlers -> architecture_pipeline chain.
"""

import importlib.util
import json
from pathlib import Path

_team_mode_path = Path(__file__).resolve().parents[1] / "cli" / "orchestration" / "team_mode.py"
_spec = importlib.util.spec_from_file_location("team_mode", _team_mode_path)
_team = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_team)
save_pending_plan = _team.save_pending_plan
load_pending_plan = _team.load_pending_plan
load_approved_operations = _team.load_approved_operations
has_pending_plan = _team.has_pending_plan
update_team_decisions = _team.update_team_decisions


def test_save_and_load_empty_ops(tmp_path: Path) -> None:
    """Save plan with empty ops; load returns [] approved."""
    plan = {"operations": []}
    ops: list = []
    decs: list = []
    save_pending_plan(tmp_path, plan, ops, decs, "s1")
    assert has_pending_plan(tmp_path)
    approved, payload = load_approved_operations(tmp_path)
    assert approved == []
    assert payload is not None
    assert payload.get("instructions")


def test_load_approved_after_edit(tmp_path: Path) -> None:
    """After setting team_decision=approve, load returns that op."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [
        {
            "target_file": "a.py",
            "kind": "remove_unused_import",
            "policy_decision": "allow",
            "team_decision": "pending",
            "approved_by": None,
        }
    ]
    decs = [{"index": 1, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text())
    data["operations"][0]["team_decision"] = "approve"
    data["operations"][0]["approved_by"] = "alice"
    path.write_text(json.dumps(data, indent=2))
    approved, _ = load_approved_operations(tmp_path)
    assert len(approved) == 1
    assert approved[0]["target_file"] == "a.py"
    assert "team_decision" not in approved[0]
    assert "approved_by" not in approved[0]


def test_update_team_decisions(tmp_path: Path) -> None:
    """update_team_decisions merges team_decision from request."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [
        {"target_file": "a.py", "kind": "split"},
        {"target_file": "b.py", "kind": "clean"},
    ]
    decs = [{"index": 1, "decision": "allow"}, {"index": 2, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    ok, msg = update_team_decisions(tmp_path, [
        {"team_decision": "approve", "approved_by": "ui"},
        {"team_decision": "reject"},
    ])
    assert ok
    data = load_pending_plan(tmp_path)
    assert data["operations"][0]["team_decision"] == "approve"
    assert data["operations"][0]["approved_by"] == "ui"
    assert data["operations"][1]["team_decision"] == "reject"
    assert data["operations"][1]["approved_by"] is None


def test_load_missing_file(tmp_path: Path) -> None:
    """Load from path with no pending plan returns ([], None)."""
    approved, payload = load_approved_operations(tmp_path)
    assert approved == []
    assert payload is None
    assert not has_pending_plan(tmp_path)
