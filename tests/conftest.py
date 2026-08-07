"""Pytest configuration. Ensures project root is in sys.path for top-level modules (code_awareness, patch_plan, etc)."""
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Same LLM routing as the app: without .env, tests fall back to local Ollama
# and hang on its timeout even when an API provider is configured.
try:
    from eurika.utils.env import LLM_ROUTING_ENV_KEYS, load_project_dotenv

    load_project_dotenv(_root, keys=LLM_ROUTING_ENV_KEYS)
except Exception:
    pass

_FUZZY_INTENT_FLAGS = ("EURIKA_USE_ML_INTENT", "EURIKA_USE_VECTOR_INTENT")


@pytest.fixture(autouse=True)
def _fuzzy_intent_flags_off() -> Iterator[None]:
    """Keep ML/vector routing opt-in per test.

    Anything that loads the full project .env mid-session (e.g. constructing the
    Qt main window) would otherwise enable them for every later test, making
    routing non-deterministic and issuing a local embedding call per message.
    """
    for flag in _FUZZY_INTENT_FLAGS:
        os.environ.pop(flag, None)
    yield
    for flag in _FUZZY_INTENT_FLAGS:
        os.environ.pop(flag, None)
