"""CLI package namespace.

Keep package import side-effect free so submodules can be imported independently
without pulling full handler graph (important for API usage from Qt shell).
"""

__all__ = []
