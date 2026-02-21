"""Analysis layer (graph, scanning, metrics) — façade.

For v0.9 this package only re-exports the existing flat analysis modules
to align with the target layout while keeping behaviour unchanged.
"""

from . import graph, scanner, metrics, cycles, self_map, topology  # noqa: F401

__all__ = ["graph", "scanner", "metrics", "cycles", "self_map", "topology"]

