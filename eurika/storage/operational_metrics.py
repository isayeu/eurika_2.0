"""Rolling operational metrics from patch events (ROADMAP 2.7.8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
        success = out.get("verify_success")
        if success is False:
            rollback_count += 1
        total_ops += ops
        total_modified += mod_count
        ms = out.get("verify_duration_ms")
        if isinstance(ms, (int, float)) and ms is not None and ms > 0:
            durations.append(int(ms))

    apply_rate = (total_modified / total_ops) if total_ops else 0.0
    rollback_rate = rollback_count / len(events) if events else 0.0

    median_ms: int | None = None
    if durations:
        durations.sort()
        mid = len(durations) // 2
        median_ms = int(
            durations[mid]
            if len(durations) % 2
            else (durations[mid - 1] + durations[mid]) / 2
        )

    return {
        "runs_count": len(events),
        "apply_rate": round(apply_rate, 4),
        "rollback_rate": round(rollback_rate, 4),
        "median_verify_time_ms": median_ms,
        "total_modified": total_modified,
        "total_ops": total_ops,
    }


# TODO (eurika): refactor long_function 'aggregate_operational_metrics' — consider extracting helper
