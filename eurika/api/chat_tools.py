"""Chat tool calls (ROADMAP 3.6.8 Phase 1).

Provides git_status, git_diff, git_commit for Chat flow.
Invoked when user intent is commit-related (e.g. «собери коммит»).
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Tuple


def git_status(project_root: Path) -> Tuple[bool, str]:
    """Run git status in project root. Returns (ok, output)."""
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        if r.returncode != 0 and not out:
            out = f"git status failed (exit {r.returncode})"
        return (r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return (False, "git status: timeout")
    except Exception as e:
        return (False, f"git status: {e}")


def git_diff(project_root: Path, staged: bool = False) -> Tuple[bool, str]:
    """Run git diff in project root. Returns (ok, output)."""
    try:
        args = ["git", "diff", "--no-color"]
        if staged:
            args.append("--cached")
        r = subprocess.run(
            args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        if r.returncode != 0 and not out:
            out = f"git diff failed (exit {r.returncode})"
        return (r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return (False, "git diff: timeout")
    except Exception as e:
        return (False, f"git diff: {e}")


def git_commit(project_root: Path, message: str) -> Tuple[bool, str]:
    """Run git add -A and git commit -m in project root. Returns (ok, output)."""
    if not message or not message.strip():
        return (False, "commit message is empty")
    try:
        add_r = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if add_r.returncode != 0:
            err = (add_r.stderr or add_r.stdout or "").strip() or f"exit {add_r.returncode}"
            return (False, f"git add -A failed: {err}")
        commit_r = subprocess.run(
            ["git", "commit", "-m", message.strip()],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (commit_r.stdout or "").strip() or (commit_r.stderr or "").strip()
        if commit_r.returncode != 0 and not out:
            out = f"git commit failed (exit {commit_r.returncode})"
        return (commit_r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return (False, "git commit: timeout")
    except Exception as e:
        return (False, f"git commit: {e}")
