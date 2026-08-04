"""Rolling operational metrics from patch events (ROADMAP 2.7.8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _aggregate_patch_event_counts(events: list[Any]) -> tuple[int, int, int, list[int]]:
    """From patch events: total_ops, total_modified, rollback_count, durations list."""
    total_ops = 0
    total_modified = 0
    rollback_count = 0
    durations: list[int] = []
    for e in events:
        inp = getattr(e, "input", None) or {}
        out = getattr(e, "output", None) or {}
        ops = int(inp.get("operations_count", 0) or 0)
        modified = out.get("modified") or []
        mod_count = len(modified) if isinstance(modified, list) else 0
        if out.get("verify_success") is False:
            rollback_count += 1
        total_ops += ops
        total_modified += mod_count
        ms = out.get("verify_duration_ms")
        if isinstance(ms, (int, float)) and ms is not None and ms > 0:
            durations.append(int(ms))
    return total_ops, total_modified, rollback_count, durations


def _median_int(values: list[int]) -> int | None:
    """Return median of non-empty list, else None."""
    if not values:
        return None
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        return int(sorted_vals[mid])
    return int((sorted_vals[mid - 1] + sorted_vals[mid]) / 2)


def aggregate_operational_metrics(path: Path, window: int = 10) -> dict[str, Any] | None:
    """
    Aggregate apply-rate, rollback-rate, median verify time from last N patch events.

    Returns dict with: runs_count, apply_rate, rollback_rate, median_verify_time_ms,
    total_modified, total_ops. Returns None if no patch events.
    """
    try:
        from eurika.storage import ProjectMemory

        memory = ProjectMemory(path)
        events = memory.events.recent_events(limit=window, types=("patch",))
    except Exception:
        return None
    if not events:
        return None

    total_ops, total_modified, rollback_count, durations = _aggregate_patch_event_counts(events)
    apply_rate = (total_modified / total_ops) if total_ops else 0.0
    rollback_rate = rollback_count / len(events)
    median_ms = _median_int(durations)

    return {
        "runs_count": len(events),
        "apply_rate": round(apply_rate, 4),
        "rollback_rate": round(rollback_rate, 4),
        "median_verify_time_ms": median_ms,
        "total_modified": total_modified,
        "total_ops": total_ops,
    }
