"""Chat tool calls (ROADMAP 3.6.8 Phase 1).

Provides git_status, git_diff, git_commit, git_push, run_eurika_ritual for Chat flow.
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


def run_release_check(project_root: Path, timeout: int | None = None) -> Tuple[bool, str]:
    """Run scripts/release_check.sh (CR-B2). Returns (ok, output)."""
    root = Path(project_root).resolve()
    script = root / "scripts" / "release_check.sh"
    if not script.exists():
        return (False, f"Скрипт не найден: {script}")
    try:
        r = subprocess.run(
            ["bash", str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        if r.returncode != 0 and not out:
            out = f"release_check failed (exit {r.returncode})"
        return (r.returncode == 0, out)
    except subprocess.TimeoutExpired:
        return (False, "release_check: timeout")
    except Exception as e:
        return (False, f"release_check: {e}")


def git_commit(
    project_root: Path, message: str, paths: list[str] | None = None
) -> Tuple[bool, str]:
    """Stage listed paths (or all non-secret dirty files) and commit via stdin.

    Never ``git add -A``, never ``--no-verify``.
    """
    from eurika.api.chat_git import collect_commit_preview, commit_selected

    try:
        if paths is None:
            preview = collect_commit_preview(project_root)
            if not preview.get("ok"):
                return (False, str(preview.get("error") or "git status failed"))
            paths = list(preview.get("include") or [])
        ok, out, _term = commit_selected(project_root, message, list(paths or []))
        return (ok, out)
    except subprocess.TimeoutExpired:
        return (False, "git commit: timeout")
    except Exception as e:
        return (False, f"git commit: {e}")


def git_push(project_root: Path) -> Tuple[bool, str]:
    """Push current branch to origin (set upstream if missing). Never --force."""
    from eurika.api.chat_git import push_current_branch

    try:
        ok, out, _term = push_current_branch(project_root)
        return (ok, out)
    except subprocess.TimeoutExpired:
        return (False, "git push: timeout")
    except Exception as e:
        return (False, f"git push: {e}")


def run_chat_smoke(project_root: Path, *, timeout: int = 120) -> Tuple[bool, str]:
    """Fast smoke for chat: PyTorch probe + Qt pytest smoke (no release_check)."""
    root = Path(project_root).resolve()
    parts: list[str] = ["SMOKE (chat)", ""]
    ok = True

    try:
        from eurika.ml.torch_runtime import format_torch_block, torch_status

        st = torch_status(run_smoke_check=True)
        parts.append(format_torch_block(st).strip())
        if st.get("available") and st.get("smoke_ok") is False:
            ok = False
    except Exception as exc:
        parts.append(f"PYTORCH\n  error: {type(exc).__name__}: {exc}")
        ok = False

    parts.append("")
    smoke_path = root / "tests" / "test_qt_smoke.py"
    if smoke_path.is_file():
        from eurika.api.chat_direct import run_qt_smoke_test

        qt_out = run_qt_smoke_test(root, timeout=timeout)
        parts.append(qt_out)
        if "FAIL" in qt_out or "timeout" in qt_out.lower():
            ok = False
    else:
        parts.append("qt smoke: skip (tests/test_qt_smoke.py нет)")

    parts.append("")
    parts.append("ok" if ok else "fail")
    parts.append("note: полный self-check — «проведи self-check»; release — «прогони release check»")
    return (ok, "\n".join(parts))


def run_self_check_capture(project_root: Path, *, timeout: int = 180) -> Tuple[bool, str]:
    """Run ``eurika self-check`` and capture output for chat."""
    return run_eurika_command(project_root, "self-check", timeout=timeout)
