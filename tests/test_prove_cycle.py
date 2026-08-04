"""Tests for eurika prove-cycle (deterministic patch→verify→learning)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.orchestration.prove_cycle import (
    DRILL_REL_PATH,
    build_prove_operation,
    run_prove_cycle,
    seed_prove_drill_file,
)


def test_seed_prove_drill_has_unused_import(tmp_path: Path) -> None:
    path = seed_prove_drill_file(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "import os" in text
    assert "from pathlib import Path" in text


def test_build_prove_operation_targets_drill(tmp_path: Path) -> None:
    op = build_prove_operation(tmp_path)
    assert op["kind"] == "remove_unused_import"
    assert op["target_file"] == DRILL_REL_PATH


def test_prove_cycle_dry_run(tmp_path: Path) -> None:
    out = run_prove_cycle(tmp_path, dry_run=True, quiet=True)
    assert out.get("dry_run") is True
    assert out.get("prove_cycle") is True
    assert (tmp_path / DRILL_REL_PATH).is_file()


def test_prove_cycle_apply_verify_and_learning(tmp_path: Path) -> None:
    """Full loop: apply remove_unused_import, custom verify passes, drill file cleaned."""
    out = run_prove_cycle(tmp_path, dry_run=False, quiet=True, verify_timeout=60)
    assert out.get("prove_cycle") is True
    assert out.get("verify_success") is True, out
    drill = tmp_path / DRILL_REL_PATH
    text = drill.read_text(encoding="utf-8")
    assert "import os" not in text
    assert "from pathlib import Path" in text
    assert DRILL_REL_PATH in (out.get("modified") or [])
