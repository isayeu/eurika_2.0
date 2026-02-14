"""Facade to the legacy `core.snapshot` module.

The real implementation currently lives in `core/snapshot.py`.
This wrapper exists to provide a stable import path:

    from eurika.core.snapshot import ArchitectureSnapshot
"""

from core.snapshot import *  # noqa: F401,F403

