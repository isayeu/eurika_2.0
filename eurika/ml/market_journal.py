"""Persist Market UI transcript under ``.eurika/ml/market_journal.jsonl``.

Append-only for the active week. UI clear does not wipe the file (writes an info line).
Weekly (or size) rotation archives the file — journal is **not** training data
(``paper_trades.jsonl`` / weights must not be wiped by this).
No secrets — event text only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from eurika.ml.market_store import ml_root, read_jsonl_rows

# Transcript only — safe to rotate. Do not apply to paper_trades / weights.
JOURNAL_ROTATE_DAYS = 7
JOURNAL_ROTATE_MAX_BYTES = 16 * 1024 * 1024  # ~16 MiB
JOURNAL_ARCHIVE_KEEP = 2


def market_journal_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "market_journal.jsonl"


def _rotate_stamp_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "market_journal_rotate.json"


def _load_rotate_stamp(project_root: str | Path) -> dict[str, Any]:
    path = _rotate_stamp_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_rotate_stamp(project_root: str | Path, started_ms: int) -> None:
    path = _rotate_stamp_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"started_ms": int(started_ms), "days": JOURNAL_ROTATE_DAYS},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _prune_archives(ml_dir: Path, *, keep: int = JOURNAL_ARCHIVE_KEEP) -> None:
    archives = sorted(
        ml_dir.glob("market_journal_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in archives[max(0, int(keep)) :]:
        try:
            old.unlink()
        except OSError:
            pass


def maybe_rotate_market_journal(project_root: str | Path) -> Path | None:
    """Archive active journal if older than a week or over size cap.

    Returns archive path when rotated, else None. Creates rotate stamp on first see.
    """
    root = Path(project_root)
    path = market_journal_path(root)
    ml_dir = path.parent
    ml_dir.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)
    stamp = _load_rotate_stamp(root)
    started = int(stamp.get("started_ms") or 0)

    if not path.is_file():
        if started <= 0:
            _save_rotate_stamp(root, now_ms)
        return None

    too_big = path.stat().st_size >= JOURNAL_ROTATE_MAX_BYTES
    if started <= 0:
        if too_big:
            reason = "размер"
        else:
            _save_rotate_stamp(root, now_ms)
            return None
    else:
        too_old = (now_ms - started) >= JOURNAL_ROTATE_DAYS * 86_400_000
        if not too_old and not too_big:
            return None
        reason = "неделя" if too_old else "размер"

    ts_label = time.strftime("%Y%m%d_%H%M%S", time.gmtime(now_ms / 1000.0))
    archive = ml_dir / f"market_journal_{ts_label}.jsonl"
    path.replace(archive)
    _prune_archives(ml_dir)
    _save_rotate_stamp(root, now_ms)
    note = {
        "ts": now_ms,
        "kind": "info",
        "message": f"журнал ротация: архив {archive.name} ({reason})",
    }
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(note, ensure_ascii=False) + "\n")
    return archive


def append_market_journal(
    project_root: str | Path,
    message: str,
    *,
    kind: str | None = None,
    reason: str | None = None,
    bar_ts: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    extras: dict[str, Any] | None = None,
) -> Path:
    """Append one Market log line (rotates weekly/size first). Returns journal path.

    Structured fields (``reason``, ``bar_ts``, ``symbol``, ``market``, …) sit beside
    ``message`` for filters/scripts — UI still shows the text line.
    """
    maybe_rotate_market_journal(project_root)
    path = market_journal_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "ts": int(time.time() * 1000),
        "kind": (kind or "info").strip() or "info",
        "message": str(message or ""),
    }
    if reason is not None and str(reason).strip():
        row["reason"] = str(reason).strip()
    if bar_ts is not None:
        try:
            row["bar_ts"] = int(bar_ts)
        except (TypeError, ValueError):
            pass
    if symbol is not None and str(symbol).strip():
        row["symbol"] = str(symbol).strip().upper()
    if market is not None and str(market).strip():
        row["market"] = str(market).strip().lower()
    if extras:
        reserved = {"ts", "kind", "message", "reason", "bar_ts", "symbol", "market"}
        for key, val in extras.items():
            if key in reserved or val is None or val == "":
                continue
            row[str(key)] = val
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def journal_fields_from_event(event: dict[str, Any]) -> dict[str, Any]:
    """Pick structured keys from a live_paper event for journal persistence."""
    out: dict[str, Any] = {}
    reason = event.get("reason") or event.get("exit_reason")
    if reason is not None and str(reason).strip():
        out["reason"] = str(reason).strip()
    bar_ts = event.get("bar_ts") or event.get("exit_ts") or event.get("entry_ts")
    if bar_ts is not None:
        try:
            out["bar_ts"] = int(bar_ts)
        except (TypeError, ValueError):
            pass
    for key in (
        "symbol",
        "market",
        "action",
        "correct",
        "edge",
        "pnl_usdt",
        "fee",
        "fee_source",
        "entry_fee",
        "exit_fee",
        "entry_liquidity",
        "exit_liquidity",
        "entry_style",
        "fill_leg",
        "exit_reason",
        "utc_hour",
    ):
        if key in event and event.get(key) is not None and event.get(key) != "":
            out[key] = event[key]
    return out


def load_market_journal(
    project_root: str | Path,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load journal rows (optionally last ``limit`` lines)."""
    rows = read_jsonl_rows(market_journal_path(project_root))
    if limit is not None and int(limit) > 0:
        return rows[-int(limit) :]
    return rows
