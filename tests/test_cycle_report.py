"""Tests for report-snapshot, telemetry, whitelist-draft (extracted from test_cycle.py)."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_handle_report_snapshot_delegates_to_format(capsys: Any, tmp_path: Path) -> None:
    """report-snapshot handler delegates to format_report_snapshot (3.1-arch.5 isolation)."""
    args = SimpleNamespace(path=tmp_path)
    with patch("report.report_snapshot.format_report_snapshot", return_value="DELEGATED_OUTPUT") as mock_fmt:
        from cli.core_handlers import handle_report_snapshot

        code = handle_report_snapshot(args)
    assert code == 0
    assert mock_fmt.called
    assert mock_fmt.call_args[0][0] == tmp_path
    out, _ = capsys.readouterr()
    assert "DELEGATED_OUTPUT" in out


def test_report_snapshot_empty_project(tmp_path: Path) -> None:
    """report-snapshot outputs fallback when no artifacts exist."""
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "No eurika_doctor_report" in result.stdout or "eurika_fix_report" in result.stdout


def test_report_snapshot_with_fix_report(tmp_path: Path) -> None:
    """report-snapshot reads eurika_fix_report.json when present."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"modified": ["a.py"], "skipped": [], "verify": {"success": True}}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "## 1. Fix" in result.stdout
    assert "modified" in result.stdout
    assert "1" in result.stdout


def test_report_snapshot_invalid_fix_report_shows_warning(tmp_path: Path) -> None:
    """report-snapshot should not crash on invalid eurika_fix_report.json and should warn."""
    (tmp_path / "eurika_fix_report.json").write_text("{broken json", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "No eurika_doctor_report" in result.stdout or "Run doctor/fix first" in result.stdout


def test_report_snapshot_invalid_doctor_report_still_shows_fix_and_warning(tmp_path: Path) -> None:
    """report-snapshot should keep valid fix section when doctor report is invalid."""
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps({"modified": ["a.py"], "skipped": [], "verify": {"success": True}}),
        encoding="utf-8",
    )
    (tmp_path / "eurika_doctor_report.json").write_text("{oops", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "## 1. Fix" in result.stdout
    assert "Snapshot warnings" in result.stdout
    assert "invalid JSON in eurika_doctor_report.json" in result.stdout


def test_attach_fix_telemetry_median_verify_time(tmp_path: Path) -> None:
    """attach_fix_telemetry adds median_verify_time_ms when path has patch events (ROADMAP 2.7.8)."""
    from eurika.storage import ProjectMemory
    from cli.orchestration.apply_stage import attach_fix_telemetry

    memory = ProjectMemory(tmp_path)
    memory.events.append_event(
        "patch",
        {"operations_count": 1},
        {"modified": ["a.py"], "verify_success": True, "verify_duration_ms": 100},
        result=True,
    )
    memory.events.append_event(
        "patch",
        {"operations_count": 1},
        {"modified": ["b.py"], "verify_success": True, "verify_duration_ms": 200},
        result=True,
    )
    report = {
        "modified": ["c.py"],
        "skipped": [],
        "verify": {"success": True},
        "verify_duration_ms": 300,
    }
    attach_fix_telemetry(report, [{"target_file": "c.py"}], tmp_path)
    assert "median_verify_time_ms" in report.get("telemetry", {})
    assert report["telemetry"]["median_verify_time_ms"] == 200


def test_attach_fix_telemetry_counts_campaign_session_skips() -> None:
    """Telemetry no-op metrics include campaign/session-filtered operations."""
    from cli.orchestration.apply_stage import attach_fix_telemetry

    report = {
        "message": "Patch plan has no operations. Cycle complete.",
        "policy_decisions": [
            {"index": 1, "target_file": "eurika/agent/tool_contract.py", "kind": "split_module"}
        ],
        "campaign_skipped": 1,
        "session_skipped": 0,
    }
    attach_fix_telemetry(report, [])
    telemetry = report.get("telemetry", {})
    assert telemetry.get("operations_total") == 1
    assert telemetry.get("skipped_count") == 1
    assert telemetry.get("no_op_rate") == 1.0
    assert telemetry.get("apply_rate") == 0.0


def test_report_snapshot_telemetry_block(tmp_path: Path) -> None:
    """report-snapshot includes telemetry subsection when fix has telemetry (ROADMAP 2.7.8)."""
    fix_report = {
        "modified": ["a.py"],
        "skipped": [],
        "verify": {"success": True},
        "telemetry": {"apply_rate": 1.0, "no_op_rate": 0.0, "rollback_rate": 0.0, "verify_duration_ms": 150},
    }
    (tmp_path / "eurika_fix_report.json").write_text(json.dumps(fix_report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "telemetry" in result.stdout
    assert "1.0" in result.stdout or "apply_rate" in result.stdout


def test_report_snapshot_context_effect_block(tmp_path: Path) -> None:
    """report-snapshot includes context effect section with no-op/apply deltas."""
    fix_report = {
        "modified": ["a.py"],
        "skipped": [],
        "verify": {"success": True},
        "telemetry": {"apply_rate": 1.0, "no_op_rate": 0.0, "rollback_rate": 0.0, "verify_duration_ms": 120},
        "context_sources": {
            "recent_verify_fail_targets": ["a.py", "b.py"],
            "campaign_rejected_targets": ["c.py"],
            "recent_patch_modified": ["a.py"],
            "by_target": {"a.py": {"related_tests": ["tests/test_a.py"], "neighbor_modules": ["b.py"]}},
        },
    }
    doctor_report = {
        "summary": {"system": {"modules": 2, "dependencies": 1}},
        "history": {"points": [{"risk_score": 40}]},
        "operational_metrics": {"runs_count": 10, "apply_rate": 0.5, "rollback_rate": 0.1},
    }
    (tmp_path / "eurika_fix_report.json").write_text(json.dumps(fix_report), encoding="utf-8")
    (tmp_path / "eurika_doctor_report.json").write_text(json.dumps(doctor_report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "report-snapshot", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "## 2.1 Context effect (ROADMAP 3.6.3)" in result.stdout
    assert "apply_rate: current=1.0, baseline=0.5" in result.stdout
    assert "no_op_rate: current=0.0" in result.stdout


def test_whitelist_draft_generates_candidates_file(tmp_path: Path) -> None:
    """whitelist-draft emits draft file from campaign verify_success candidates."""
    from eurika.storage import SessionMemory

    mem = SessionMemory(tmp_path)
    op = {"target_file": "eurika/api/chat.py", "kind": "extract_block_to_helper", "params": {"location": "_ctx"}}
    mem.record_verify_success([op])
    mem.record_verify_success([op])

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "whitelist-draft", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    draft_path = tmp_path / ".eurika" / "operation_whitelist.draft.json"
    assert draft_path.exists()
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    ops = payload.get("operations") or []
    assert len(ops) >= 1
    assert ops[0].get("kind") == "extract_block_to_helper"
    assert ops[0].get("target_file") == "eurika/api/chat.py"
    assert ops[0].get("location") == "_ctx"
    assert ops[0].get("allow_in_auto") is False


def test_whitelist_draft_filters_kinds_by_default(tmp_path: Path) -> None:
    """whitelist-draft keeps only default safe kind unless --all-kinds."""
    from eurika.storage import SessionMemory

    mem = SessionMemory(tmp_path)
    op_extract = {"target_file": "a.py", "kind": "extract_block_to_helper", "params": {"location": "f"}}
    op_split = {"target_file": "b.py", "kind": "split_module", "params": {"location": "g"}}
    mem.record_verify_success([op_extract, op_split])
    mem.record_verify_success([op_extract, op_split])

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "whitelist-draft", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    payload = json.loads((tmp_path / ".eurika" / "operation_whitelist.draft.json").read_text(encoding="utf-8"))
    kinds = {op.get("kind") for op in (payload.get("operations") or [])}
    assert "extract_block_to_helper" in kinds
    assert "split_module" not in kinds


def test_whitelist_draft_all_kinds_includes_other_kinds(tmp_path: Path) -> None:
    """--all-kinds disables default kind filter."""
    from eurika.storage import SessionMemory

    mem = SessionMemory(tmp_path)
    op_extract = {"target_file": "a.py", "kind": "extract_block_to_helper", "params": {"location": "f"}}
    op_split = {"target_file": "b.py", "kind": "split_module", "params": {"location": "g"}}
    mem.record_verify_success([op_extract, op_split])
    mem.record_verify_success([op_extract, op_split])

    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "whitelist-draft", "--all-kinds", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    payload = json.loads((tmp_path / ".eurika" / "operation_whitelist.draft.json").read_text(encoding="utf-8"))
    kinds = {op.get("kind") for op in (payload.get("operations") or [])}
    assert "extract_block_to_helper" in kinds
    assert "split_module" in kinds


def test_whitelist_draft_rejects_unknown_kind(tmp_path: Path) -> None:
    """Unknown --kinds should fail fast with a clear CLI error."""
    result = subprocess.run(
        [sys.executable, "-m", "eurika_cli", "whitelist-draft", "--kinds", "unknown_kind", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "unknown --kinds values" in result.stderr
