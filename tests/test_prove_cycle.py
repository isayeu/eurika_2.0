"""Tests for eurika prove-cycle (deterministic patch→verify→learning)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.orchestration.prove_cycle import (
    DRILL_REL_PATH,
    POLYGON_EXTRACTABLE_REL,
    POLYGON_IMPORTS_REL,
    POLYGON_LLM_EXTRACT_REL,
    POLYGON_LONG_FUNCTION_REL,
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
    assert normalize_propose_drill("long") == "long_function"
    assert normalize_propose_drill("third") == "long_function"
    assert normalize_propose_drill("llm") == "llm_extract"
    assert normalize_propose_drill("fourth") == "llm_extract"
    assert normalize_propose_drill("deep") == "deep_nesting"
    assert normalize_propose_drill("fifth") == "deep_nesting"


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


def test_propose_long_function_writes_pending_and_seeds(tmp_path: Path) -> None:
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="long_function"
    )
    assert out.get("ok") is True
    assert out.get("drill_id") == "long_function"
    assert out.get("target_file") == POLYGON_LONG_FUNCTION_REL
    assert out.get("seeded_nested") is True
    target = tmp_path / POLYGON_LONG_FUNCTION_REL
    text = target.read_text(encoding="utf-8")
    assert "def polygon_long_function" in text
    assert "def _compute_first_half" in text
    assert text.find("def polygon_long_function") < text.find("def _compute_first_half")
    pending = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(pending.read_text(encoding="utf-8"))
    op = data["operations"][0]
    assert op["kind"] == "extract_nested_function"
    assert op["target_file"] == POLYGON_LONG_FUNCTION_REL
    assert op["team_decision"] == "pending"
    params = op.get("params") or {}
    assert params.get("location") == "polygon_long_function"
    assert params.get("nested_function_name") == "_compute_first_half"


def test_propose_long_function_approve_then_apply(tmp_path: Path) -> None:
    run_prove_cycle(tmp_path, propose=True, quiet=True, drill="long_function")
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
    assert POLYGON_LONG_FUNCTION_REL in (report.get("modified") or [])
    after = (tmp_path / POLYGON_LONG_FUNCTION_REL).read_text(encoding="utf-8")
    assert after.find("def _compute_first_half") < after.find("def polygon_long_function")
    ns: dict = {}
    exec(compile(after, str(tmp_path / POLYGON_LONG_FUNCTION_REL), "exec"), ns)
    assert ns["polygon_long_function"]() == 55


def test_propose_llm_extract_offline_synthetic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EURIKA_USE_LLM_EXTRACT", raising=False)
    out = run_prove_cycle(tmp_path, propose=True, quiet=True, drill="llm_extract")
    assert out.get("ok") is True
    assert out.get("drill_id") == "llm_extract"
    assert out.get("target_file") == POLYGON_LLM_EXTRACT_REL
    assert out.get("llm_extract_source") == "synthetic_offline"
    pending = json.loads((tmp_path / ".eurika" / "pending_plan.json").read_text(encoding="utf-8"))
    op = pending["operations"][0]
    assert op["kind"] == "llm_extract_block"
    params = op.get("params") or {}
    assert params.get("location") == "polygon_refactor_code_smell_drill"
    assert "_sum_intermediates" in str(params.get("new_content") or "")
    assert "_sum_intermediates" not in (tmp_path / POLYGON_LLM_EXTRACT_REL).read_text(
        encoding="utf-8"
    )


def test_propose_llm_extract_require_llm_fails_without_patch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("EURIKA_USE_LLM_EXTRACT", raising=False)

    def _no_patch(*_a, **_k):
        return None

    monkeypatch.setattr(
        "eurika.reasoning.planner.llm_adapter.ask_llm_extract_patch",
        _no_patch,
    )
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="llm_extract", require_llm=True
    )
    assert out.get("ok") is False
    assert "require-llm" in str(out.get("error") or "").lower()
    assert not (tmp_path / ".eurika" / "pending_plan.json").is_file()


def test_propose_llm_extract_require_llm_parks_live_patch(
    tmp_path: Path, monkeypatch
) -> None:
    from eurika.orchestration.prove_cycle import _POLYGON_LLM_EXTRACT_SYNTHETIC

    monkeypatch.delenv("EURIKA_USE_LLM_EXTRACT", raising=False)

    def _fake_patch(*_a, **_k):
        return _POLYGON_LLM_EXTRACT_SYNTHETIC

    monkeypatch.setattr(
        "eurika.reasoning.planner.llm_adapter.ask_llm_extract_patch",
        _fake_patch,
    )
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="llm_extract", require_llm=True
    )
    assert out.get("ok") is True
    assert out.get("llm_extract_source") == "llm"
    assert out.get("require_llm") is True
    pending = json.loads((tmp_path / ".eurika" / "pending_plan.json").read_text(encoding="utf-8"))
    assert (pending["operations"][0].get("params") or {}).get("source") == "llm"


def test_require_llm_rejected_for_non_llm_drill(tmp_path: Path) -> None:
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="imports", require_llm=True
    )
    assert out.get("ok") is False
    assert "llm_extract" in str(out.get("error") or "")


def test_propose_llm_extract_approve_then_apply(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EURIKA_USE_LLM_EXTRACT", raising=False)
    run_prove_cycle(tmp_path, propose=True, quiet=True, drill="llm_extract")
    path = tmp_path / ".eurika" / "pending_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["operations"][0]["team_decision"] = "approve"
    data["operations"][0]["approved_by"] = "tester"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    approved, _ = load_approved_operations(tmp_path)
    report = apply_patch_plan(
        tmp_path, {"operations": approved}, dry_run=False, backup=False
    )
    assert POLYGON_LLM_EXTRACT_REL in (report.get("modified") or [])
    after = (tmp_path / POLYGON_LLM_EXTRACT_REL).read_text(encoding="utf-8")
    assert "def _sum_intermediates" in after
    ns: dict = {}
    exec(compile(after, str(tmp_path / POLYGON_LLM_EXTRACT_REL), "exec"), ns)
    assert ns["polygon_refactor_code_smell_drill"](5) == ns["polygon_refactor_code_smell_drill"](5)
    # seed semantics: intermediates + 1
    before_ns: dict = {}
    from eurika.orchestration.prove_cycle import _POLYGON_LLM_EXTRACT_SEED

    exec(compile(_POLYGON_LLM_EXTRACT_SEED, "seed", "exec"), before_ns)
    assert (
        ns["polygon_refactor_code_smell_drill"](5)
        == before_ns["polygon_refactor_code_smell_drill"](5)
    )


def test_propose_sandbox_imports_verifies_then_parks(tmp_path: Path) -> None:
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="imports", sandbox=True
    )
    assert out.get("ok") is True
    assert out.get("sandbox") is True
    assert out.get("sandbox_mode") == "copy"
    assert out.get("verify_success") is True
    assert (out.get("sandbox_verify") or {}).get("ok") is True
    assert (tmp_path / ".eurika" / "pending_plan.json").is_file()
    seeded = (tmp_path / POLYGON_IMPORTS_REL).read_text(encoding="utf-8")
    assert "import os" in seeded  # main still seeded for HITL apply
    # Default: sandbox dir cleaned up
    sandbox_root = tmp_path / ".eurika" / "sandbox"
    if sandbox_root.is_dir():
        assert list(sandbox_root.iterdir()) == []


def test_propose_sandbox_keep_leaves_dir(tmp_path: Path) -> None:
    out = run_prove_cycle(
        tmp_path,
        propose=True,
        quiet=True,
        drill="extractable_block",
        sandbox=True,
        keep_sandbox=True,
    )
    assert out.get("ok") is True
    assert out.get("sandbox_kept") is True
    sb = Path(str(out.get("sandbox_path")))
    assert sb.is_dir()
    # Applied inside sandbox — helper present there
    applied = (sb / POLYGON_EXTRACTABLE_REL).read_text(encoding="utf-8")
    assert "def _extracted_block_" in applied
    # Main still only seeded (not applied)
    main = (tmp_path / POLYGON_EXTRACTABLE_REL).read_text(encoding="utf-8")
    assert "_extracted_block_" not in main


def test_propose_sandbox_llm_extract_offline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EURIKA_USE_LLM_EXTRACT", raising=False)
    out = run_prove_cycle(
        tmp_path, propose=True, quiet=True, drill="llm_extract", sandbox=True
    )
    assert out.get("ok") is True
    assert out.get("llm_extract_source") == "synthetic_offline"
    assert out.get("verify_success") is True

