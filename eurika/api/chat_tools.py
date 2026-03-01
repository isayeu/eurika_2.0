"""Chat tool calls (ROADMAP 3.6.8 Phase 1).

Provides git_status, git_diff, git_commit, run_eurika_ritual for Chat flow.
Invoked when user intent is commit-related or ritual-related.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Tuple


def run_eurika_command(project_root: Path, subcommand: str, *args: str, timeout: int = 180) -> Tuple[bool, str]:
    """Run eurika CLI subcommand. Returns (ok, output)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "eurika_cli", subcommand, str(project_root), *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0 and not out:
            out = f"eurika {subcommand} failed (exit {r.returncode})"
        return (r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return (False, f"eurika {subcommand}: timeout")
    except Exception as e:
        return (False, f"eurika {subcommand}: {e}")


def run_eurika_ritual(project_root: Path) -> Tuple[bool, str]:
    """Run scan → doctor → report-snapshot. Returns (ok, combined output)."""
    parts: list[str] = []
    steps = [
        ("scan", []),
        ("doctor", ["--quiet", "--no-llm"]),
        ("report-snapshot", []),
    ]
    all_ok = True
    for cmd, extra in steps:
        ok, out = run_eurika_command(project_root, cmd, *extra, timeout=180)
        parts.append(f"--- eurika {cmd} ---\n{out[:4000]}{'...' if len(out) > 4000 else ''}")
        if not ok:
            all_ok = False
            break
    return (all_ok, "\n\n".join(parts))


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
