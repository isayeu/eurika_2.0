from __future__ import annotations

"""
Project graph public API.

Thin facade that re-exports:
- ProjectGraph (core dependency graph model),
- NodeMetrics (per-node fan-in/fan-out/layer metrics).

Downstream modules should import from this facade instead of depending
directly on project_graph.py, to keep the core graph model less centralised.
"""

from project_graph import NodeMetrics, ProjectGraph

__all__ = ["ProjectGraph", "NodeMetrics"]
