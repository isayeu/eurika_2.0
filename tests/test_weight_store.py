"""Tests for WeightStore (ROADMAP §5.7 этап 7)."""

import os
from pathlib import Path

from eurika.analysis.weight_store import (
    DEFAULT_DELTA,
    MAX_DELTA,
    MIN_DELTA,
    WEIGHTS_VERSION,
    adapt_weights_from_experience,
    freeze_weights,
    get_estimated_delta,
    load_weights,
    metrics_schema_hash,
    save_weights,
)


def test_load_weights_empty_returns_defaults(tmp_path: Path) -> None:
    """load_weights with no file returns defaults."""
    w = load_weights(tmp_path)
    assert ("god_module", "split_module") in w
    assert w[("god_module", "split_module")] == 0.15


def test_save_and_load_weights(tmp_path: Path) -> None:
    """save_weights persists; load_weights merges with defaults."""
    custom = {("god_module", "split_module"): 0.20}
    save_weights(tmp_path, custom)
    w = load_weights(tmp_path)
    assert w[("god_module", "split_module")] == 0.20
    assert ("deep_nesting", "refactor_code_smell") in w  # from defaults merge


def test_get_estimated_delta_no_project_uses_defaults() -> None:
    """get_estimated_delta(project_root=None) uses hardcoded defaults."""
    assert get_estimated_delta(None, "god_module", "split_module") == 0.15
    assert get_estimated_delta(None, "unknown", "unknown") == DEFAULT_DELTA


def test_get_estimated_delta_with_project(tmp_path: Path) -> None:
    """get_estimated_delta uses stored weights when available."""
    save_weights(tmp_path, {("god_module", "split_module"): 0.22})
    assert get_estimated_delta(tmp_path, "god_module", "split_module") == 0.22
    assert get_estimated_delta(tmp_path, "x", "y") == DEFAULT_DELTA


def test_freeze_weights_rv8(tmp_path: Path) -> None:
    """RV8: freeze_weights returns snapshot; adapt does not affect snapshot during cycle."""
    save_weights(tmp_path, {("god_module", "split_module"): 0.18})
    snap = freeze_weights(tmp_path)
    assert isinstance(snap, dict)
    assert snap[("god_module", "split_module")] == 0.18
    # Snapshot is a copy: changing on-disk weights doesn't affect it
    save_weights(tmp_path, {("god_module", "split_module"): 0.25})
    assert snap[("god_module", "split_module")] == 0.18


def test_adapt_weights_from_experience(tmp_path: Path) -> None:
    """adapt_weights adjusts based on success/fail stats."""
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.storage import record_outcome

        # Add many successes for god_module|split_module
        for _ in range(8):
            record_outcome(
                tmp_path,
                ["m.py"],
                [{"kind": "split_module", "smell_type": "god_module"}],
                [],
                True,
            )
        for _ in range(2):
            record_outcome(
                tmp_path,
                ["m.py"],
                [{"kind": "split_module", "smell_type": "god_module"}],
                [],
                False,
            )
        # 80% success -> should increase estimated_delta (success_rate heuristic, no delta_energy in events)
        changed = adapt_weights_from_experience(tmp_path, learning_rate=0.03, use_delta_energy=False)
        assert changed
        w = load_weights(tmp_path)
        assert w[("god_module", "split_module")] > 0.15
        assert w[("god_module", "split_module")] <= MAX_DELTA
    finally:
        if "EURIKA_DISABLE_GLOBAL_MEMORY" in os.environ:
            del os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"]


def test_adapt_weights_bounded(tmp_path: Path) -> None:
    """adapt_weights keeps values in [MIN_DELTA, MAX_DELTA]."""
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.storage import record_outcome

        # Many fails for long_function|extract_block_to_helper
        for _ in range(10):
            record_outcome(
                tmp_path,
                ["x.py"],
                [{"kind": "extract_block_to_helper", "smell_type": "long_function"}],
                [],
                False,
            )
        adapt_weights_from_experience(tmp_path, learning_rate=0.1, use_delta_energy=False)
        w = load_weights(tmp_path)
        val = w[("long_function", "extract_block_to_helper")]
        assert val >= MIN_DELTA
        assert val <= MAX_DELTA
    finally:
        if "EURIKA_DISABLE_GLOBAL_MEMORY" in os.environ:
            del os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"]


def test_rv6_versioned_format_and_legacy_migration(tmp_path: Path) -> None:
    """RV6: new format has version/schema_hash; legacy format still loads and migrates."""
    # Legacy format (pre-RV6)
    legacy = {"god_module|split_module": 0.19, "hub|split_module": 0.16}
    path = tmp_path / ".eurika" / "weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"god_module|split_module": 0.19, "hub|split_module": 0.16}')
    w = load_weights(tmp_path)
    assert w[("god_module", "split_module")] == 0.19
    assert w[("hub", "split_module")] == 0.16
    # Save rewrites in new format
    save_weights(tmp_path, w)
    raw = __import__("json").loads(path.read_text())
    assert raw["version"] == WEIGHTS_VERSION
    assert "schema_hash" in raw
    assert raw["schema_hash"] == metrics_schema_hash()
    assert "weights" in raw
    # Reload from new format
    w2 = load_weights(tmp_path)
    assert w2[("god_module", "split_module")] == 0.19


def test_adapt_weights_delta_energy_mode(tmp_path: Path) -> None:
    """P6/R9: use_delta_energy=True uses W -= lr*delta from learn events."""
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.storage import record_outcome

        # Improvement: delta_energy negative -> W should increase
        record_outcome(
            tmp_path,
            ["m.py"],
            [{"kind": "split_module", "smell_type": "god_module"}],
            [],
            True,
            delta_energy=-0.1,  # improvement (after < before)
        )
        changed = adapt_weights_from_experience(
            tmp_path, learning_rate=0.05, use_delta_energy=True
        )
        assert changed
        w = load_weights(tmp_path)
        # Negative delta -> W increases (0.15 + 0.05*0.1 = 0.155)
        assert w[("god_module", "split_module")] > 0.15

        # Regression: delta_energy positive -> W should decrease
        save_weights(tmp_path, {("hub", "split_module"): 0.20})
        record_outcome(
            tmp_path,
            ["h.py"],
            [{"kind": "split_module", "smell_type": "hub"}],
            [],
            False,
            delta_energy=0.05,  # regression
        )
        adapt_weights_from_experience(
            tmp_path, learning_rate=0.05, use_delta_energy=True
        )
        w2 = load_weights(tmp_path)
        assert w2[("hub", "split_module")] < 0.20
    finally:
        if "EURIKA_DISABLE_GLOBAL_MEMORY" in os.environ:
            del os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"]
