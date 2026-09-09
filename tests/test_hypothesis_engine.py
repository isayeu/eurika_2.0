"""Hypothesis Engine v0."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.hypothesis_engine import (
    format_hypotheses_text,
    generate_hypotheses,
    hypotheses_path,
    load_hypotheses,
    refresh_hypotheses,
)


def _write_hitl(tmp: Path, *, approve: int, reject: int, apply_ok: int = 0, apply_fail: int = 0) -> None:
    eurika = tmp / ".eurika"
    eurika.mkdir(parents=True, exist_ok=True)
    (eurika / "hitl_journal.json").write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-09-08T00:00:00",
                "decisions": [],
                "applies": [],
                "aggregates": {
                    "approve": approve,
                    "reject": reject,
                    "apply_ok": apply_ok,
                    "apply_fail": apply_fail,
                },
            }
        ),
        encoding="utf-8",
    )


def test_generate_hitl_volume_and_apply_loop(tmp_path: Path) -> None:
    _write_hitl(tmp_path, approve=1, reject=0, apply_ok=0)
    hyps = generate_hypotheses(tmp_path)
    kinds = {h["kind"] for h in hyps}
    assert "hitl_volume" in kinds
    assert "apply_loop" in kinds
    hitl = next(h for h in hyps if h["kind"] == "hitl_volume")
    assert hitl["status"] == "insufficient"
    assert hitl["evidence"]
    assert hitl["expected"]["metric"] == "hitl.n"
    apply = next(h for h in hyps if h["kind"] == "apply_loop")
    assert apply["expected"]["metric"] == "hitl.apply_ok"
    assert apply["expected"]["op"] == ">="


def test_evaluate_apply_ok_supported(tmp_path: Path) -> None:
    _write_hitl(tmp_path, approve=2, reject=1, apply_ok=0)
    payload = refresh_hypotheses(tmp_path)
    assert hypotheses_path(tmp_path).is_file()
    kinds = {r["kind"]: r for r in payload["records"]}
    assert "apply_loop" in kinds
    assert kinds["apply_loop"]["status"] in {"open", "insufficient"}

    _write_hitl(tmp_path, approve=2, reject=1, apply_ok=1)
    again = refresh_hypotheses(tmp_path)
    apply = next(r for r in again["records"] if r["kind"] == "apply_loop")
    assert apply["status"] == "supported"
    assert apply["actual"]["value"] == 1


def test_idle_gap_hypothesis(tmp_path: Path) -> None:
    eurika = tmp_path / ".eurika"
    eurika.mkdir()
    (eurika / "idle_self_dev.json").write_text(
        json.dumps(
            {
                "drill_ok": {"imports": 1, "extractable_block": 5},
                "last_drill": "imports",
                "last_ok": True,
            }
        ),
        encoding="utf-8",
    )
    _write_hitl(tmp_path, approve=0, reject=0)
    hyps = generate_hypotheses(tmp_path)
    idle = [h for h in hyps if h["kind"] == "idle_gap"]
    assert idle
    assert "imports" in idle[0]["claim"]
    assert idle[0]["expected"]["op"] == "incr"


def test_empty_project_no_fake_success(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    hyps = generate_hypotheses(tmp_path)
    # May emit hitl_volume meta only — never claim code quality success
    for h in hyps:
        assert h.get("evidence"), h
        assert h.get("expected"), h
        assert "умнее" not in (h.get("claim") or "").lower()
    text = format_hypotheses_text(refresh_hypotheses(tmp_path), mode="full")
    assert "Hypothesis Engine" in text


def test_hypotheses_chat_and_cli(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod
    from argparse import Namespace

    from cli.core_handlers_hypothesis import handle_hypotheses
    from eurika.api.chat_direct import resolve_direct_handler

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    _write_hitl(tmp_path, approve=1, reject=0, apply_ok=0)
    assert resolve_direct_handler(tmp_path, "гипотезы")[0] == "hypotheses"
    assert resolve_direct_handler(tmp_path, "какие гипотезы?")[0] == "hypotheses"
    out = chat_mod.chat_send(tmp_path, "гипотезы")
    assert out.get("error") is None
    assert "Hypothesis Engine" in (out.get("text") or "")
    assert hypotheses_path(tmp_path).is_file()

    code = handle_hypotheses(Namespace(path=tmp_path, json=True, quiet=False))
    assert code == 0
    loaded = load_hypotheses(tmp_path)
    assert isinstance(loaded, list)


def test_experiment_memory_has_structured_expected(tmp_path: Path) -> None:
    from eurika.api.experiment_memory import load_experiments
    from eurika.orchestration.team_mode import save_pending_plan

    (tmp_path / ".eurika").mkdir()
    ops = [
        {
            "kind": "extract_block_to_helper",
            "target_file": "a.py",
            "description": "extract helper",
        }
    ]
    save_pending_plan(
        tmp_path,
        {"source": "bug_hunt", "drill": "bug_hunt"},
        ops,
        [],
        notify_telegram=False,
    )
    recs = load_experiments(tmp_path)
    assert len(recs) == 1
    assert recs[0].get("expected_result")
    assert isinstance(recs[0].get("expected"), dict)
    assert recs[0]["expected"].get("metric") == "hitl.apply_ok"
    assert isinstance(recs[0].get("evidence"), list)
    assert recs[0]["evidence"]


def test_caution_action_kinds_and_persisted_action_kind(tmp_path: Path) -> None:
    import json

    from eurika.api.hypothesis_engine import (
        caution_action_kinds,
        load_hypotheses,
        refresh_hypotheses,
    )

    eurika = tmp_path / ".eurika"
    eurika.mkdir()
    (eurika / "hitl_journal.json").write_text(
        json.dumps(
            {
                "aggregates": {"approve": 0, "reject": 2, "apply_ok": 0, "apply_fail": 0},
                "decisions": [
                    {
                        "decision": "reject",
                        "kind": "extract_block_to_helper",
                        "target": "a.py",
                        "proposal_hash": "h1",
                        "ts_ms": 1,
                    },
                    {
                        "decision": "reject",
                        "kind": "extract_block_to_helper",
                        "target": "b.py",
                        "proposal_hash": "h2",
                        "ts_ms": 2,
                    },
                ],
                "applies": [],
            }
        ),
        encoding="utf-8",
    )
    assert "extract_block_to_helper" in caution_action_kinds(tmp_path)
    payload = refresh_hypotheses(tmp_path)
    rej = [r for r in payload["records"] if r.get("kind") == "reject_pattern"]
    assert rej
    assert rej[0].get("action_kind") == "extract_block_to_helper"
    assert str(rej[0].get("claim_key") or "").startswith("reject_")
    again = refresh_hypotheses(tmp_path)
    rej2 = [r for r in again["records"] if r.get("kind") == "reject_pattern"]
    assert rej2[0].get("action_kind") == "extract_block_to_helper"
    disk = load_hypotheses(tmp_path)
    assert any(r.get("action_kind") == "extract_block_to_helper" for r in disk)


def test_multi_reject_pattern_and_rank_order(tmp_path: Path) -> None:
    from eurika.api.hypothesis_engine import (
        generate_hypotheses,
        hypothesis_ranking_signals,
        rank_hypotheses,
        refresh_hypotheses,
    )

    eurika = tmp_path / ".eurika"
    eurika.mkdir()
    (eurika / "hitl_journal.json").write_text(
        json.dumps(
            {
                "aggregates": {"approve": 0, "reject": 5, "apply_ok": 0, "apply_fail": 0},
                "decisions": [
                    {"decision": "reject", "kind": "extract_block_to_helper", "target": "a.py", "ts_ms": 1},
                    {"decision": "reject", "kind": "extract_block_to_helper", "target": "b.py", "ts_ms": 2},
                    {"decision": "reject", "kind": "extract_block_to_helper", "target": "c.py", "ts_ms": 3},
                    {"decision": "reject", "kind": "clean_imports", "target": "d.py", "ts_ms": 4},
                    {"decision": "reject", "kind": "clean_imports", "target": "e.py", "ts_ms": 5},
                ],
                "applies": [],
            }
        ),
        encoding="utf-8",
    )
    gen = generate_hypotheses(tmp_path)
    rejects = [h for h in gen if h.get("kind") == "reject_pattern"]
    assert len(rejects) >= 2
    kinds = {h.get("action_kind") for h in rejects}
    assert "extract_block_to_helper" in kinds
    assert "clean_imports" in kinds

    ranked = rank_hypotheses(gen)
    assert ranked[0].get("rank_score") >= ranked[-1].get("rank_score")
    # reject_pattern should outrank hitl_volume / apply_loop when present
    top_kinds = [r.get("kind") for r in ranked[:3]]
    assert "reject_pattern" in top_kinds

    signals = hypothesis_ranking_signals(tmp_path)
    assert "extract_block_to_helper" in signals["caution_weights"]
    assert "clean_imports" in signals["caution_weights"]
    assert signals["caution_weights"]["extract_block_to_helper"] <= -25

    payload = refresh_hypotheses(tmp_path)
    assert payload.get("ranking_version") == 1
    assert "rank=" in format_hypotheses_text(payload, mode="full")
    assert payload["records"][0].get("rank_score") is not None
