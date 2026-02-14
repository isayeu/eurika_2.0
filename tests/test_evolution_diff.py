"""Tests for eurika.evolution.diff (build_snapshot, diff_snapshots, diff_to_text).

Contract: public API lives in eurika.evolution.diff; flat architecture_diff is re-export.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.evolution.diff import (
    ArchSnapshot,
    build_snapshot,
    diff_snapshots,
    diff_to_text,
)


def _write_self_map(path: Path, modules: list, dependencies: dict) -> None:
    data = {
        "modules": [{"path": p, "lines": 10, "functions": [], "classes": []} for p in modules],
        "dependencies": dependencies,
        "summary": {"files": len(modules), "total_lines": 10 * len(modules)},
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_build_snapshot_from_self_map(tmp_path: Path) -> None:
    """eurika.evolution.diff.build_snapshot loads self_map and returns ArchSnapshot."""
    old_path = tmp_path / "old.json"
    _write_self_map(old_path, ["a.py", "b.py"], {"a.py": ["b"]})

    snap = build_snapshot(old_path)

    assert isinstance(snap, ArchSnapshot)
    assert snap.path == old_path
    assert set(snap.modules) == {"a.py", "b.py"}
    assert "nodes" in snap.graph_summary
    assert "maturity" in snap.summary
    assert "system" in snap.summary


def test_diff_snapshots_and_diff_to_text(tmp_path: Path) -> None:
    """eurika.evolution.diff: diff_snapshots returns dict; diff_to_text renders it."""
    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    _write_self_map(old_path, ["a.py", "b.py"], {"a.py": ["b"]})
    _write_self_map(new_path, ["a.py", "b.py", "c.py"], {"a.py": ["b"], "c.py": ["a"]})

    old_snap = build_snapshot(old_path)
    new_snap = build_snapshot(new_path)
    diff = diff_snapshots(old_snap, new_snap)

    assert "structures" in diff
    assert "modules_added" in diff["structures"]
    assert "c.py" in diff["structures"]["modules_added"]
    assert "centrality_shifts" in diff
    assert "maturity" in diff
    assert "recommended_actions" in diff

    text = diff_to_text(diff)
    assert "ARCHITECTURE EVOLUTION REPORT" in text
    assert "Structural changes" in text or "modules added" in text
