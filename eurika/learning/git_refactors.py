"""Extract before/after refactor pairs from OSS git history (REFACTOR_CODE_SMELL_PLAN Phase 5).

For curated repos, scans git log for refactor-like commits and extracts
file-level before/after content for LLM few-shot context.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# Commits matching any of these terms (extended regex, case-insensitive)
REFACTOR_GREP = "refactor|extract|simplify"


def _git_available(repo_path: Path) -> bool:
    try:
        subprocess.run(
            ["git", "status"],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _git_refactor_commits(repo_path: Path, limit: int = 30) -> List[Dict[str, str]]:
    """List commits that look like refactors. Returns [{sha, subject, files_str}...]."""
    try:
        out = subprocess.run(
            [
                "git", "log",
                "-E",
                f"--grep={REFACTOR_GREP}",
                "-i",
                f"-n{limit}",
                "--format=%H%x00%s",
                "--name-only",
                "--",
                "*.py",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return []
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []
    commits: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in (out.stdout or "").splitlines():
        if "\0" in line:
            if current:
                commits.append(current)
            sha, subj = line.split("\0", 1)
            current = {"sha": sha.strip(), "subject": subj.strip(), "files": ""}
        elif current and line.strip() and line.endswith(".py"):
            current["files"] = (current["files"] + " " + line.strip()).strip()
    if current:
        commits.append(current)
    return commits


def _git_show_file(repo_path: Path, rev: str, file_path: str) -> Optional[str]:
    """Get file content at revision. Returns None on failure."""
    try:
        out = subprocess.run(
            ["git", "show", f"{rev}:{file_path}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def extract_before_after_from_repo(
    repo_path: Path,
    project_name: str,
    max_entries: int = 10,
    min_lines: int = 15,
    max_lines: int = 400,
) -> List[Dict[str, Any]]:
    """
    Extract before/after pairs from refactor commits in a single repo.

    Returns list of {project, module, before, after, commit, hint}.
    """
    if not _git_available(repo_path):
        return []
    entries: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for c in _git_refactor_commits(repo_path, limit=20):
        sha = c.get("sha", "")
        if not sha:
            continue
        files_str = c.get("files", "")
        for rel in files_str.split():
            if not rel.endswith(".py"):
                continue
            key = (sha, rel)
            if key in seen:
                continue
            seen.add(key)
            before = _git_show_file(repo_path, f"{sha}^", rel)
            after = _git_show_file(repo_path, sha, rel)
            if not before or not after or before == after:
                continue
            bl, al = len(before.splitlines()), len(after.splitlines())
            if bl < min_lines or bl > max_lines or al < min_lines or al > max_lines:
                continue
            hint = f"OSS refactor: {project_name} — {c.get('subject', '')[:60]}"
            entries.append({
                "project": project_name,
                "module": rel,
                "before": before,
                "after": after,
                "commit": sha[:8],
                "hint": hint,
            })
            if len(entries) >= max_entries:
                return entries
    return entries


def extract_before_after_from_repos(
    cache_dir: Path,
    max_per_kind: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract before/after pairs from all curated repos in cache_dir.

    Returns {long_function_before_after: [...], deep_nesting_before_after: [...]}.
    Phase 5: OSS before/after for LLM few-shot (REFACTOR_CODE_SMELL_PLAN).
    """
    out: Dict[str, List[Dict[str, Any]]] = {
        "long_function_before_after": [],
        "deep_nesting_before_after": [],
    }
    if not cache_dir.exists():
        return out
    total = 0
    for subdir in sorted(cache_dir.iterdir()):
        if not subdir.is_dir():
            continue
        project = subdir.name
        pairs = extract_before_after_from_repo(
            subdir, project, max_entries=max_per_kind // 2,
        )
        for p in pairs:
            if total >= max_per_kind:
                break
            out["long_function_before_after"].append(p)
            total += 1
        if total >= max_per_kind:
            break
    out["deep_nesting_before_after"] = []  # Same source for now; can refine later
    return out
