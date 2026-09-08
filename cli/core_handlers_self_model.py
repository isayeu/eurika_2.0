"""CLI: self-model — Self + Capability + Goal snapshot (VISION § Master)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_self_model(args: Any) -> int:
    from eurika.api.self_model import (
        format_self_model_text,
        load_self_model,
        snapshot_path,
    )

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    snap = load_self_model(path, refresh=True, persist=True)
    if bool(getattr(args, "json", False)) or bool(getattr(args, "quiet", False)):
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_self_model_text(snap, mode="full"))
        print(f"\n(written {snapshot_path(path)})")
    return 0
