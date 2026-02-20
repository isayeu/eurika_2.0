"""Dependency loader for fix-cycle apply/rescan stages."""

from __future__ import annotations

from typing import Any, TypedDict


class FixCycleDeps(TypedDict):
    """Resolved callables/constants for fix-cycle runtime stages."""

    BACKUP_DIR: str
    apply_and_verify: Any
    rollback_patch: Any
    run_scan: Any
    build_snapshot_from_self_map: Any
    diff_architecture_snapshots: Any
    metrics_from_graph: Any


def load_fix_cycle_deps() -> FixCycleDeps:
    """Load runtime dependencies for fix apply/rescan stages."""
    from patch_apply import BACKUP_DIR
    from patch_engine import apply_and_verify, rollback_patch
    from runtime_scan import run_scan
    from eurika.core.pipeline import build_snapshot_from_self_map
    from eurika.evolution.diff import diff_architecture_snapshots
    from eurika.reasoning.graph_ops import metrics_from_graph

    return {
        "BACKUP_DIR": BACKUP_DIR,
        "apply_and_verify": apply_and_verify,
        "rollback_patch": rollback_patch,
        "run_scan": run_scan,
        "build_snapshot_from_self_map": build_snapshot_from_self_map,
        "diff_architecture_snapshots": diff_architecture_snapshots,
        "metrics_from_graph": metrics_from_graph,
    }
