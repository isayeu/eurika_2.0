"""Formal A/B v0 — baseline vs sandbox fixed metrics."""
from __future__ import annotations

import json
from pathlib import Path

from eurika.evaluation.ab_compare import (
    ab_trials_path,
    compare_ab,
    decide_ab_winner,
    format_ab_text,
    load_ab_trials,
    persist_ab_trial,
    run_ab_compare,
)


def _snap(**kwargs):
    base = {
        "ok": True,
        "insufficient_data": False,
        "energy": 10.0,
        "score": 0.5,
        "risk_score": 0.8,
        "total_smells": 5,
        "cycles": 1,
    }
    base.update(kwargs)
    return base


def test_decide_ab_winner_smoke_fail() -> None:
    w, _rule, insuff = decide_ab_winner(_snap(), _snap(), smoke_ok=False)
    assert w == "baseline"
    assert insuff is False


def test_decide_ab_winner_tie_and_sandbox() -> None:
    b = _snap()
    w, _, _ = decide_ab_winner(b, dict(b), smoke_ok=True)
    assert w == "tie"
    better = _snap(energy=8.0, total_smells=3, cycles=0, risk_score=0.9)
    w2, _, _ = decide_ab_winner(b, better, smoke_ok=True)
    assert w2 == "sandbox"
    worse = _snap(energy=12.0)
    w3, _, _ = decide_ab_winner(b, worse, smoke_ok=True)
    assert w3 == "baseline"


def test_decide_ab_winner_layer_regression() -> None:
    b = _snap(layer_violations=0)
    worse = _snap(energy=8.0, total_smells=3, cycles=0, risk_score=0.9, layer_violations=2)
    w, rule, _ = decide_ab_winner(b, worse, smoke_ok=True)
    assert w == "baseline"
    assert "layer_violations" in rule


def test_decide_ab_winner_insufficient() -> None:
    bad = {"ok": False, "insufficient_data": True, "energy": None}
    w, _, insuff = decide_ab_winner(bad, bad, smoke_ok=True)
    assert w == "insufficient"
    assert insuff is True


def test_persist_and_format(tmp_path: Path) -> None:
    trial = compare_ab(
        _snap(),
        _snap(energy=9.0),
        smoke_ok=True,
        sandbox_mode="copy",
        source="test",
        kind="extract_block_to_helper",
        target="pkg/a.py",
        proposal_hash="abc123",
    )
    assert trial["winner"] == "sandbox"
    assert trial["version"] == 2
    assert "layer_violations" in trial["delta"]
    persist_ab_trial(tmp_path, trial)
    assert ab_trials_path(tmp_path).is_file()
    loaded = load_ab_trials(tmp_path)
    assert len(loaded) == 1
    text = format_ab_text(tmp_path)
    assert "Formal A/B" in text
    assert "sandbox" in text


def test_run_ab_compare_without_self_map(tmp_path: Path, monkeypatch) -> None:
    main = tmp_path / "main"
    sand = tmp_path / "sand"
    main.mkdir()
    sand.mkdir()
    (main / ".eurika").mkdir()
    monkeypatch.setenv("EURIKA_AB_RESCAN", "off")
    trial = run_ab_compare(
        main,
        sand,
        smoke_ok=True,
        sandbox_mode="copy",
        operation={"kind": "clean_imports", "target_file": "x.py"},
        source="unit",
    )
    assert trial["winner"] == "insufficient"
    assert trial["smoke_ok"] is True
    assert trial.get("rescan_mode") == "off"
    assert load_ab_trials(main)


def test_seed_self_map_from_main(tmp_path: Path, monkeypatch) -> None:
    """Worktree often lacks gitignored self_map — seed enables tie/graph_unchanged."""
    main = tmp_path / "main"
    sand = tmp_path / "sand"
    main.mkdir()
    sand.mkdir()
    (main / ".eurika").mkdir()
    monkeypatch.setenv("EURIKA_AB_RESCAN", "off")

    def _fake_snap(root):
        root = Path(root)
        if (root / "self_map.json").is_file():
            return {
                "ok": True,
                "insufficient_data": False,
                "energy": 1.0,
                "score": 0.5,
                "risk_score": 10,
                "total_smells": 2,
                "cycles": 0,
            }
        return {
            "ok": False,
            "insufficient_data": True,
            "error": "self_map.json missing",
            "energy": None,
            "score": None,
            "risk_score": None,
            "total_smells": None,
            "cycles": None,
        }

    (main / "self_map.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "eurika.evaluation.ab_compare.snapshot_ab_metrics", _fake_snap
    )
    trial = run_ab_compare(
        main,
        sand,
        smoke_ok=True,
        sandbox_mode="worktree",
        operation={"kind": "remove_unused_import", "target_file": "p.py"},
        source="unit",
    )
    assert trial["self_map_seeded"] is True
    assert trial["winner"] == "tie"
    assert trial["graph_unchanged"] is True
    assert trial.get("rescanned") is False
    assert (sand / "self_map.json").is_file()


def test_assess_metrics_stability_and_auto_rescan(tmp_path: Path, monkeypatch) -> None:
    from eurika.evaluation.ab_compare import (
        assess_metrics_stability,
        decide_ab_rescan,
    )

    eurika = tmp_path / ".eurika"
    eurika.mkdir()
    # unstable: not enough points
    assert assess_metrics_stability(tmp_path)["stable"] is False

    points = [
        {"modules": 100, "total_smells": 10, "cycles": 0},
        {"modules": 100, "total_smells": 10, "cycles": 0},
        {"modules": 101, "total_smells": 11, "cycles": 0},
        {"modules": 101, "total_smells": 11, "cycles": 0},
        {"modules": 101, "total_smells": 12, "cycles": 0},
    ]
    (eurika / "history.json").write_text(
        json.dumps({"history": points}), encoding="utf-8"
    )
    stab = assess_metrics_stability(tmp_path)
    assert stab["stable"] is True
    assert stab["smell_swing"] == 2

    monkeypatch.setenv("EURIKA_AB_RESCAN", "auto")
    do, meta = decide_ab_rescan(tmp_path, self_map_seeded=True)
    assert do is True
    assert meta["rescan_mode"] == "auto"
    do2, meta2 = decide_ab_rescan(tmp_path, self_map_seeded=False)
    assert do2 is False
    assert "already present" in str(meta2.get("skip_reason") or "")

    monkeypatch.setenv("EURIKA_AB_RESCAN", "off")
    assert decide_ab_rescan(tmp_path, self_map_seeded=True)[0] is False

    monkeypatch.setenv("EURIKA_AB_RESCAN", "on")
    assert decide_ab_rescan(tmp_path, self_map_seeded=False)[0] is True


def test_auto_rescan_runs_scan_when_stable(tmp_path: Path, monkeypatch) -> None:
    import json as _json

    main = tmp_path / "main"
    sand = tmp_path / "sand"
    main.mkdir()
    sand.mkdir()
    eurika = main / ".eurika"
    eurika.mkdir()
    points = [
        {"modules": 10, "total_smells": 2, "cycles": 0} for _ in range(5)
    ]
    (eurika / "history.json").write_text(
        _json.dumps({"history": points}), encoding="utf-8"
    )
    (main / "self_map.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("EURIKA_AB_RESCAN", "auto")
    called: list[Path] = []

    def _fake_snap(root):
        root = Path(root).resolve()
        if (root / "self_map.json").is_file():
            # After rescan, pretend smells dropped in sandbox only.
            smells = 1 if root == sand.resolve() and called else 2
            return {
                "ok": True,
                "insufficient_data": False,
                "energy": float(smells),
                "score": 0.5,
                "risk_score": 10,
                "total_smells": smells,
                "cycles": 0,
            }
        return {
            "ok": False,
            "insufficient_data": True,
            "error": "missing",
            "energy": None,
            "score": None,
            "risk_score": None,
            "total_smells": None,
            "cycles": None,
        }

    def _fake_rescan(sandbox_root: Path) -> bool:
        called.append(Path(sandbox_root))
        return True

    monkeypatch.setattr(
        "eurika.evaluation.ab_compare.snapshot_ab_metrics", _fake_snap
    )
    monkeypatch.setattr(
        "eurika.evaluation.ab_compare._run_sandbox_rescan", _fake_rescan
    )
    trial = run_ab_compare(
        main,
        sand,
        smoke_ok=True,
        sandbox_mode="worktree",
        operation={"kind": "k", "target_file": "t.py"},
        source="unit",
    )
    assert called and called[0] == sand.resolve()
    assert trial["rescanned"] is True
    assert trial["metrics_stable"] is True
    assert trial["winner"] == "sandbox"
    assert trial["graph_unchanged"] is False


def test_ab_compare_chat_and_cli(tmp_path: Path) -> None:
    from argparse import Namespace

    from cli.core_handlers_ab_compare import handle_ab_compare
    from eurika.api import chat as chat_mod
    from eurika.api.chat_direct import resolve_direct_handler

    persist_ab_trial(
        tmp_path,
        compare_ab(
            _snap(),
            _snap(),
            smoke_ok=True,
            kind="k",
            target="t.py",
            proposal_hash="h1",
        ),
    )
    assert resolve_direct_handler(tmp_path, "a/b")[0] == "ab_compare"
    assert resolve_direct_handler(tmp_path, "сравни sandbox")[0] == "ab_compare"
    out = chat_mod.chat_send(tmp_path, "a/b")
    assert out.get("error") is None
    assert "Formal A/B" in (out.get("text") or "")
    code = handle_ab_compare(Namespace(path=tmp_path, json=True, quiet=False))
    assert code == 0
