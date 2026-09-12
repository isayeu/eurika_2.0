"""JSON file I/O utilities (L0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    """Narrow a JSON-ish mapping; never return None (mypy union-attr)."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Narrow a JSON-ish sequence; never return None."""
    return list(value) if isinstance(value, list) else []


def load_json_safe(path: Path) -> dict[str, Any] | None:
    """Load JSON from path; return dict or None on failure (missing, invalid, non-dict)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
