"""Architecture summary/history/diff handlers (P0.4 split)."""

from __future__ import annotations

import json
from typing import Any

from .core_handlers_common import _check_path, _err


def handle_arch_summary(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    if getattr(args, "json", False):
        from eurika.api import get_summary

        data = get_summary(path)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    from architecture_pipeline import print_arch_summary

    return print_arch_summary(path)


def handle_arch_history(args: Any) -> int:
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    window = getattr(args, "window", 5)
    if getattr(args, "json", False):
        from eurika.api import get_history

        data = get_history(path, window=window)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    from architecture_pipeline import print_arch_history

    return print_arch_history(path, window=window)


def handle_arch_diff(args: Any) -> int:
    old = args.old.resolve()
    new = args.new.resolve()
    if not old.exists():
        _err(f"old self_map not found: {old}")
        return 1
    if not new.exists():
        _err(f"new self_map not found: {new}")
        return 1
    if getattr(args, "json", False):
        from eurika.api import get_diff

        data = get_diff(old, new)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    from architecture_pipeline import print_arch_diff

    return print_arch_diff(old, new)
