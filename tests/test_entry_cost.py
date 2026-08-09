"""Tests for the entry cost gate: trade only when the move pays the fee."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.ml import entry_cost as ec
from eurika.ml.features import FEATURE_NAMES


def _feat(*, vol_z: float, atr_burst: float) -> dict[str, float]:
    base = {name: 0.0 for name in FEATURE_NAMES}
    base["vol_z"] = vol_z
    base["atr_burst"] = atr_burst
    return base


def _row(*, vol_z: float, atr_burst: float, ret: float, fee: float = 0.0009) -> dict:
    feat = _feat(vol_z=vol_z, atr_burst=atr_burst)
    return {
        "action": "BUY",
        "ret": ret,
        "fee": fee,
        "exit_reason": "model",
        "feature_vec": [feat[name] for name in FEATURE_NAMES],
    }


def test_expansion_score_is_the_weaker_of_both_signals() -> None:
    assert ec.expansion_score(_feat(vol_z=1.5, atr_burst=0.2)) == 0.2
    assert ec.expansion_score(_feat(vol_z=-0.4, atr_burst=2.0)) == -0.4
    vec = [0.0] * len(FEATURE_NAMES)
    vec[FEATURE_NAMES.index("vol_z")] = 0.8
    vec[FEATURE_NAMES.index("atr_burst")] = 1.1
    assert ec.expansion_score(vec) == 0.8


def test_expansion_score_none_when_features_missing() -> None:
    assert ec.expansion_score(None) is None
    assert ec.expansion_score({"vol_z": 1.0}) is None
    assert ec.expansion_score({"vol_z": "-", "atr_burst": 1.0}) is None


def test_gate_blocks_flat_market_and_passes_expansion() -> None:
    gate = {"expansion_min": 0.5, "cost_mult": 1.5}
    ok, why = ec.cost_gate_ok(_feat(vol_z=1.2, atr_burst=0.9), fee=0.0008, gate=gate)
    assert ok is True
    assert why == ""
    ok, why = ec.cost_gate_ok(_feat(vol_z=1.2, atr_burst=-0.3), fee=0.0008, gate=gate)
    assert ok is False
    assert "комиссию" in why
    # Reason carries the numbers so a rejected entry stays auditable.
    assert "-0.30" in why and "+0.50" in why


def test_gate_stays_open_when_features_are_unusable() -> None:
    ok, why = ec.cost_gate_ok(None, fee=0.0008, gate={"expansion_min": 0.5})
    assert ok is True
    assert why == ""


def test_legacy_fee_defaults_are_reinterpreted_per_side() -> None:
    assert ec._row_fee({"market": "spot", "fee": 0.001}) == 0.002
    assert ec._row_fee({"market": "futures", "fee": 0.0008}) == 0.001
    # Explicit/new rows and synthetic rows retain their recorded total.
    assert ec._row_fee({"market": "spot", "fee": 0.001, "fee_source": "override"}) == 0.001
    assert ec._row_fee({"fee": 0.0009}) == 0.0009


def test_calibration_picks_lowest_threshold_that_pays_the_fee(tmp_path: Path) -> None:
    # Flat market: edge below the fee. Expanding market: edge well above it.
    rows = [_row(vol_z=-1.0, atr_burst=-1.0, ret=0.0002) for _ in range(200)]
    rows += [_row(vol_z=1.2, atr_burst=1.1, ret=0.004) for _ in range(60)]
    out = ec.calibrate_cost_gate(tmp_path, rows=rows, min_samples=40)
    assert out["calibrated"] is True
    # Lowest rung whose own band pays, so flow stays as high as the economics allow.
    assert out["expansion_min"] == 0.75
    assert out["expected_edge"] > out["cost_mult"] * 0.0009
    assert out["samples"] == 60
    assert out["scanned"] == 260
    saved = json.loads(ec.cost_gate_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["expansion_min"] == 0.75


def test_calibration_opens_up_when_even_a_quiet_market_pays(tmp_path: Path) -> None:
    rows = [_row(vol_z=-1.0, atr_burst=-1.0, ret=0.01) for _ in range(80)]
    out = ec.calibrate_cost_gate(tmp_path, rows=rows, min_samples=40)
    assert out["calibrated"] is True
    assert out["expansion_min"] == -1.0


def test_calibration_will_not_lower_the_gate_without_evidence(tmp_path: Path) -> None:
    """The failure this guards: once the gate filters, the journal holds only
    trades it allowed, so a tail-average rule would conclude everything pays
    and unlock itself. A threshold may only drop into a band it has seen."""
    winners = [_row(vol_z=1.2, atr_burst=1.1, ret=0.004) for _ in range(120)]
    strict = ec.calibrate_cost_gate(tmp_path, rows=winners, min_samples=40, write=False)
    assert strict["expansion_min"] == 0.75

    # Same journal a week later, still only gate-approved trades in it.
    again = ec.calibrate_cost_gate(tmp_path, rows=winners, min_samples=40, write=False)
    assert again["expansion_min"] >= strict["expansion_min"]

    # Shadow rows from the refused region are what legitimately reopens it.
    with_shadows = winners + [_row(vol_z=-0.7, atr_burst=-0.6, ret=0.005) for _ in range(60)]
    reopened = ec.calibrate_cost_gate(tmp_path, rows=with_shadows, min_samples=40, write=False)
    assert reopened["expansion_min"] == -1.0


def test_calibration_ignores_a_losing_band_propped_up_from_above(tmp_path: Path) -> None:
    """A weak band must not slip through on the strength of the trades above it."""
    strong = [_row(vol_z=2.0, atr_burst=2.0, ret=0.02) for _ in range(200)]
    weak = [_row(vol_z=0.1, atr_burst=0.1, ret=-0.001) for _ in range(60)]
    out = ec.calibrate_cost_gate(tmp_path, rows=strong + weak, min_samples=40, write=False)
    assert out["expansion_min"] > 0.1


def test_calibration_falls_back_when_nothing_covers_the_fee(tmp_path: Path) -> None:
    rows = [_row(vol_z=v / 10.0, atr_burst=v / 10.0, ret=0.0001) for v in range(-60, 60)]
    out = ec.calibrate_cost_gate(tmp_path, rows=rows, min_samples=40)
    assert out["calibrated"] is False
    assert out["expansion_min"] == ec.DEFAULT_EXPANSION_MIN
    assert out["retained_previous"] is False


def test_failed_recalibration_preserves_previous_stricter_gate(tmp_path: Path) -> None:
    path = ec.cost_gate_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "expansion_min": 1.0,
                "expected_edge": 0.002,
                "cost_mult": 1.5,
                "samples": 80,
                "calibrated": True,
            }
        ),
        encoding="utf-8",
    )
    losing = [
        _row(vol_z=v / 10.0, atr_burst=v / 10.0, ret=0.0001)
        for v in range(-60, 60)
    ]

    out = ec.calibrate_cost_gate(tmp_path, rows=losing, min_samples=40)

    assert out["calibrated"] is False
    assert out["retained_previous"] is True
    assert out["expansion_min"] == 1.0
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["expansion_min"] == 1.0


def test_calibration_ignores_cancelled_rows(tmp_path: Path) -> None:
    rows = [_row(vol_z=2.0, atr_burst=2.0, ret=0.004) for _ in range(50)]
    for row in rows[:10]:
        row["exit_reason"] = "cancel_expire"
    out = ec.calibrate_cost_gate(tmp_path, rows=rows, min_samples=10)
    assert out["scanned"] == 40


def test_loaded_gate_is_cached_until_the_file_changes(tmp_path: Path) -> None:
    assert ec.load_cost_gate(tmp_path)["source"] == "default"
    ec.calibrate_cost_gate(
        tmp_path,
        rows=[_row(vol_z=2.0, atr_burst=2.0, ret=0.004) for _ in range(50)],
        min_samples=10,
    )
    conf = ec.load_cost_gate(tmp_path)
    assert conf["source"] == "calibrated"
    assert conf["expansion_min"] == 2.0


def test_corrupt_gate_file_falls_back_to_default(tmp_path: Path) -> None:
    path = ec.cost_gate_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    conf = ec.load_cost_gate(tmp_path)
    assert conf["source"] == "default"
    assert conf["expansion_min"] == ec.DEFAULT_EXPANSION_MIN
