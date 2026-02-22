"""Tests for Explainability Record (ROADMAP 2.7.4)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_operation_explanations_include_verify_outcome(tmp_path: Path) -> None:
    """After apply, operation_explanations have verify_outcome from verify result."""
    from cli.orchestration.apply_stage import execute_fix_apply_stage

    ops = [
        {"target_file": "foo.py", "kind": "remove_unused_import", "explainability": {"why": "cleanup", "risk": "low"}},
    ]
    patch_plan = {"operations": ops}
    fake_apply = lambda *a, **k: {
        "modified": [],
        "verify": {"success": True},
        "run_id": "x",
    }
    report, _, _ = execute_fix_apply_stage(
        tmp_path, patch_plan, ops,
        session_id=None,
        quiet=True, verify_cmd=None, verify_timeout=None, backup_dir=".eurika_backups",
        apply_and_verify=fake_apply,
        run_scan=lambda *a: 0,
        build_snapshot_from_self_map=lambda *a: {},
        diff_architecture_snapshots=lambda *a: {},
        metrics_from_graph=lambda *a: {},
        rollback_patch=lambda *a: {},
        result=type("R", (), {"output": {"policy_decisions": [{"target_file": "foo.py", "decision": "allow"}]}})(),
    )
    expls = report.get("operation_explanations") or []
    assert len(expls) == 1
    assert expls[0].get("verify_outcome") is True
    assert "why" in expls[0]
    assert "risk" in expls[0]


def test_dry_run_report_includes_operation_explanations_with_verify_outcome_none(tmp_path: Path) -> None:
    """Dry-run eurika_fix_report.json has operation_explanations with verify_outcome=None."""
    from unittest.mock import MagicMock, patch

    from cli.orchestrator import run_cycle

    with patch("cli.orchestrator._fix_cycle_deps") as mock_deps:
        mock_deps.return_value = {"run_scan": lambda *a: 0}
        with patch("cli.orchestrator._prepare_fix_cycle_operations") as mock_prep:
            result = MagicMock()
            result.output = {"policy_decisions": [{"target_file": "x.py", "decision": "allow"}]}
            ops = [{"target_file": "x.py", "kind": "split_module", "explainability": {"why": "split", "risk": "high"}}]
            mock_prep.return_value = (None, result, {"operations": ops}, ops)
            run_cycle(tmp_path, mode="fix", dry_run=True, quiet=True)

    report_path = tmp_path / "eurika_fix_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    expls = data.get("operation_explanations") or []
    assert len(expls) >= 1
    assert expls[0].get("verify_outcome") is None
    assert expls[0].get("why")
    assert expls[0].get("risk")
