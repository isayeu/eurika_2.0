"""Tests for patch_engine.simulate_patch (ROADMAP v3.0 Stage 2)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from patch_engine import simulate_patch


def test_simulate_patch_no_write(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")
    plan = {
        "operations": [
            {
                "target_file": "x.py",
                "kind": "refactor_module",
                "diff": "\n# added\n",
                "description": "test",
            }
        ]
    }
    result = simulate_patch(tmp_path, plan)
    assert result["simulation_only"] is True
    assert result["dry_run"] is True
    assert "x.py" in result["would_modify"]
    assert (tmp_path / "x.py").read_text() == "a = 1\n"  # unchanged


def test_simulate_patch_missing_file(tmp_path: Path) -> None:
    plan = {
        "operations": [
            {
                "target_file": "nonexistent.py",
                "kind": "refactor_module",
                "diff": "\n# x\n",
                "description": "test",
            }
        ]
    }
    result = simulate_patch(tmp_path, plan)
    assert "nonexistent.py" in result["would_skip"]
    assert result["operations_count"] == 1
