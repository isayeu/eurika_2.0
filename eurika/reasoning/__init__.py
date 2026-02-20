"""Reasoning facade package with lazy submodule loading."""

from importlib import import_module

__all__ = [
    "advisor",
    "architect",
    "planner",
    "heuristics",
    "refactor_plan",
    "graph_ops",
]


def __getattr__(name: str):
    if name in __all__:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

