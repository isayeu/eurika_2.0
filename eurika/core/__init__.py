"""Core orchestration layer (facade).

For now this package re-exports the existing flat-core modules
(`core.pipeline`, `core.snapshot`) to match the target layout without
changing behaviour.
"""

from . import pipeline, snapshot  # noqa: F401

__all__ = ["pipeline", "snapshot"]

