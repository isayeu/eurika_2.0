"""Tests for eurika.checks.file_size (ROADMAP 3.1-arch.3)."""

from pathlib import Path

import pytest

from eurika.checks import check_file_size_limits
from eurika.checks.file_size import format_file_size_report


def test_check_file_size_limits_empty(tmp_path: Path) -> None:
    """Empty project has no violations."""
    candidates, must_split = check_file_size_limits(tmp_path)
    assert candidates == []
    assert must_split == []


def test_check_file_size_limits_small_file(tmp_path: Path) -> None:
    """Small file is not reported."""
    (tmp_path / "small.py").write_text("\n".join(["x = 1"] * 50), encoding="utf-8")
    candidates, must_split = check_file_size_limits(tmp_path)
    assert candidates == []
    assert must_split == []


def test_check_file_size_limits_candidate(tmp_path: Path) -> None:
    """File with 401 lines is a candidate."""
    (tmp_path / "mid.py").write_text("\n".join(["pass"] * 401), encoding="utf-8")
    candidates, must_split = check_file_size_limits(tmp_path)
    assert ("mid.py", 401) in candidates
    assert must_split == []


def test_check_file_size_limits_must_split(tmp_path: Path) -> None:
    """File with 601 lines must split."""
    (tmp_path / "big.py").write_text("\n".join(["pass"] * 601), encoding="utf-8")
    candidates, must_split = check_file_size_limits(tmp_path)
    assert ("big.py", 601) in must_split
    assert ("big.py", 601) not in candidates


def test_format_report_empty(tmp_path: Path) -> None:
    """Empty report for no violations."""
    assert format_file_size_report(tmp_path) == ""


def test_format_report_non_empty(tmp_path: Path) -> None:
    """Report includes must_split and candidates."""
    (tmp_path / "big.py").write_text("\n" * 601, encoding="utf-8")
    (tmp_path / "mid.py").write_text("\n" * 450, encoding="utf-8")
    report = format_file_size_report(tmp_path)
    assert "FILE SIZE LIMITS" in report
    assert ">400" in report
    assert ">600" in report
    assert "big.py" in report
    assert "mid.py" in report


def test_skip_pycache(tmp_path: Path) -> None:
    """__pycache__ is skipped."""
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "huge.py").write_text("\n" * 700, encoding="utf-8")
    candidates, must_split = check_file_size_limits(tmp_path)
    assert must_split == []
