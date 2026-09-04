"""Tests for eurika prove-cycle (deterministic patch→verify→learning)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.orchestration.prove_cycle import (
    DRILL_REL_PATH,
    POLYGON_EXTRACTABLE_REL,
    POLYGON_IMPORTS_REL,
    build_polygon_propose_operation,
    build_prove_operation,
    format_prove_cycle_summary,
    normalize_propose_drill,
    run_prove_cycle,
    seed_prove_drill_file,
)
from eurika.orchestration.team_mode import load_approved_operations
from eurika.refactor.remove_unused_import import remove_unused_imports
from patch_apply import apply_patch_plan


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


def test_propose_dry_run_does_not_seed_or_write_plan(tmp_path: Path) -> None:
    out = run_prove_cycle(tmp_path, dry_run=True, propose=True, quiet=True)
    assert out.get("propose") is True
    assert out.get("dry_run") is True
    assert out.get("modified") == []
    assert not (tmp_path / POLYGON_IMPORTS_REL).exists()
    assert not (tmp_path / ".eurika" / "pending_plan.json").exists()
    assert "Approvals" in format_prove_cycle_summary(out)


def test_propose_writes_pending_plan_no_disk_clean(tmp_path: Path) -> None:
    out = run_prove_cycle(tmp_path, propose=True, quiet=True)
    assert out.get("ok") is True
    assert out.get("propose") is True
    assert out.get("verify_success") is None
    assert out.get("modified") == []
    target = tmp_path / POLYGON_IMPORTS_REL
    assert target.is_file()
    assert "import os" in target.read_text(encoding="utf-8")
    pending = tmp_path / ".eurika" / "pending_plan.json"
    assert pending.is_file()
    data = json.loads(pending.read_text(encoding="utf-8"))
    ops = data.get("operations") or []
    assert len(ops) == 1
    assert ops[0]["kind"] == "remove_unused_import"
    assert ops[0]["target_file"] == POLYGON_IMPORTS_REL
    assert ops[0]["team_decision"] == "pending"
    assert ops[0].get("approval_state") == "pending"


def test_propose_op_shape(tmp_path: Path) -> None:
    op = build_polygon_propose_operation(tmp_path)
    assert op["kind"] == "remove_unused_import"
    assert op["target_file"] == POLYGON_IMPORTS_REL
    assert op["team_decision"] == "pending"
    assert op["approval_state"] == "pending"
    assert op["decision_source"] == "prove_cycle_propose"


def test_propose_approve_then_clean_polygon(tmp_path: Path) -> None:
    run_prove_cycle(tmp_path, propose=True, quiet=True)
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["operations"][0]["team_decision"] = "approve"
    data["operations"][0]["approved_by"] = "tester"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    approved, _ = load_approved_operations(tmp_path)
    assert len(approved) == 1
    target = tmp_path / POLYGON_IMPORTS_REL
    before = target.read_text(encoding="utf-8")
    assert "import os" in before
    result = remove_unused_imports(target)
    assert isinstance(result, str)
    target.write_text(result, encoding="utf-8")
    after = target.read_text(encoding="utf-8")
    assert "import os" not in after
    assert "from pathlib import Path" in after
    assert "polygon_imports_ok" in after


def test_default_prove_cycle_still_sandboxed(tmp_path: Path) -> None:
    run_prove_cycle(tmp_path, quiet=True, verify_timeout=60)
    assert (tmp_path / DRILL_REL_PATH).is_file()
    assert not (tmp_path / "eurika" / "orchestration").exists()
    assert not (tmp_path / POLYGON_IMPORTS_REL).exists()


def test_normalize_propose_drill_aliases() -> None:
    assert normalize_propose_drill("imports") == "imports"
    assert normalize_propose_drill("extract") == "extractable_block"
    assert normalize_propose_drill("second") == "extractable_block"


def test_propose_extractable_writes_pending_and_seeds(tmp_path: Path) -> None:
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="extractable_block"
    )
    assert out.get("ok") is True
    assert out.get("drill_id") == "extractable_block"
    assert out.get("target_file") == POLYGON_EXTRACTABLE_REL
    target = tmp_path / POLYGON_EXTRACTABLE_REL
    text = target.read_text(encoding="utf-8")
    assert "polygon_extractable_block" in text
    assert "_extracted_block_" not in text
    assert "a = x + 1" in text
    pending = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(pending.read_text(encoding="utf-8"))
    op = data["operations"][0]
    assert op["kind"] == "extract_block_to_helper"
    assert op["target_file"] == POLYGON_EXTRACTABLE_REL
    assert op["team_decision"] == "pending"
    params = op.get("params") or {}
    assert params.get("location") == "polygon_extractable_block"
    assert params.get("helper_name")
    assert params.get("block_start_line")


def test_propose_extractable_approve_then_apply(tmp_path: Path) -> None:
    run_prove_cycle(tmp_path, propose=True, quiet=True, drill="extractable_block")
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["operations"][0]["team_decision"] = "approve"
    data["operations"][0]["approved_by"] = "tester"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    approved, _ = load_approved_operations(tmp_path)
    assert len(approved) == 1
    report = apply_patch_plan(
        tmp_path, {"operations": approved}, dry_run=False, backup=False
    )
    assert POLYGON_EXTRACTABLE_REL in (report.get("modified") or [])
    after = (tmp_path / POLYGON_EXTRACTABLE_REL).read_text(encoding="utf-8")
    assert "def _extracted_block_" in after
    assert "a = x + 1" not in after or "_extracted_block_" in after
