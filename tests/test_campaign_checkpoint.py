"""Tests for campaign checkpoint + undo (ROADMAP 3.6.4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_campaign_checkpoint_create_attach_and_undo(tmp_path: Path) -> None:
    from eurika.storage.campaign_checkpoint import (
        attach_run_to_checkpoint,
        create_campaign_checkpoint,
        list_campaign_checkpoints,
        undo_campaign_checkpoint,
    )

    checkpoint = create_campaign_checkpoint(
        tmp_path,
        operations=[{"target_file": "a.py", "kind": "split_module"}],
        session_id="s1",
    )
    cid = checkpoint["checkpoint_id"]
    attached = attach_run_to_checkpoint(
        tmp_path,
        cid,
        run_id="r1",
        verify_success=True,
        modified=["a.py"],
    )
    assert attached is not None
    assert attached.get("run_ids") == ["r1"]

    listed = list_campaign_checkpoints(tmp_path)
    assert listed.get("checkpoints")
    assert listed["checkpoints"][0]["checkpoint_id"] == cid

    def fake_rollback(_root: Path, run_id: str | None) -> dict:
        return {"run_id": run_id, "restored": ["a.py"], "errors": []}

    undone = undo_campaign_checkpoint(tmp_path, checkpoint_id=cid, rollback_fn=fake_rollback)
    assert undone.get("status") == "undone"
    assert undone.get("run_ids") == ["r1"]
    assert "a.py" in (undone.get("restored") or [])
    assert not undone.get("errors")


def test_execute_fix_apply_stage_attaches_campaign_checkpoint(tmp_path: Path) -> None:
    from cli.orchestration.apply_stage import execute_fix_apply_stage

    ops = [
        {"target_file": "foo.py", "kind": "remove_unused_import", "explainability": {"why": "cleanup", "risk": "low"}},
    ]
    plan = {"operations": ops}

    def fake_apply(*_a, **_k):
        return {"modified": ["foo.py"], "verify": {"success": True}, "run_id": "run_123", "verify_duration_ms": 10}

    report, _, _ = execute_fix_apply_stage(
        tmp_path,
        plan,
        ops,
        session_id="session-1",
        quiet=True,
        verify_cmd=None,
        verify_timeout=None,
        backup_dir=".eurika_backups",
        apply_and_verify=fake_apply,
        run_scan=lambda *_a: 0,
        build_snapshot_from_self_map=lambda *_a: {},
        diff_architecture_snapshots=lambda *_a: {},
        metrics_from_graph=lambda *_a: {},
        rollback_patch=lambda *_a: {},
        result=type("R", (), {"output": {"policy_decisions": []}})(),
    )
    cp = report.get("campaign_checkpoint") or {}
    assert cp.get("checkpoint_id")
    assert "run_123" in (cp.get("run_ids") or [])

    # checkpoint is persisted on disk for later campaign-undo
    checkpoints_dir = tmp_path / ".eurika" / "campaign_checkpoints"
    files = list(checkpoints_dir.glob("*.json"))
    assert files
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload.get("session_id") == "session-1"


def test_campaign_checkpoint_reuses_same_session(tmp_path: Path) -> None:
    from eurika.storage.campaign_checkpoint import create_campaign_checkpoint

    first = create_campaign_checkpoint(
        tmp_path,
        operations=[{"target_file": "a.py", "kind": "split_module"}],
        session_id="sess-42",
    )
    second = create_campaign_checkpoint(
        tmp_path,
        operations=[{"target_file": "b.py", "kind": "remove_unused_import"}],
        session_id="sess-42",
    )
    assert second.get("checkpoint_id") == first.get("checkpoint_id")
    assert second.get("reused") is True
    assert int(second.get("operations_total") or 0) >= 2
    assert "a.py" in (second.get("targets") or [])
    assert "b.py" in (second.get("targets") or [])


def test_doctor_cycle_includes_latest_campaign_checkpoint(tmp_path: Path) -> None:
    from cli.orchestration.doctor import run_doctor_cycle
    from eurika.storage.campaign_checkpoint import create_campaign_checkpoint

    (tmp_path / "self_map.json").write_text(
        json.dumps(
            {
                "modules": [{"path": "a.py", "lines": 10, "functions": [], "classes": []}],
                "dependencies": {},
                "summary": {"files": 1, "total_lines": 10},
            }
        ),
        encoding="utf-8",
    )
    cp = create_campaign_checkpoint(tmp_path, operations=[{"target_file": "a.py", "kind": "split_module"}], session_id="s-doc")
    out = run_doctor_cycle(tmp_path, window=3, no_llm=True, online=False)
    latest = out.get("campaign_checkpoint") or {}
    assert latest.get("checkpoint_id") == cp.get("checkpoint_id")
