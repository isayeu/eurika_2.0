"""Watch handler (P0.4 split)."""

from __future__ import annotations

import sys
import time
from typing import Any

from .core_handlers_common import _check_path


def handle_watch(args: Any) -> int:
    """Watch for .py file changes and run fix when detected (ROADMAP 2.6.2)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    poll_sec = int(getattr(args, "poll", 5) or 5)
    quiet = getattr(args, "quiet", False)
    skip_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", ".eurika_backups", ".eurika"}

    prev_mtimes = _collect_mtimes(path, skip_dirs)

    if not quiet:
        print(f"eurika watch: monitoring {len(prev_mtimes)} .py files (poll every {poll_sec}s, Ctrl+C to stop)", file=sys.stderr)
    try:
        while True:
            time.sleep(poll_sec)
            curr_mtimes = _collect_mtimes(path, skip_dirs)
            if curr_mtimes != prev_mtimes:
                run_fix(args, path, quiet)
                prev_mtimes = curr_mtimes
    except KeyboardInterrupt:
        if not quiet:
            print("\neurika watch: stopped (Ctrl+C)", file=sys.stderr)
    return 0

def _collect_mtimes(path, skip_dirs) -> dict:
    out: dict = {}
    for f in path.rglob("*.py"):
        if any(s in f.parts for s in skip_dirs):
            continue
        try:
            out[str(f.relative_to(path))] = f.stat().st_mtime
        except (OSError, ValueError):
            pass
    return out

def run_fix(args, path, quiet) -> None:
    from types import SimpleNamespace

    from cli.agent_handlers import handle_agent_cycle

    fix_args = SimpleNamespace(
        path=path,
        window=getattr(args, "window", 5),
        dry_run=False,
        quiet=quiet,
        no_clean_imports=getattr(args, "no_clean_imports", False),
        no_code_smells=getattr(args, "no_code_smells", False),
        interval=0,
    )
    handle_agent_cycle(fix_args)