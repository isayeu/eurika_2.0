"""HITL journal + experiment memory."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.experiment_memory import (
    experiments_path,
    hitl_accept_rate,
    journal_path,
    load_experiments,
    load_hitl_journal,
    record_apply_outcome,
    record_decision_transitions,
    record_proposals,
)
from eurika.orchestration.team_mode import save_pending_plan, update_team_decisions


def test_record_proposals_and_decisions(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    ops = [
        {
            "kind": "extract_block_to_helper",
            "target_file": "a.py",
            "description": "extract helper",
            "params": {"start": 1},
        }
    ]
    path = save_pending_plan(
        tmp_path,
        {"source": "bug_hunt", "drill": "bug_hunt"},
        ops,
        [],
        notify_telegram=False,
    )
    assert path.is_file()
    recs = load_experiments(tmp_path)
    assert len(recs) == 1
    assert recs[0]["status"] == "proposed"
    assert recs[0]["conclusion"] == "pending"

    pending = json.loads(path.read_text(encoding="utf-8"))
    after = [dict(pending["operations"][0])]
    after[0]["team_decision"] = "approve"
    after[0]["approval_state"] = "approved"
    after[0]["approved_by"] = "tester"
    ok, msg = update_team_decisions(tmp_path, after)
    assert ok, msg

    journal = load_hitl_journal(tmp_path)
    assert journal_path(tmp_path).is_file()
    assert len(journal["decisions"]) == 1
    assert journal["decisions"][0]["decision"] == "approve"
    assert journal["aggregates"]["approve"] == 1

    rate = hitl_accept_rate(tmp_path)
    assert rate["approve"] == 1
    assert rate["reject"] == 0
    assert rate["insufficient_data"] is True  # need ≥3

    # two more rejects → rate measurable
    for i in range(2):
        ops_i = [
            {
                "kind": "remove_unused_import",
                "target_file": f"b{i}.py",
                "description": f"drop import {i}",
            }
        ]
        save_pending_plan(
            tmp_path,
            {"source": "prove-cycle", "drill": "imports"},
            ops_i,
            [],
            notify_telegram=False,
        )
        plan = json.loads((tmp_path / ".eurika" / "pending_plan.json").read_text())
        rej = [dict(plan["operations"][0])]
        rej[0]["team_decision"] = "reject"
        rej[0]["approval_state"] = "rejected"
        assert update_team_decisions(tmp_path, rej)[0]

    rate2 = hitl_accept_rate(tmp_path)
    assert rate2["n"] == 3
    assert rate2["insufficient_data"] is False
    assert rate2["accept_rate"] == round(1 / 3, 3)
    assert rate2["level"] == rate2["accept_rate"]


def test_record_apply_outcome_updates_experiment(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    op = {
        "kind": "extract_block_to_helper",
        "target_file": "c.py",
        "description": "extract",
        "params": {"x": 1},
    }
    record_proposals(tmp_path, [op], patch_plan={"source": "idle", "drill": "imports"})
    before = [dict(op, team_decision="pending", approval_state="pending")]
    after = [dict(op, team_decision="approve", approval_state="approved", approved_by="t")]
    assert record_decision_transitions(tmp_path, before, after, source="test") == 1
    assert record_apply_outcome(tmp_path, [op], verify_ok=True, exit_code=0) == 1

    journal = load_hitl_journal(tmp_path)
    assert journal["aggregates"]["apply_ok"] == 1
    assert journal["applies"][-1]["ok"] is True
    recs = load_experiments(tmp_path)
    assert recs[-1]["conclusion"] == "accept"
    assert recs[-1]["status"] == "applied"
    assert experiments_path(tmp_path).is_file()


def test_self_model_includes_hitl_score(tmp_path: Path) -> None:
    from eurika.api.self_model import build_self_model, format_self_model_text

    (tmp_path / ".eurika").mkdir()
    for i, dec in enumerate(["approve", "reject", "approve"]):
        op = {"kind": "k", "target_file": f"f{i}.py", "description": "d"}
        record_proposals(tmp_path, [op], patch_plan={"source": "t"})
        before = [dict(op, team_decision="pending")]
        after = [dict(op, team_decision=dec, approval_state="approved" if dec == "approve" else "rejected")]
        record_decision_transitions(tmp_path, before, after, source="test")

    snap = build_self_model(tmp_path)
    hitl = snap["capabilities"]["scores"]["hitl_accept_rate"]
    assert hitl["insufficient_data"] is False
    assert hitl["accept_rate"] == round(2 / 3, 3)
    text = format_self_model_text(snap, mode="full")
    assert "hitl_accept_rate" in text
    assert snap["experiments"]["hitl"]["approve"] == 2
    assert snap["experiments"]["experiment_records"]["n"] >= 3
