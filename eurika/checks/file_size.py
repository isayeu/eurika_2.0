"""File size limits check (ROADMAP 3.1-arch.3).

Rule: >400 LOC = candidate for splitting; >600 LOC = must split.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

CANDIDATE_LIMIT = 400  # lines
MUST_SPLIT_LIMIT = 600  # lines

SKIP_DIRS = frozenset({"__pycache__", ".git", ".venv", "venv", ".eurika_backups", "node_modules"})
SKIP_CONTAINING = (".eurika_backups", "_shelved")


def check_file_size_limits(
    root: Path,
    *,
    include_tests: bool = True,
) -> Tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """
    Scan Python files for LOC limit violations.

    Returns:
        (candidates, must_split) where each item is (relative_path, line_count).
        candidates: files with 400 < LOC <= 600
        must_split: files with LOC > 600
    """
    root = Path(root).resolve()
    candidates: list[tuple[str, int]] = []
    must_split: list[tuple[str, int]] = []

    for py_path in root.rglob("*.py"):
        if any(s in py_path.parts for s in SKIP_DIRS):
            continue
        if any(s in str(py_path) for s in SKIP_CONTAINING):
            continue
        if not include_tests and "tests" in py_path.parts:
            continue
        try:
            content = py_path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = py_path.relative_to(root).as_posix()
        total = len(content.splitlines())
        if total > MUST_SPLIT_LIMIT:
            must_split.append((rel, total))
        elif total > CANDIDATE_LIMIT:
            candidates.append((rel, total))

    candidates.sort(key=lambda x: -x[1])
    must_split.sort(key=lambda x: -x[1])
    return candidates, must_split


def format_file_size_report(
    root: Path,
    *,
    include_tests: bool = True,
) -> str:
    """Produce human-readable report of file size violations."""
    candidates, must_split = check_file_size_limits(root, include_tests=include_tests)
    if not candidates and not must_split:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("FILE SIZE LIMITS (ROADMAP 3.1-arch.3)")
    lines.append("  Rule: >400 LOC = candidate; >600 LOC = must split")
    lines.append("")
    if must_split:
        lines.append("Must split (>600 LOC):")
        for rel, count in must_split[:15]:
            lines.append(f"  - {rel} ({count})")
        if len(must_split) > 15:
            lines.append(f"  ... and {len(must_split) - 15} more")
        lines.append("")
    if candidates:
        lines.append("Candidates (>400 LOC):")
        for rel, count in candidates[:10]:
            lines.append(f"  - {rel} ({count})")
        if len(candidates) > 10:
            lines.append(f"  ... and {len(candidates) - 10} more")
    return "\n".join(lines)


if __name__ == "__main__":
    """Run: python -m eurika.checks.file_size [path]"""
    import sys

    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    report = format_file_size_report(path)
    print(report if report else "No file size violations.")
