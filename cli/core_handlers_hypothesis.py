"""CLI: hypotheses — Hypothesis Engine v0 (VISION § Master Stage 3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_hypotheses(args: Any) -> int:
    from eurika.api.hypothesis_engine import (
        format_hypotheses_text,
        hypotheses_path,
        refresh_hypotheses,
    )

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    payload = refresh_hypotheses(path)
    if bool(getattr(args, "json", False)) or bool(getattr(args, "quiet", False)):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_hypotheses_text(payload, mode="full"))
        print(f"\n(written {hypotheses_path(path)})")
    return 0
