"""Tests for eurika.learning.git_refactors (Phase 5 OSS before/after)."""

from pathlib import Path


def test_extract_before_after_empty_dir(tmp_path: Path) -> None:
    """Empty cache_dir returns empty before_after."""
    from eurika.learning.git_refactors import extract_before_after_from_repos

    result = extract_before_after_from_repos(tmp_path)
    assert "long_function_before_after" in result
    assert "deep_nesting_before_after" in result
    assert result["long_function_before_after"] == []
    assert result["deep_nesting_before_after"] == []


def test_extract_before_after_nongit_dir(tmp_path: Path) -> None:
    """Non-git subdir yields no entries."""
    from eurika.learning.git_refactors import extract_before_after_from_repos

    (tmp_path / "norepo").mkdir()
    (tmp_path / "norepo" / "foo.py").write_text("x = 1\n")
    result = extract_before_after_from_repos(tmp_path)
    assert result["long_function_before_after"] == []
    assert result["deep_nesting_before_after"] == []


def test_pattern_library_includes_before_after(tmp_path: Path) -> None:
    """extract_patterns_from_repos includes before_after keys when present."""
    from eurika.learning.pattern_library import extract_patterns_from_repos

    result = extract_patterns_from_repos(tmp_path)
    assert "long_function_before_after" in result
    assert "deep_nesting_before_after" in result
    assert isinstance(result["long_function_before_after"], list)
    assert isinstance(result["deep_nesting_before_after"], list)


def test_load_oss_before_after_empty(tmp_path: Path) -> None:
    """_load_oss_before_after_for_smell returns [] when no library."""
    from eurika.api.ops import _load_oss_before_after_for_smell

    assert _load_oss_before_after_for_smell(tmp_path, "long_function") == []


def test_load_oss_before_after_with_data(tmp_path: Path) -> None:
    """_load_oss_before_after_for_smell loads formatted pairs from pattern_library."""
    from eurika.api.ops import _load_oss_before_after_for_smell

    (tmp_path / ".eurika").mkdir(parents=True, exist_ok=True)
    lib = tmp_path / ".eurika" / "pattern_library.json"
    lib.write_text(
        """{
  "long_function_before_after": [
    {"project": "test", "module": "foo.py", "before": "def old():\\n    pass", "after": "def old():\\n    x = helper()\\n    return x\\n\\ndef helper():\\n    pass"}
  ]
}""",
        encoding="utf-8",
    )
    result = _load_oss_before_after_for_smell(tmp_path, "long_function", max_count=2)
    assert len(result) == 1
    assert "Before:" in result[0]
    assert "After:" in result[0]
    assert "test:foo.py" in result[0]
