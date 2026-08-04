"""Append-only chat routing metrics (.eurika/chat_metrics.jsonl)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _metrics_enabled() -> bool:
    raw = (os.environ.get("EURIKA_CHAT_METRICS") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def record_chat_metric(project_root: Path, event: str, **fields: Any) -> None:
    """Best-effort metric append; never breaks chat flow."""
    if not _metrics_enabled():
        return
    root = Path(project_root).resolve()
    try:
        metrics_dir = root / ".eurika"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }
        path = metrics_dir / "chat_metrics.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
