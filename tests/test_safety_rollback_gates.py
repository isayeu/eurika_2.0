"""Tests for Safety & Rollback Gates (ROADMAP 2.7.7)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from patch_engine import apply_and_verify


def test_verify_fail_triggers_rollback_files_restored(tmp_path: Path) -> None:
    """When verify fails and auto_rollback=True, modified files are restored to original."""
    original = "x = 1\n"
    (tmp_path / "target.py").write_text(original, encoding="utf-8")
    (tmp_path / "test_target.py").write_text(
        'def test_import(): __import__("target")\n', encoding="utf-8"
    )
    plan = {
        "operations": [
            {
                "target_file": "target.py",
                "diff": '\nraise RuntimeError("verify fail")\n',
                "kind": "refactor_module",
            }
        ]
    }
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True, auto_rollback=True)
    assert report["verify"]["success"] is False
    assert report.get("rollback", {}).get("done") is True
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == original


def test_apply_with_verify_produces_verify_gate(tmp_path: Path) -> None:
    """apply_and_verify with verify=True runs verify and report has verify gate."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "test_a.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    plan = {"operations": [{"target_file": "a.py", "diff": "\n# eurika\n", "kind": "refactor_module"}]}
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True, auto_rollback=True)
    assert report["verify"]["success"] is True
    assert report.get("verify_duration_ms") is not None
    assert report.get("run_id")


def test_no_partially_applied_on_verify_fail(tmp_path: Path) -> None:
    """No leftover modified files when verify fails and rollback runs."""
    (tmp_path / "f.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "test_f.py").write_text("def test_x(): assert False\n", encoding="utf-8")
    before = (tmp_path / "f.py").read_text(encoding="utf-8")
    plan = {
        "operations": [
            {"target_file": "f.py", "diff": "\n# change\n", "kind": "refactor_module"},
        ]
    }
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True, auto_rollback=True)
    assert report["verify"]["success"] is False
    assert report.get("rollback", {}).get("done") is True
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == before
