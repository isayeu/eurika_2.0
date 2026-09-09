"""CLI: ab-compare — Formal A/B v0 (VISION Stage 4 Experimenter)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_ab_compare(args: Any) -> int:
    from eurika.evaluation.ab_compare import (
        ab_trials_path,
        format_ab_text,
        load_ab_trials,
    )

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    trials = load_ab_trials(path)
    if bool(getattr(args, "json", False)) or bool(getattr(args, "quiet", False)):
        print(
            json.dumps(
                {
                    "version": 1,
                    "path": str(ab_trials_path(path)),
                    "count": len(trials),
                    "trials": trials[-20:],
                    "note": "A/B does not auto-apply; HITL still required",
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        print(format_ab_text(path, limit=8))
        print(f"\n(source {ab_trials_path(path)})")
    return 0
