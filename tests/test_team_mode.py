"""Tests for Team Mode (ROADMAP 3.0.4).

Import team_mode directly to avoid cli -> handlers -> architecture_pipeline chain.
S3: eurika.orchestration.team_mode (cli.orchestration removed).
"""

import json
from pathlib import Path

from eurika.orchestration.team_mode import (
    clear_pending_plan_after_apply,
    has_pending_plan,
    load_approved_operations,
    load_pending_plan,
    record_team_rejections,
    save_pending_plan,
    update_team_decisions,
)


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
    assert data is not None
    assert data["operations"][0]["team_decision"] == "approve"
    assert data["operations"][0]["approved_by"] == "ui"
    assert data["operations"][1]["team_decision"] == "reject"
    assert data["operations"][1]["approved_by"] is None


def test_update_team_decisions_supports_approval_state(tmp_path: Path) -> None:
    """API payload may send approval_state directly; it must map to team_decision."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [{"target_file": "a.py", "kind": "split"}]
    decs = [{"index": 1, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    ok, _ = update_team_decisions(
        tmp_path,
        [{"approval_state": "approved", "approved_by": "ui"}],
    )
    assert ok
    data = load_pending_plan(tmp_path)
    assert data is not None
    assert data["operations"][0]["approval_state"] == "approved"
    assert data["operations"][0]["team_decision"] == "approve"
    approved, _ = load_approved_operations(tmp_path)
    assert len(approved) == 1
    assert approved[0]["approval_state"] == "approved"
    assert approved[0]["decision_source"] == "team"


def test_record_team_rejections_creates_deduplicated_learning_outcome(tmp_path: Path) -> None:
    from eurika.storage import (
        ProjectMemory,
        get_recent_human_rejected_proposal_hashes,
    )

    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [
        {"target_file": "a.py", "kind": "extract_block_to_helper"},
        {"target_file": "b.py", "kind": "remove_unused_import"},
    ]
    decs = [{"index": 1, "decision": "review"}, {"index": 2, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    ok, _ = update_team_decisions(
        tmp_path,
        [
            {"team_decision": "reject"},
            {"team_decision": "approve", "approved_by": "ui"},
        ],
    )
    assert ok

    assert record_team_rejections(tmp_path) == 1
    assert record_team_rejections(tmp_path) == 0

    events = ProjectMemory(tmp_path).events.recent_events(limit=10, types=("learn",))
    rejects = [event for event in events if event.output.get("failure_reason") == "human_rejected"]
    assert len(rejects) == 1
    assert rejects[0].result is False
    assert rejects[0].input["operations"][0]["target_file"] == "a.py"
    assert rejects[0].input["operations"][0]["decision_source"] == "team"
    proposal_hash = rejects[0].input["operations"][0]["proposal_hash"]
    assert proposal_hash in get_recent_human_rejected_proposal_hashes(tmp_path)


def test_clear_pending_plan_after_apply_removes_approve_reject(tmp_path: Path) -> None:
    """clear_pending_plan_after_apply removes approve/reject ops; keeps pending."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [
        {"target_file": "a.py", "kind": "split"},
        {"target_file": "b.py", "kind": "clean"},
        {"target_file": "c.py", "kind": "refactor"},
    ]
    decs = [{"index": i, "decision": "allow"} for i in range(1, 4)]
    save_pending_plan(tmp_path, plan, ops, decs)
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text())
    data["operations"][0]["team_decision"] = "approve"
    data["operations"][1]["team_decision"] = "reject"
    data["operations"][2]["team_decision"] = "pending"
    path.write_text(json.dumps(data, indent=2))
    ok = clear_pending_plan_after_apply(tmp_path)
    assert ok
    after = load_pending_plan(tmp_path)
    assert after is not None
    assert len(after["operations"]) == 1
    assert after["operations"][0]["target_file"] == "c.py"


def test_clear_pending_plan_after_apply_deletes_when_no_pending(tmp_path: Path) -> None:
    """When all ops are approve/reject, file is deleted."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [{"target_file": "a.py", "kind": "split"}]
    decs = [{"index": 1, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text())
    data["operations"][0]["team_decision"] = "reject"
    path.write_text(json.dumps(data, indent=2))
    ok = clear_pending_plan_after_apply(tmp_path)
    assert ok
    assert not has_pending_plan(tmp_path)
    assert load_pending_plan(tmp_path) is None


def test_load_missing_file(tmp_path: Path) -> None:
    """Load from path with no pending plan returns ([], None)."""
    approved, payload = load_approved_operations(tmp_path)
    assert approved == []
    assert payload is None
    assert not has_pending_plan(tmp_path)


def test_load_pending_plan_invalid_operations_shape_returns_none(tmp_path: Path) -> None:
    """load_pending_plan returns None when operations is not list[dict]."""
    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps({"operations": ["bad"]}), encoding="utf-8")
    assert load_pending_plan(tmp_path) is None


def test_update_team_decisions_count_mismatch_does_not_modify_file(tmp_path: Path) -> None:
    """count mismatch should fail and keep existing pending plan unchanged."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [
        {"target_file": "a.py", "kind": "split"},
        {"target_file": "b.py", "kind": "clean"},
    ]
    decs = [{"index": 1, "decision": "allow"}, {"index": 2, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    before = load_pending_plan(tmp_path)
    ok, msg = update_team_decisions(tmp_path, [{"team_decision": "approve", "approved_by": "ui"}])
    after = load_pending_plan(tmp_path)
    assert not ok
    assert "count mismatch" in msg
    assert before == after


def test_update_team_decisions_invalid_existing_item_returns_error(tmp_path: Path) -> None:
    """Invalid pending operations shape should fail predictably and keep file untouched."""
    pending = tmp_path / ".eurika" / "pending_plan.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    payload = {"operations": ["bad"]}
    pending.write_text(json.dumps(payload), encoding="utf-8")
    before = pending.read_text(encoding="utf-8")
    ok, msg = update_team_decisions(tmp_path, [{"team_decision": "approve", "approved_by": "ui"}])
    after = pending.read_text(encoding="utf-8")
    assert not ok
    assert "invalid pending plan" in msg
    assert before == after


def test_update_team_decisions_invalid_input_item_returns_error(tmp_path: Path) -> None:
    """Invalid incoming operations payload should fail and not rewrite pending plan."""
    plan = {"project_root": str(tmp_path), "operations": []}
    ops = [{"target_file": "a.py", "kind": "split"}]
    decs = [{"index": 1, "decision": "allow"}]
    save_pending_plan(tmp_path, plan, ops, decs)
    pending = tmp_path / ".eurika" / "pending_plan.json"
    before = pending.read_text(encoding="utf-8")
    ok, msg = update_team_decisions(tmp_path, ["bad"])  # type: ignore[list-item]
    after = pending.read_text(encoding="utf-8")
    assert not ok
    assert "invalid operations payload" in msg
    assert before == after
