"""Scan and self-check handlers (P0.4 split)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core_handlers_common import (
    _check_path,
    _clog,
    _format_file_size_block,
    _format_layer_discipline_block,
    _paths_from_args,
)


def handle_scan(args: Any) -> int:
    from runtime_scan import run_scan

    paths = _paths_from_args(args)
    exit_code = 0
    for i, path in enumerate(paths):
        if len(paths) > 1:
            _clog().info("\n--- Project %s/%s: %s ---\n", i + 1, len(paths), path)
        if _check_path(path) != 0:
            exit_code = 1
            continue
        fmt = getattr(args, "format", "text")
        color = getattr(args, "color", None)
        if run_scan(path, format=fmt, color=color) != 0:
            exit_code = 1
    return exit_code


def handle_self_check(args: Any) -> int:
    """Run full scan on the project (self-analysis ritual: Eurika analyzes itself)."""
    from runtime_scan import run_scan

    from eurika.checks.self_guard import collect_self_guard, format_self_guard_block, self_guard_pass

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    _clog().info("eurika: self-check — analyzing project architecture...")
    fmt = getattr(args, "format", "text")
    color = getattr(args, "color", None)
    code = run_scan(path, format=fmt, color=color)
    lf_report = _format_layer_discipline_block(path)
    if lf_report:
        _clog().info("%s", lf_report)
    fs_report = _format_file_size_block(path)
    if fs_report:
        _clog().info("%s", fs_report)
    guard_result = collect_self_guard(path)
    _clog().info("%s", format_self_guard_block(guard_result))
    if getattr(args, "strict", False) and not self_guard_pass(guard_result):
        return 1
    return code
