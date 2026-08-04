"""Reasoning facade package with lazy submodule loading."""

from importlib import import_module

__all__ = [
    "advisor",
    "analyzer",
    "architect",
    "evaluator",
    "execution_context",
    "generator",
    "graph_ops",
    "heuristics",
    "planner",
    "refactor_plan",
]


def __getattr__(name: str):
    if name in __all__:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

