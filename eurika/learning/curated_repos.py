"""Curated OSS repos for Learning from GitHub (ROADMAP 3.0.5.1).

Clone, scan, extract smell→fix patterns from Django, FastAPI and similar projects.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


# Default curated list: stable Python OSS projects for pattern extraction
CURATED_REPOS: list[dict[str, Any]] = [
    {"url": "https://github.com/django/django.git", "name": "django", "branch": "main"},
    {"url": "https://github.com/tiangolo/fastapi.git", "name": "fastapi", "branch": "master"},
    {"url": "https://github.com/encode/httpx.git", "name": "httpx", "branch": "master"},
    {"url": "https://github.com/pallets/flask.git", "name": "flask", "branch": "main"},
]


def load_curated_repos(config_path: Path | None) -> list[dict[str, Any]]:
    """Load curated repos from JSON config, or return default CURATED_REPOS."""
    if config_path and config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            repos = data.get("repos", data) if isinstance(data, dict) else []
            if isinstance(repos, list) and repos:
                return repos
        except (json.JSONDecodeError, OSError):
            pass
    return CURATED_REPOS.copy()


def clone_repo(url: str, dest: Path, branch: str | None = None, *, timeout: int = 180) -> tuple[bool, str]:
    """Clone repo into dest. Returns (success, error_message)."""
    if dest.exists() and (dest / ".git").exists():
        return True, ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([url, str(dest)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd="/")
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "unknown").strip()
            return False, err[:500]
        return (dest / ".git").exists(), ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:200]


def ensure_repo_cloned(
    repo: dict[str, Any],
    cache_dir: Path,
    *,
    timeout: int = 180,
) -> tuple[Path | None, str]:
    """Clone repo into cache_dir/name if not present. Returns (path_or_none, error_message)."""
    name = repo.get("name") or repo.get("url", "").rstrip("/").split("/")[-1].removesuffix(".git")
    url = repo.get("url", "")
    branch = repo.get("branch")
    dest = cache_dir / name
    ok, err = clone_repo(url, dest, branch, timeout=timeout)
    return (dest if ok else None), err
