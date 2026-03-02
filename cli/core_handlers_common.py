"""Shared helpers for core CLI handlers (P0.4 split)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_WHITELIST_DRAFT_ALLOWED_KINDS = frozenset(
    {
        "remove_unused_import",
        "remove_cyclic_import",
        "fix_import",
        "create_module_stub",
        "split_module",
        "extract_class",
        "extract_block_to_helper",
        "extract_nested_function",
        "refactor_module",
        "refactor_code_smell",
        "introduce_facade",
    }
)


def _err(msg: str) -> None:
    """Log unified error message (R2: via logger, respects --quiet)."""
    _clog().error("eurika: %s", msg)


def _clog() -> Any:
    from eurika.orchestration.logging import get_logger

    return get_logger("core_handlers")


def _paths_from_args(args: Any) -> list[Path]:
    """Normalize path(s) from args (ROADMAP 3.0.1 multi-repo). Returns list of resolved Paths."""
    raw = getattr(args, "path", None)
    if not raw:
        return [Path(".").resolve()]
    if isinstance(raw, Path):
        return [raw.resolve()]
    return [Path(p).resolve() for p in raw]


def _check_path(path: Path, must_be_dir: bool = True) -> int:
    """Return 0 if path is valid, 1 and print error otherwise."""
    if not path.exists():
        _err(f"path does not exist: {path}")
        return 1
    if must_be_dir and (not path.is_dir()):
        _err(f"not a directory: {path}")
        return 1
    return 0


def _format_layer_discipline_block(path: Path) -> str:
    """Return layer discipline report for self-check (R1, Architecture.md §0.6)."""
    from eurika.checks.dependency_firewall import (
        collect_dependency_violations,
        collect_layer_violations,
    )

    forbidden = collect_dependency_violations(path)
    layer_viol = collect_layer_violations(path)
    if not forbidden and not layer_viol:
        return "\nLAYER DISCIPLINE: OK (0 forbidden, 0 layer violations)\n"
    lines = ["", "LAYER DISCIPLINE (R1, Architecture.md §0.6)", ""]
    if forbidden:
        lines.append("Forbidden imports:")
        for v in forbidden[:10]:
            lines.append(f"  - {v.path} -> {v.forbidden_module}")
        if len(forbidden) > 10:
            lines.append(f"  ... +{len(forbidden) - 10} more")
        lines.append("")
    if layer_viol:
        lines.append("Layer violations (upward):")
        for lv in layer_viol[:10]:
            lines.append(f"  - {lv.path} -> {lv.imported_module} (L{lv.source_layer}->L{lv.target_layer})")
        if len(layer_viol) > 10:
            lines.append(f"  ... +{len(layer_viol) - 10} more")
    return "\n".join(lines)


def _format_file_size_block(path: Path) -> str:
    """Return file size limits report for self-check (3.1-arch.3)."""
    from eurika.checks import check_file_size_limits

    candidates, must_split = check_file_size_limits(path, include_tests=True)
    if not candidates and not must_split:
        return ""
    lines = ["", "FILE SIZE LIMITS (ROADMAP 3.1-arch.3)", "  >400 LOC = candidate; >600 LOC = must split", ""]
    if must_split:
        lines.append("Must split (>600):")
        for rel, count in must_split[:10]:
            lines.append(f"  - {rel} ({count})")
        if len(must_split) > 10:
            lines.append(f"  ... +{len(must_split) - 10} more")
        lines.append("")
    if candidates:
        lines.append("Candidates (>400):")
        for rel, count in candidates[:5]:
            lines.append(f"  - {rel} ({count})")
        if len(candidates) > 5:
            lines.append(f"  ... +{len(candidates) - 5} more")
    return "\n".join(lines)


def _aggregate_multi_repo_reports(project_reports: list[dict[str, Any]], paths: list[Path]) -> dict[str, Any]:
    """Build aggregated JSON for multi-repo (ROADMAP 3.0.1)."""
    total_modules = 0
    total_risks = 0
    for r in project_reports:
        s = (r.get("summary") or {}).get("system") or {}
        total_modules += int(s.get("modules", 0) or 0)
        total_risks += len((r.get("summary") or {}).get("risks") or [])
    return {
        "projects": [{"path": str(p), "report": r} for p, r in zip(paths, project_reports)],
        "aggregate": {"total_projects": len(paths), "total_modules": total_modules, "total_risks": total_risks},
    }


def _aggregate_multi_repo_fix_reports(paths: list[Path]) -> dict[str, Any] | None:
    """Build aggregated fix JSON for multi-repo (3.0.1). Reads eurika_fix_report.json per path."""
    pairs: list[tuple[Path, dict[str, Any]]] = []
    for p in paths:
        fp = p / "eurika_fix_report.json"
        if not fp.exists():
            continue
        try:
            pairs.append((p, json.loads(fp.read_text(encoding="utf-8"))))
        except Exception:
            continue
    if len(pairs) < 2:
        return None
    reports = [r for _, r in pairs]
    total_modified = sum(int(r.get("modified", 0) or 0) for r in reports)
    total_skipped = sum(int(r.get("skipped", 0) or 0) for r in reports)
    telemetry_list = [r.get("telemetry") for r in reports if r.get("telemetry")]
    return {
        "projects": [{"path": str(p), "report": r} for p, r in pairs],
        "aggregate": {
            "total_projects": len(pairs),
            "total_modified": total_modified,
            "total_skipped": total_skipped,
            "telemetry_list": telemetry_list,
        },
    }
