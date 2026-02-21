"""
Cross-project memory (ROADMAP 3.0.2).

Global learning store at ~/.eurika/ or EURIKA_GLOBAL_MEMORY.
Learning from project A is considered when fixing project B (smell|action match).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_global_memory_root() -> Optional[Path]:
    """Return global memory directory; None if disabled via EURIKA_DISABLE_GLOBAL_MEMORY."""
    if os.environ.get("EURIKA_DISABLE_GLOBAL_MEMORY", "").strip().lower() in ("1", "true", "yes"):
        return None
    if os.environ.get("EURIKA_GLOBAL_MEMORY"):
        p = Path(os.environ["EURIKA_GLOBAL_MEMORY"]).resolve()
        return p
    return Path.home() / ".eurika"


def _global_events_path() -> Optional[Path]:
    root = get_global_memory_root()
    if root is None:
        return None
    return root / "events.json"


def _is_strong_refactor_code_smell_success(op: Dict[str, Any]) -> bool:
    """Marker-only refactor_code_smell should not inflate success (same as event_views)."""
    if (op.get("kind") or "") != "refactor_code_smell":
        return True
    diff = str(op.get("diff") or "")
    if "# TODO (eurika): refactor " in diff:
        return False
    return True


def append_learn_to_global(
    project_root: Path,
    modules: List[str],
    operations: List[Dict[str, Any]],
    risks: List[str],
    verify_success: Optional[bool],
) -> None:
    """Append learn event to global store. No-op if global memory disabled."""
    path = _global_events_path()
    if path is None:
        return
    try:
        from .events import EventStore
        path.parent.mkdir(parents=True, exist_ok=True)
        store = EventStore(storage_path=path)
        store.append_event(
            type="learn",
            input={
                "project_root": str(project_root),
                "modules": list(modules),
                "operations": operations,
                "risks": list(risks),
            },
            output={},
            result=verify_success,
        )
    except Exception:
        pass


def aggregate_global_by_smell_action() -> Dict[str, Dict[str, Any]]:
    """Aggregate learning from global store by smell|action. Returns {} if disabled or empty."""
    path = _global_events_path()
    if path is None or not path.exists():
        return {}
    try:
        from .events import EventStore
        store = EventStore(storage_path=path)
        stats: Dict[str, Dict[str, Any]] = {}
        sep = "|"
        for e in store.by_type("learn"):
            ops = (e.input or {}).get("operations", [])
            for op in ops:
                kind = op.get("kind", "unknown")
                smell = op.get("smell_type") or "unknown"
                key = f"{smell}{sep}{kind}"
                by_key = stats.setdefault(key, {"total": 0, "success": 0, "fail": 0})
                by_key["total"] += 1
                if e.result is True:
                    if _is_strong_refactor_code_smell_success(op):
                        by_key["success"] += 1
                elif e.result is False:
                    by_key["fail"] += 1
        return stats
    except Exception:
        return {}


def get_merged_learning_stats(project_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Return learning stats merged from local project and global store (ROADMAP 3.0.2).
    Used when building patch plan — learning from other projects influences sorting/filtering.
    """
    from .memory import ProjectMemory
    local: Dict[str, Dict[str, Any]] = {}
    try:
        local = ProjectMemory(project_root).learning.aggregate_by_smell_action()
    except Exception:
        pass
    global_stats = aggregate_global_by_smell_action()
    return merge_learning_stats(local, global_stats)


def merge_learning_stats(
    local: Dict[str, Dict[str, Any]],
    global_stats: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Merge local and global learning stats. Sum total/success/fail per smell|action key.
    Local and global contribute additively; more data improves confidence.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for key, rec in (local or {}).items():
        result[key] = {
            "total": int(rec.get("total", 0) or 0),
            "success": int(rec.get("success", 0) or 0),
            "fail": int(rec.get("fail", 0) or 0),
        }
    for key, rec in (global_stats or {}).items():
        if key not in result:
            result[key] = {"total": 0, "success": 0, "fail": 0}
        result[key]["total"] += int(rec.get("total", 0) or 0)
        result[key]["success"] += int(rec.get("success", 0) or 0)
        result[key]["fail"] += int(rec.get("fail", 0) or 0)
    return result


# TODO (eurika): refactor deep_nesting 'aggregate_global_by_smell_action' — consider extracting nested block
