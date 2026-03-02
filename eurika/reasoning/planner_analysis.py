"""Shim: re-export from planner.analysis (ROADMAP v3.0 Stage 1)."""
from eurika.reasoning.planner.analysis import (  # noqa: F401
    build_steps_from_priorities,
    index_smells_by_node,
)

__all__ = ["build_steps_from_priorities", "index_smells_by_node"]
