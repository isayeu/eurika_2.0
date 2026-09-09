"""Planning coupling v0 — soft A/B + verify_by_kind into bug-hunt ranking."""
from __future__ import annotations

import json
from pathlib import Path

from eurika.api.planning_coupling import (
    load_planning_signals,
    score_delta_for_kind,
    stamp_planning_on_ops,
)
from eurika.orchestration.bug_hunt import list_bug_hunt_candidates


def _op(target: str, kind: str) -> dict:
    return {
        "target_file": target,
        "kind": kind,
        "smell_type": "test",
        "description": f"{kind} on {target}",
        "params": {},
    }


def test_ab_baseline_bias_demotes_kind(tmp_path: Path) -> None:
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
                    {
                        "kind": "remove_unused_import",
                        "winner": "sandbox",
                        "smoke_ok": True,
                        "graph_unchanged": False,
                    },
                    {
                        "kind": "remove_unused_import",
                        "winner": "sandbox",
                        "smoke_ok": True,
                        "graph_unchanged": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    for rel in ("eurika/a.py", "eurika/b.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x=1\n", encoding="utf-8")

    signals = load_planning_signals(tmp_path)
    d_ext, st_ext = score_delta_for_kind("extract_block_to_helper", signals)
    d_imp, st_imp = score_delta_for_kind("remove_unused_import", signals)
    assert d_ext < 0 and st_ext.get("planning_ab_bias") == "baseline"
    assert d_imp > 0 and st_imp.get("planning_ab_bias") == "sandbox"

    ops = [
        _op("eurika/a.py", "extract_block_to_helper"),
        _op("eurika/b.py", "remove_unused_import"),
    ]
    ranked = list_bug_hunt_candidates(tmp_path, operations=ops, allow_llm=False)
    assert ranked[0]["kind"] == "remove_unused_import"
    assert ranked[0].get("planning_coupling_v0") is True
    assert ranked[0].get("planning_ab_bias") == "sandbox"


def test_verify_low_rate_demotes_kind(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".eurika").mkdir()

    def _fake_metrics(_root):
        return {
            "verify_by_kind": {
                "by_kind": {
                    "extract_block_to_helper": {
                        "verify_success": 1,
                        "verify_fail": 4,
                        "rate": 0.2,
                        "total": 5,
                    },
                    "remove_unused_import": {
                        "verify_success": 5,
                        "verify_fail": 0,
                        "rate": 1.0,
                        "total": 5,
                    },
                }
            }
        }

    monkeypatch.setattr(
        "eurika.api.experiment_memory.compute_self_improvement_metrics",
        _fake_metrics,
    )
    for rel in ("eurika/a.py", "eurika/b.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x=1\n", encoding="utf-8")
    ops = [
        _op("eurika/a.py", "extract_block_to_helper"),
        _op("eurika/b.py", "remove_unused_import"),
    ]
    ranked = list_bug_hunt_candidates(tmp_path, operations=ops, allow_llm=False)
    assert ranked[0]["kind"] == "remove_unused_import"
    cautioned = [r for r in ranked if r["kind"] == "extract_block_to_helper"][0]
    assert cautioned.get("planning_verify_delta") == -20


def test_graph_unchanged_tie_ignored() -> None:
    from eurika.api.planning_coupling import _ab_kind_bias

    bias = _ab_kind_bias(
        [
            {"kind": "k", "winner": "tie", "graph_unchanged": True, "smoke_ok": True},
            {"kind": "k", "winner": "tie", "graph_unchanged": True, "smoke_ok": True},
            {"kind": "k", "winner": "insufficient", "smoke_ok": True},
        ]
    )
    assert bias == {}


def test_stamp_planning_on_ops() -> None:
    signals = {
        "ab_by_kind": {"remove_unused_import": {"bias": "sandbox", "delta": 15}},
        "verify_low_by_kind": {},
    }
    ops = [_op("a.py", "remove_unused_import"), _op("b.py", "clean_imports")]
    stamped = stamp_planning_on_ops(ops, signals)
    assert stamped[0].get("planning_ab_bias") == "sandbox"
    assert "planning_coupling_v0" not in stamped[1]
