"""
Failure log — legacy; FailureLog is now a bounded view over EventLog (ARCHITECTURE_MEMORY_REVIEW).

get_recent_failures reads from EventLog (learn events, result=False). Single source of truth.
append_failures/load_recent_failures kept for migration; not used by record_outcome.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Tuple

from .paths import ensure_storage_dir, storage_path

MAX_FAILURES = 100


def _failures_path(root: Path) -> Path:
    return storage_path(Path(root).resolve(), "failures")


def append_failures(
    project_root: Path,
    entries: List[Tuple[str, str, str]],
) -> None:
    """Append failure entries. Keeps last MAX_FAILURES."""
    if not entries:
        return
    root = Path(project_root).resolve()
    ensure_storage_dir(root)
    path = _failures_path(root)
    records = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = list(data.get("failures", [])) or []
        except (json.JSONDecodeError, OSError):
            records = []
    ts = time.time()
    for tf, k, reason in entries:
        records.append({
            "target_file": tf,
            "kind": k,
            "failure_reason": reason,
            "timestamp": ts,
        })
    records = records[-MAX_FAILURES:]
    path.write_text(
        json.dumps({"failures": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_recent_failures(
    project_root: Path,
    limit: int = 20,
) -> List[Tuple[str, str, str]]:
    """Load (target_file, kind, failure_reason) from failure log, newest first."""
    path = _failures_path(Path(project_root).resolve())
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = list(data.get("failures", [])) or []
    except (json.JSONDecodeError, OSError):
        return []
    out: List[Tuple[str, str, str]] = []
    seen: set[Tuple[str, str, str]] = set()
    for r in reversed(records[-limit * 3:]):
        tf = str(r.get("target_file") or "")
        k = str(r.get("kind") or "")
        reason = str(r.get("failure_reason") or "")
        if (tf or k) and reason:
            key = (tf, k, reason)
            if key not in seen:
                seen.add(key)
                out.append(key)
                if len(out) >= limit:
                    break
    return out


__all__ = ["append_failures", "load_recent_failures"]
