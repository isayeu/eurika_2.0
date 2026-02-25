"""Tests for Tool Contract Layer (ROADMAP 2.7.2)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.agent.models import ToolResult
from eurika.agent import DefaultToolContract


def test_patch_dry_run_reproducible(tmp_path: Path) -> None:
    """Dry-run returns same report without modifying files; reproducible."""
    (tmp_path / "foo.py").write_text("x = 1\n")
    plan = {"operations": [{"target_file": "foo.py", "kind": "refactor_code_smell", "diff": "# TODO: refactor\n", "params": {}}]}
    contract = DefaultToolContract()
    r1 = contract.patch(tmp_path, plan, dry_run=True, backup=False)
    r2 = contract.patch(tmp_path, plan, dry_run=True, backup=False)
    assert r1.status == "ok"
    assert r2.status == "ok"
    assert r1.payload["dry_run"] is True
    assert r2.payload["dry_run"] is True
    assert r1.payload.get("modified") == r2.payload.get("modified")
    assert (tmp_path / "foo.py").read_text() == "x = 1\n"


def test_patch_dry_run_empty_plan(tmp_path: Path) -> None:
    """Empty plan returns ok with no modifications."""
    contract = DefaultToolContract()
    r = contract.patch(tmp_path, {"operations": []}, dry_run=True)
    assert r.status == "ok"
    assert r.payload["modified"] == []
    assert r.payload["dry_run"] is True


def test_verify_returns_tool_result(tmp_path: Path) -> None:
    """Verify returns ToolResult with success, returncode, stdout, stderr."""
    (tmp_path / "test_nothing.py").write_text("def test_ok(): pass\n")
    contract = DefaultToolContract()
    r = contract.verify(tmp_path, timeout=10)
    assert r.status == "ok"
    assert "success" in r.payload
    assert "returncode" in r.payload


def test_rollback_no_backup_returns_ok(tmp_path: Path) -> None:
    """Rollback when no backup returns ok with restored=[]."""
    contract = DefaultToolContract()
    r = contract.rollback(tmp_path, run_id=None)
    assert r.status == "ok"
    assert "restored" in r.payload or "run_id" in r.payload


def test_tests_alias_for_verify(tmp_path: Path) -> None:
    """Tests is alias for verify."""
    (tmp_path / "t.py").write_text("def test_x(): pass\n")
    contract = DefaultToolContract()
    r = contract.tests(tmp_path, timeout=10)
    assert r.status == "ok"
    assert "success" in r.payload


def test_git_read_not_repo(tmp_path: Path) -> None:
    """git_read on non-repo returns commit=None."""
    contract = DefaultToolContract()
    r = contract.git_read(tmp_path)
    assert r.status == "ok"
    assert r.payload.get("commit") is None


def test_patch_missing_target_file_error_normalized(tmp_path: Path) -> None:
    """Operations with missing target_file yield ToolResult with status=error or errors in payload."""
    contract = DefaultToolContract()
    r = contract.patch(tmp_path, {"operations": [{"target_file": "", "diff": ""}]}, dry_run=True)
    assert isinstance(r, ToolResult)
    if r.status == "error":
        assert r.message
    else:
        assert r.payload.get("errors")
