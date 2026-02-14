"""Tests for patch_engine (apply_and_verify, rollback, list_backups)."""

from pathlib import Path

import pytest

from patch_engine import apply_and_verify, list_backups, rollback


def test_apply_and_verify_modifies_files(tmp_path: Path) -> None:
    """apply_and_verify applies plan and runs verify step."""
    (tmp_path / "foo.py").write_text("x = 1\n", encoding="utf-8")
    plan = {
        "operations": [
            {
                "target_file": "foo.py",
                "diff": "# TODO: refactor (eurika)\n",
                "smell_type": "god_module",
                "kind": "refactor_module",
            }
        ]
    }
    report = apply_and_verify(tmp_path, plan, backup=True, verify=True)
    assert report["modified"] == ["foo.py"]
    assert report["errors"] == []
    assert "verify" in report
    assert "success" in report["verify"]
    assert (tmp_path / "foo.py").read_text(encoding="utf-8") == "x = 1\n\n# TODO: refactor (eurika)\n"
    # Backup was created
    assert report.get("run_id")
    assert (tmp_path / ".eurika_backups" / report["run_id"] / "foo.py").exists()


def test_apply_and_verify_no_verify(tmp_path: Path) -> None:
    """With verify=False, no pytest run; report has verify placeholder."""
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    plan = {"operations": [{"target_file": "a.py", "diff": "# eurika\n", "smell_type": "hub", "kind": "split"}]}
    report = apply_and_verify(tmp_path, plan, backup=False, verify=False)
    assert report["modified"] == ["a.py"]
    assert report["verify"]["success"] is None


def test_rollback_restores_files(tmp_path: Path) -> None:
    """rollback restores from .eurika_backups/<run_id>."""
    backup_dir = tmp_path / ".eurika_backups" / "20250101_120000"
    backup_dir.mkdir(parents=True)
    (backup_dir / "bar.py").write_text("original\n", encoding="utf-8")
    (tmp_path / "bar.py").write_text("modified\n", encoding="utf-8")

    result = rollback(tmp_path, run_id="20250101_120000")
    assert result["errors"] == []
    assert "bar.py" in result["restored"]
    assert (tmp_path / "bar.py").read_text(encoding="utf-8") == "original\n"


def test_rollback_latest_when_no_run_id(tmp_path: Path) -> None:
    """rollback with run_id=None uses latest backup dir."""
    (tmp_path / ".eurika_backups" / "run1").mkdir(parents=True)
    (tmp_path / ".eurika_backups" / "run1" / "f.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "f.py").write_text("y\n", encoding="utf-8")

    result = rollback(tmp_path, run_id=None)
    assert result["errors"] == []
    assert result["run_id"] == "run1"
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "x\n"


def test_list_backups_empty(tmp_path: Path) -> None:
    """list_backups returns empty list when no backups."""
    info = list_backups(tmp_path)
    assert info["run_ids"] == []
    assert ".eurika_backups" in info["backup_dir"]


def test_list_backups_finds_runs(tmp_path: Path) -> None:
    """list_backups returns sorted run_ids."""
    (tmp_path / ".eurika_backups" / "20250102_000000").mkdir(parents=True)
    (tmp_path / ".eurika_backups" / "20250101_000000").mkdir(parents=True)
    info = list_backups(tmp_path)
    assert len(info["run_ids"]) == 2
    assert "20250101_000000" in info["run_ids"]
    assert "20250102_000000" in info["run_ids"]
