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

    def _collect_mtimes() -> dict:
        out: dict = {}
        for f in path.rglob("*.py"):
            if any(s in f.parts for s in skip_dirs):
                continue
            try:
                out[str(f.relative_to(path))] = f.stat().st_mtime
            except (OSError, ValueError):
                pass
        return out

    prev = _collect_mtimes()
    if not quiet:
        print(f"eurika watch: monitoring {len(prev)} .py files (poll every {poll_sec}s, Ctrl+C to stop)", file=sys.stderr)
    run_count = 0
    try:
        while True:
            time.sleep(poll_sec)
            curr = _collect_mtimes()
            if curr != prev:
                run_count += 1
                if not quiet:
                    print(f"\neurika watch: changes detected, running fix (#{run_count})...", file=sys.stderr)
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
                prev = _collect_mtimes()
            else:
                prev = curr
    except KeyboardInterrupt:
        if not quiet:
            print("\neurika watch: stopped (Ctrl+C)", file=sys.stderr)
    return 0
