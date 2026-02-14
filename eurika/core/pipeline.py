"""Facade to the legacy `core.pipeline` module.

The real implementation currently lives in `core/pipeline.py`.
This wrapper exists to provide a stable import path:

    from eurika.core import pipeline
    # or
    from eurika.core.pipeline import run_full_analysis

without changing any behaviour.
"""

from core.pipeline import *  # noqa: F401,F403

