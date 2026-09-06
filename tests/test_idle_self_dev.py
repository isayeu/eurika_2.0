"""Tests for idle self-dev (C.14 propose+sandbox when LLM quiet)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eurika.orchestration import idle_self_dev as isd
from eurika.orchestration import llm_lease as ll


def test_next_drill_rotation() -> None:
    assert isd.next_drill(None) == "imports"
    assert isd.next_drill("imports") == "extractable_block"
    assert isd.next_drill("extractable_block") == "long_function"
    assert isd.next_drill("long_function") == "deep_nesting"
    assert isd.next_drill("deep_nesting") == "llm_extract"
    assert isd.next_drill("llm_extract") == "bug_hunt"
    assert isd.next_drill("bug_hunt") == "imports"


def test_next_drill_skips_saturated_deterministic() -> None:
    ok_counts = {
        "imports": 5,
        "extractable_block": 5,
        "long_function": 5,
        "deep_nesting": 5,
    }
    assert isd.drill_is_saturated("imports", ok_counts=ok_counts) is True
    assert isd.drill_is_saturated("deep_nesting", ok_counts=ok_counts) is True
    assert isd.drill_is_saturated("llm_extract", ok_counts=ok_counts) is False
    assert isd.drill_is_saturated("bug_hunt", ok_counts=ok_counts) is False
    # Deterministic saturated → prefer llm_extract / bug_hunt (2 unsaturated).
    assert isd.next_drill(None, ok_counts=ok_counts) == "llm_extract"
    assert isd.next_drill("imports", ok_counts=ok_counts) == "llm_extract"
    assert isd.next_drill("deep_nesting", ok_counts=ok_counts) == "llm_extract"
    assert isd.next_drill("llm_extract", ok_counts=ok_counts) == "bug_hunt"
    assert isd.next_drill("bug_hunt", ok_counts=ok_counts) == "llm_extract"
    # Partial saturation prefers unsaturated deterministic + llm/bug_hunt.
    ok_partial = {
        "imports": 5,
        "extractable_block": 5,
        "long_function": 5,
        "deep_nesting": 0,
    }
    assert isd.next_drill("llm_extract", ok_counts=ok_partial) == "bug_hunt"
    assert isd.next_drill("bug_hunt", ok_counts=ok_partial) == "deep_nesting"
    assert isd.next_drill("deep_nesting", ok_counts=ok_partial) == "llm_extract"


def test_stamp_last_drill_retries_on_failure() -> None:
    assert isd.stamp_last_drill(attempted="imports", ok=True) == "imports"
    assert isd.stamp_last_drill(attempted="imports", ok=False) is None
    assert isd.next_drill(isd.stamp_last_drill(attempted="extractable_block", ok=False)) == (
        "extractable_block"
    )
    assert isd.next_drill(isd.stamp_last_drill(attempted="long_function", ok=False)) == (
        "long_function"
    )
    assert isd.next_drill(isd.stamp_last_drill(attempted="deep_nesting", ok=False)) == (
        "deep_nesting"
    )
    assert isd.next_drill(isd.stamp_last_drill(attempted="llm_extract", ok=False)) == (
        "llm_extract"
    )
    assert isd.next_drill(isd.stamp_last_drill(attempted="bug_hunt", ok=False)) == (
        "bug_hunt"
    )


def test_maybe_run_skips_when_not_due(tmp_path: Path) -> None:
    t0 = 5_000_000
    isd.save_stamp(tmp_path, {"last_ms": t0, "last_drill": "imports"})
    out = isd.maybe_run(tmp_path, now_ms=t0 + 60_000, min_interval_ms=30 * 60 * 1000)
    assert out["skipped"] == "not_due"


def test_maybe_run_skips_when_pending_exists(tmp_path: Path) -> None:
    eurika = tmp_path / ".eurika"
    eurika.mkdir(parents=True)
    (eurika / "pending_plan.json").write_text(
        json.dumps(
            {
                "operations": [
                    {
                        "kind": "remove_unused_import",
                        "target_file": "eurika/polygon/imports_ok.py",
                        "team_decision": "pending",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = isd.maybe_run(tmp_path, force=True, now_ms=6_000_000, quiet_ms=0)
    assert out["skipped"] == "pending_exists"


def test_maybe_run_skips_when_lease_busy(tmp_path: Path) -> None:
    t0 = 7_000_000
    ll.acquire(
        tmp_path,
        holder="market:busy",
        priority="market",
        purpose="cursor_hour",
        now_ms=t0,
        ttl_ms=60_000,
    )
    out = isd.maybe_run(tmp_path, force=True, now_ms=t0 + 100, quiet_ms=0)
    assert out["skipped"] == "llm_busy_or_quiet"


def test_maybe_run_yields_to_market_due(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "eurika.ml.cursor_hourly.is_due",
        lambda *_a, **_k: True,
    )
    out = isd.maybe_run(
        tmp_path,
        force=True,
        now_ms=8_000_000,
        quiet_ms=0,
        market_llm_enabled=True,
    )
    assert out["skipped"] == "market_llm_due"


def test_maybe_run_happy_path_mocks_propose(tmp_path: Path) -> None:
    t0 = 9_000_000
    calls: list[dict[str, Any]] = []

    def _fake_propose(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs, root=str(root)))
        return {
            "ok": True,
            "sandbox": True,
            "sandbox_mode": "worktree",
            "target_file": "eurika/polygon/imports_ok.py",
            "pending_plan": ".eurika/pending_plan.json",
            "drill_id": kwargs.get("drill"),
        }

    out = isd.maybe_run(
        tmp_path,
        force=True,
        now_ms=t0,
        quiet_ms=0,
        run_propose=_fake_propose,
    )
    assert out["skipped"] is None
    assert out["ok"] is True
    assert out["drill_id"] == "imports"
    assert out["approvalsQueued"] == 1
    assert "imports_ok.py" in str(out.get("message") or "")
    assert calls and calls[0]["sandbox"] is True
    assert calls[0]["drill"] == "imports"
    stamp = isd.load_stamp(tmp_path)
    assert stamp.get("last_drill") == "imports"
    assert (stamp.get("drill_ok") or {}).get("imports") == 1
    from eurika.api.chat_context import load_dialog_state

    dialog = load_dialog_state(tmp_path)
    last = dialog.get("last_execution") or {}
    assert last.get("ok") is True
    assert "idle_self_dev" in str(last.get("summary") or "")
    assert not (dialog.get("active_goal") or {})

    out2 = isd.maybe_run(
        tmp_path,
        force=True,
        now_ms=t0 + 10,
        quiet_ms=0,
        run_propose=_fake_propose,
    )
    assert out2["drill_id"] == "extractable_block"


def test_maybe_run_prefers_bug_hunt_when_deterministic_saturated(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """All deterministic saturated via drill_ok → llm_extract/bug_hunt, not det forever."""
    isd.save_stamp(
        tmp_path,
        {
            "last_ms": 0,
            "last_drill": "llm_extract",
            "drill_ok": {
                "imports": 5,
                "extractable_block": 5,
                "long_function": 5,
                "deep_nesting": 5,
            },
        },
    )
    calls: list[dict[str, Any]] = []

    def _fake_propose(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs, root=str(root)))
        return {
            "ok": True,
            "sandbox": True,
            "sandbox_mode": "copy",
            "target_file": "eurika/api/ops.py",
            "pending_plan": ".eurika/pending_plan.json",
            "drill_id": kwargs.get("drill"),
        }

    out = isd.maybe_run(
        tmp_path,
        force=True,
        now_ms=11_000_000,
        quiet_ms=0,
        run_propose=_fake_propose,
    )
    assert out["ok"] is True
    assert out["drill_id"] == "bug_hunt"
    assert calls and calls[0]["drill"] == "bug_hunt"


def test_maybe_run_stamps_on_propose_exception(tmp_path: Path) -> None:
    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("sandbox boom")

    out = isd.maybe_run(
        tmp_path,
        force=True,
        now_ms=10_000_000,
        quiet_ms=0,
        run_propose=_boom,
    )
    assert out["ok"] is False
    assert out["persisted"] is True
    assert "sandbox boom" in str(out.get("error") or "")
    stamp = isd.load_stamp(tmp_path)
    assert stamp.get("last_attempted") == "imports"
    # Failure must not advance rotation — next due window retries imports.
    assert stamp.get("last_drill") in (None, "")
    assert stamp.get("last_ok") is False
    # Retry within min_interval is blocked
    again = isd.maybe_run(
        tmp_path,
        now_ms=10_000_000 + 60_000,
        quiet_ms=0,
        run_propose=_boom,
    )
    assert again["skipped"] == "not_due"
    assert isd.next_drill(stamp.get("last_drill")) == "imports"


def test_idle_self_dev_activity_titles(tmp_path: Path) -> None:
    from eurika.agent.live_activity import publish_progress, publish_start, recent

    started = publish_start(
        tmp_path,
        "idle_self_dev",
        {
            "drill": "imports",
            "detail": isd.drill_detail("imports"),
        },
        client="idle_self_dev",
    )
    assert "саморазвитие" in started["title"]
    assert "imports_ok.py" in started["title"]
    publish_progress(
        tmp_path,
        method="idle_self_dev",
        title="саморазвитие: sandbox apply+verify для drill `imports`…",
        client="idle_self_dev",
    )
    events = recent(tmp_path)["events"]
    assert events[-1]["phase"] == "progress"


def test_ui_prefs_roundtrip(tmp_path: Path, monkeypatch: Any) -> None:
    prefs = tmp_path / "qt_settings.json"
    monkeypatch.setattr(isd, "ui_prefs_path", lambda: prefs)
    assert isd.get_idle_prefs()["idle_self_dev"] is False
    out = isd.set_idle_enabled(True)
    assert out["idle_self_dev"] is True
    assert json.loads(prefs.read_text(encoding="utf-8"))["idle_self_dev"] is True


def test_rpc_idle_self_dev_run_and_prefs(tmp_path: Path, monkeypatch: Any) -> None:
    import threading

    from eurika.agent.local_runtime import LocalAgentRuntime

    prefs = tmp_path / "qt_settings.json"
    monkeypatch.setattr(isd, "ui_prefs_path", lambda: prefs)
    runtime = LocalAgentRuntime(tmp_path)
    assert "idle-self-dev/run" in runtime.capabilities()["methods"]

    got = runtime.dispatch(
        "idle-self-dev/prefs",
        {"enabled": True},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )
    assert got["idle_self_dev"] is True

    calls: list[dict[str, Any]] = []

    def _fake(root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs, root=str(root)))
        return {
            "ok": True,
            "skipped": None,
            "idle_self_dev": True,
            "drill_id": "imports",
            "message": "ok",
            "approvalsQueued": 0,
            "persisted": True,
        }

    monkeypatch.setattr(isd, "maybe_run", _fake)
    result = runtime.dispatch(
        "idle-self-dev/run",
        {"force": True},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )
    assert result["ok"] is True
    assert calls and calls[0].get("force") is True
    status = runtime.dispatch(
        "idle-self-dev/status",
        {},
        cancel=threading.Event(),
        emit=lambda *_: None,
    )
    assert status["prefs"]["idle_self_dev"] is True
