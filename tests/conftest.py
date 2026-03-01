"""Pytest configuration. Ensures project root is in sys.path for top-level modules (code_awareness, runtime_scan, architecture_pipeline)."""
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _add_project_root_to_path():
    root = Path(__file__).resolve().parent.parent
    import sys
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
