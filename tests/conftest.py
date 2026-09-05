"""Pytest configuration. Ensures project root is in sys.path for top-level modules (code_awareness, patch_plan, etc)."""
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Do not inherit the operator's ~/.eurika/qt_settings.json (Cursor vs Groq).
os.environ.setdefault(
    "EURIKA_QT_SETTINGS_PATH",
    str(_root / ".eurika" / "qt_settings.pytest-absent.json"),
)

# Same LLM routing as the app: without .env, tests fall back to local Ollama
# and hang on its timeout even when an API provider is configured.
try:
    from eurika.utils.env import LLM_ROUTING_ENV_KEYS, load_project_dotenv

    load_project_dotenv(_root, keys=LLM_ROUTING_ENV_KEYS)
except Exception:
    pass

_FUZZY_INTENT_FLAGS = ("EURIKA_USE_ML_INTENT", "EURIKA_USE_VECTOR_INTENT")


@pytest.fixture(scope="session", autouse=True)
def _close_lingering_qt_windows() -> Iterator[None]:
    """Avoid QThread abort when the session tears down a leaked MainWindow."""
    yield
    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
        except Exception:
            pass
    try:
        app.processEvents()
    except Exception:
        pass
    # Interpreter shutdown destroys QThread wrappers while native threads still
    # run → "QThread: Destroyed while thread is still running" → SIGABRT, which
    # made release_check treat a green suite as FAIL.
    try:
        for thread in list(app.findChildren(QThread)):
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(2000)
            except Exception:
                pass
    except Exception:
        pass


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
