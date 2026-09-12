"""Critic / decision coupling v0 tests."""
from __future__ import annotations

import json
from pathlib import Path

from eurika.api.critic_coupling import couple_critic_verdict, load_critic_coupling_signals
from eurika.orchestration.prepare_critic import run_critic_pass


def test_couple_escalates_allow_on_ab_baseline() -> None:
    signals = {
        "planning": {
            "ab_by_kind": {
                "extract_block_to_helper": {"bias": "baseline", "delta": -25},
            },
            "verify_low_by_kind": {},
        },
        "caution_weights": {},
    }
    op = {"kind": "extract_block_to_helper", "target_file": "a.py"}
    verdict, reason, stamp = couple_critic_verdict(
        op, verdict="allow", reason="passed", signals=signals
    )
    assert verdict == "review"
    assert "ab_baseline" in reason
    assert stamp.get("critic_coupling_v0") is True
    assert stamp.get("planning_ab_bias") == "baseline"


def test_couple_never_denies_from_signals() -> None:
    signals = {
        "planning": {
            "ab_by_kind": {"k": {"bias": "baseline", "delta": -25}},
            "verify_low_by_kind": {"k": {"delta": -20, "rate": 0.1}},
        },
        "caution_weights": {"k": -55},
    }
    verdict, _reason, stamp = couple_critic_verdict(
        {"kind": "k"}, verdict="allow", reason="ok", signals=signals
    )
    assert verdict == "review"
    assert verdict != "deny"
    assert stamp.get("critic_coupling_triggers")


def test_couple_skips_whitelist_auto() -> None:
    signals = {
        "planning": {
            "ab_by_kind": {"remove_unused_import": {"bias": "baseline", "delta": -25}},
            "verify_low_by_kind": {},
        },
        "caution_weights": {"remove_unused_import": -40},
    }
    verdict, reason, stamp = couple_critic_verdict(
        {"kind": "remove_unused_import"},
        verdict="allow",
        reason="passed",
        signals=signals,
        whitelisted_auto=True,
    )
    assert verdict == "allow"
    assert reason == "passed"
    assert stamp.get("critic_coupling_skipped") == "whitelisted_auto"


def test_run_critic_pass_applies_coupling(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "ab_trials.json").write_text(
        json.dumps(
            {
                "trials": [
                    {
                        "kind": "extract_block_to_helper",
                        "winner": "baseline",
                        "smoke_ok": True,
                        "graph_unchanged": False,
                    },
                    {
                        "kind": "extract_block_to_helper",
                        "winner": "baseline",
                        "smoke_ok": True,
                        "graph_unchanged": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "eurika.api.hypothesis_engine.hypothesis_ranking_signals",
        lambda _r: {"caution_weights": {"extract_block_to_helper": -40}, "prefer_safe_delta": 0},
    )
    ops = [
        {
            "target_file": "eurika/a.py",
            "kind": "extract_block_to_helper",
            "approval_state": "pending",
            "explainability": {"risk": "low"},
        }
    ]
    updated, decisions = run_critic_pass(
        ops, runtime_mode="assist", project_root=tmp_path
    )
    assert updated[0]["critic_verdict"] == "review"
    assert updated[0].get("critic_coupling_v0") is True
    assert updated[0].get("decision_source") == "critic_coupling"
    assert decisions[0]["verdict"] == "review"
    assert decisions[0].get("critic_coupling_v0") is True


def test_hard_deny_still_wins(tmp_path: Path) -> None:
    ops = [
        {
            "target_file": "x_extracted_extracted.py",
            "kind": "remove_unused_import",
            "approval_state": "pending",
        }
    ]
    updated, _ = run_critic_pass(ops, runtime_mode="assist", project_root=tmp_path)
    assert updated[0]["critic_verdict"] == "deny"


def test_load_signals_shape(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    sig = load_critic_coupling_signals(tmp_path)
    assert sig.get("version") == 2
    assert "planning" in sig
    assert "caution_weights" in sig
    assert sig.get("roles") == ["evidence", "verify", "hypothesis", "self"]
    assert any(p.get("id") == "missing_self_map" for p in sig.get("self_problems") or [])


def test_self_role_escalates_on_missing_self_map(tmp_path: Path) -> None:
    from eurika.api.critic_coupling import collect_critic_role_votes

    (tmp_path / ".eurika").mkdir()
    signals = load_critic_coupling_signals(tmp_path)
    votes = collect_critic_role_votes({"kind": "extract_block_to_helper"}, signals)
    by_role = {v["role"]: v["vote"] for v in votes}
    assert by_role["self"] == "caution"
    verdict, reason, stamp = couple_critic_verdict(
        {"kind": "extract_block_to_helper"},
        verdict="allow",
        reason="ok",
        signals=signals,
    )
    assert verdict == "review"
    assert "missing_self_map" in reason
    assert stamp.get("critic_roles_caution") >= 1
