"""Shared LLM / Cursor lease so Market/Chat preempt idle self-dev.

File: ``.eurika/llm_lease.json``. Priorities: interactive > market > self_dev.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

LeasePriority = Literal["interactive", "market", "self_dev"]

LEASE_NAME = "llm_lease.json"
LOCK_NAME = "llm_lease.lock"
DEFAULT_TTL_MS = 10 * 60 * 1000
DEFAULT_QUIET_MS = 3 * 60 * 1000

PRIORITY_RANK: dict[str, int] = {
    "self_dev": 1,
    "market": 2,
    "interactive": 3,
}


def lease_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / LEASE_NAME


def _lock_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / LOCK_NAME


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rank(priority: str) -> int:
    return int(PRIORITY_RANK.get(str(priority or "").strip().lower(), 0))


def _read_unlocked(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_unlocked(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = dict(data)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _with_lock(project_root: str | Path, fn: Any) -> Any:
    root = Path(project_root).resolve()
    lock = _lock_path(root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            return fn()
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def _is_live(blob: dict[str, Any], *, now_ms: int) -> bool:
    holder = str(blob.get("holder") or "").strip()
    if not holder:
        return False
    try:
        heartbeat = int(blob.get("heartbeat_ms") or blob.get("acquired_ms") or 0)
    except (TypeError, ValueError):
        heartbeat = 0
    try:
        ttl = int(blob.get("ttl_ms") or DEFAULT_TTL_MS)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL_MS
    if heartbeat <= 0:
        return False
    return now_ms - heartbeat <= max(1_000, ttl)


def load_lease(project_root: str | Path) -> dict[str, Any]:
    return _read_unlocked(lease_path(project_root))


def acquire(
    project_root: str | Path,
    *,
    holder: str,
    priority: LeasePriority | str,
    purpose: str = "",
    ttl_ms: int = DEFAULT_TTL_MS,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Try to take the lease. Returns ``{ok, reason?, lease}``."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else _now_ms())
    want_holder = str(holder or "").strip() or f"pid:{os.getpid()}"
    want_prio = str(priority or "interactive").strip().lower()
    if want_prio not in PRIORITY_RANK:
        want_prio = "interactive"
    want_rank = _rank(want_prio)

    def _do() -> dict[str, Any]:
        path = lease_path(root)
        cur = _read_unlocked(path)
        last_released = cur.get("last_released_ms")
        live = _is_live(cur, now_ms=now)
        if live:
            cur_holder = str(cur.get("holder") or "")
            cur_rank = _rank(str(cur.get("priority") or ""))
            if cur_holder == want_holder:
                cur["heartbeat_ms"] = now
                cur["ttl_ms"] = int(ttl_ms)
                cur["purpose"] = str(purpose or cur.get("purpose") or "")
                _write_unlocked(path, cur)
                return {"ok": True, "renewed": True, "lease": dict(cur)}
            if cur_rank >= want_rank:
                return {
                    "ok": False,
                    "reason": "busy",
                    "holder": cur_holder,
                    "priority": cur.get("priority"),
                    "purpose": cur.get("purpose"),
                    "lease": dict(cur),
                }
        lease = {
            "holder": want_holder,
            "priority": want_prio,
            "purpose": str(purpose or ""),
            "pid": os.getpid(),
            "acquired_ms": now,
            "heartbeat_ms": now,
            "ttl_ms": int(ttl_ms),
        }
        if last_released is not None:
            lease["last_released_ms"] = last_released
        _write_unlocked(path, lease)
        return {"ok": True, "renewed": False, "lease": dict(lease)}

    return _with_lock(root, _do)


def release(
    project_root: str | Path,
    *,
    holder: str | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Release if ``holder`` matches (or holder is None = force clear live fields)."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else _now_ms())
    want = str(holder or "").strip()

    def _do() -> dict[str, Any]:
        path = lease_path(root)
        cur = _read_unlocked(path)
        if want and str(cur.get("holder") or "") not in {"", want}:
            return {"ok": False, "reason": "not_holder", "lease": dict(cur)}
        out = {
            "holder": "",
            "priority": "",
            "purpose": "",
            "pid": None,
            "acquired_ms": None,
            "heartbeat_ms": None,
            "ttl_ms": None,
            "last_released_ms": now,
        }
        _write_unlocked(path, out)
        return {"ok": True, "lease": dict(out)}

    return _with_lock(root, _do)


def heartbeat(
    project_root: str | Path,
    *,
    holder: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else _now_ms())
    want = str(holder or "").strip()

    def _do() -> dict[str, Any]:
        path = lease_path(root)
        cur = _read_unlocked(path)
        if str(cur.get("holder") or "") != want:
            return {"ok": False, "reason": "not_holder", "lease": dict(cur)}
        cur["heartbeat_ms"] = now
        _write_unlocked(path, cur)
        return {"ok": True, "lease": dict(cur)}

    return _with_lock(root, _do)


def is_idle_for(
    project_root: str | Path,
    *,
    quiet_ms: int = DEFAULT_QUIET_MS,
    now_ms: int | None = None,
) -> bool:
    """True when no live lease and quiet period since last release elapsed."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else _now_ms())
    cur = load_lease(root)
    if _is_live(cur, now_ms=now):
        return False
    try:
        last = int(cur.get("last_released_ms") or 0)
    except (TypeError, ValueError):
        last = 0
    if last <= 0:
        return True
    return now - last >= max(0, int(quiet_ms))


def status(
    project_root: str | Path,
    *,
    quiet_ms: int = DEFAULT_QUIET_MS,
    now_ms: int | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else _now_ms())
    cur = load_lease(root)
    live = _is_live(cur, now_ms=now)
    return {
        "live": live,
        "idle": is_idle_for(root, quiet_ms=quiet_ms, now_ms=now),
        "quiet_ms": int(quiet_ms),
        "lease": dict(cur),
        "now_ms": now,
    }
