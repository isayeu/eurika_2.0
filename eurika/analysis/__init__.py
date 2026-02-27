"""Analysis layer namespace.

Keep package import lightweight: submodules are loaded on demand to avoid
hard dependency on legacy flat modules during startup.
"""

__all__ = ["graph", "scanner", "metrics", "cycles", "self_map", "topology"]

