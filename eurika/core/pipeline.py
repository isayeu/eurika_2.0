"""Facade to the legacy `core.pipeline` module with explicit exports."""

from core.pipeline import build_snapshot_from_self_map, run_full_analysis

__all__ = ["run_full_analysis", "build_snapshot_from_self_map"]

