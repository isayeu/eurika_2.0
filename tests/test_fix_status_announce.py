"""announce_apply_approved writes Chat + Goals after HITL apply."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat import load_chat_history
from eurika.api.chat_context import load_dialog_state
from eurika.api.fix_status import announce_apply_approved


def test_announce_apply_approved_writes_chat_and_goals(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir(parents=True)
    report = {
        "run_id": "test_run",
        "verify": {"success": True},
        "verify_duration_ms": 12,
        "modified": ["eurika/polygon/extractable_block.py"],
        "errors": [],
    }
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    out = announce_apply_approved(
        tmp_path, exit_code=0, client="test", publish_activity=False
    )
    assert out["ok"] is True
    assert "apply-approved (exit 0)" in out["text"]
    assert "extractable_block.py" in out["text"]

    history = load_chat_history(tmp_path, limit=10)
    assert history
    assert history[-1]["role"] == "assistant"
    assert "verify: **True**" in history[-1]["content"]

    state = load_dialog_state(tmp_path)
    last = state.get("last_execution") or {}
    assert last.get("ok") is True
    assert any("extractable_block.py" in str(x) for x in (last.get("artifacts_changed") or []))
    assert not state.get("active_goal")


def test_announce_apply_approved_notifies_telegram(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".eurika").mkdir(parents=True)
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "verify": {"success": True},
                "modified": ["a.py"],
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict] = []

    def fake_notify(root, **kwargs):
        calls.append({"root": str(root), **kwargs})
        return {"ok": True, "sent": 1, "skipped": None}

    monkeypatch.setattr(
        "eurika.integrations.telegram_bot.notify_apply_result",
        fake_notify,
    )
    out = announce_apply_approved(
        tmp_path, exit_code=0, client="test", publish_activity=False
    )
    assert out["ok"] is True
    assert len(calls) == 1
    assert calls[0]["ok"] is True
    assert calls[0]["run_id"] == "r1"
    assert "a.py" in calls[0]["modified"]


def test_announce_approvals_decision_writes_chat_and_goals(tmp_path: Path) -> None:
    from eurika.api.fix_status import announce_approvals_decision

    (tmp_path / ".eurika").mkdir(parents=True)
    out = announce_approvals_decision(
        tmp_path,
        decision="approve",
        n=2,
        approved_by="telegram",
        client="telegram",
        publish_activity=False,
    )
    assert out["ok"] is True
    assert out["decision"] == "approve"
    assert "approve" in out["text"].lower()
    assert "apply-approved" in out["text"]

    history = load_chat_history(tmp_path, limit=10)
    assert history
    assert history[-1]["role"] == "assistant"
    assert "approve" in history[-1]["content"].lower()

    state = load_dialog_state(tmp_path)
    last = state.get("last_execution") or {}
    assert "approve" in str(last.get("summary") or "").lower()
    assert not state.get("active_goal")


def test_handle_approvals_decision_announces_chat(tmp_path: Path) -> None:
    from eurika.integrations.telegram_bot import handle_approvals_decision
    from eurika.orchestration.team_mode import save_pending_plan

    (tmp_path / ".eurika").mkdir(parents=True)
    save_pending_plan(
        tmp_path,
        {"source": "t", "summary": "1"},
        [
            {
                "kind": "remove_unused_import",
                "target_file": "a.py",
                "critic_verdict": "allow",
            }
        ],
        [],
        notify_telegram=False,
    )
    reply = handle_approvals_decision(
        tmp_path, decision="approve", approved_by="telegram"
    )
    assert "approve" in reply.lower()
    history = load_chat_history(tmp_path, limit=5)
    assert history and "telegram" in history[-1]["content"].lower()
