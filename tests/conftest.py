"""Pytest configuration. Ensures project root is in sys.path for top-level modules (code_awareness, patch_plan, etc)."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
