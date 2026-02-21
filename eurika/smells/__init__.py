"""Smell engine façade.

For v0.9 this package re-exports the existing smell/diagnostics modules.
"""

from . import detector, rules, models  # noqa: F401

__all__ = ["detector", "rules", "models"]

