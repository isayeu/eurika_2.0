"""Idle self-dev: C.14 propose+sandbox when LLM lease is quiet (no cron).

Never applies on main — only parks polygon drills / bug_hunt in Approvals.
Drills: imports → extractable_block → long_function → deep_nesting →
llm_extract → bug_hunt.
Anti-tread uses idle stamp ``drill_ok`` counts (not lifetime learning): skip a
deterministic drill after ≥5 successful idle runs; if ≤1 unsaturated remains,
full round-robin resumes (no one-file loop).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from eurika.orchestration.llm_lease import (
    DEFAULT_QUIET_MS,
    acquire,
    is_idle_for,
    release,
    status as lease_status,
)
from eurika.orchestration.prove_cycle import run_prove_propose

STAMP_NAME = "idle_self_dev.json"
MIN_INTERVAL_MS = 30 * 60 * 1000
IDLE_DRILLS: tuple[str, ...] = (
    "imports",
    "extractable_block",
    "long_function",
    "deep_nesting",
    "llm_extract",
    "bug_hunt",
)
DETERMINISTIC_DRILLS: frozenset[str] = frozenset(
    {"imports", "extractable_block", "long_function", "deep_nesting"}
)
SATURATED_MIN_SUCCESS = 5
HOLDER_PREFIX = "idle_self_dev"
UI_PREFS_NAME = "qt_settings.json"  # shared with Qt shell (~/.eurika/)

# Human-readable step text for Chat live_activity (C.14 polygon drills).
DRILL_SUMMARY: dict[str, str] = {
    "imports": "убрать unused import `os` в eurika/polygon/imports_ok.py",
    "extractable_block": (
        "extract block → helper в eurika/polygon/extractable_block.py"
    ),
    "long_function": "extract nested def в eurika/polygon/long_function.py",
    "deep_nesting": (
        "extract block → helper в eurika/polygon/deep_nesting.py "
        "(polygon_deep_nesting_extractable)"
    ),
    "llm_extract": (
        "llm_extract_block в eurika/polygon/refactor_code_smell_drill.py "
        "(live LLM или synthetic)"
    ),
    "bug_hunt": (
        "один реальный smell → sandbox verify → Approvals "
        "(не polygon; apply только HITL)"
    ),
}


def stamp_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / STAMP_NAME


def ui_prefs_path() -> Path:
    """Shell prefs shared by Qt and Desktop (not workspace-local)."""
    return Path.home() / ".eurika" / UI_PREFS_NAME


def load_ui_prefs() -> dict[str, Any]:
    path = ui_prefs_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_prefs(blob: dict[str, Any]) -> Path:
    path = ui_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def get_idle_prefs() -> dict[str, Any]:
    data = load_ui_prefs()
    return {
        "idle_self_dev": bool(data.get("idle_self_dev", False)),
        "market_llm_learn": bool(data.get("market_llm_learn", False)),
        "market_portfolio_agent": bool(data.get("market_portfolio_agent", False)),
    }


def set_idle_enabled(enabled: bool) -> dict[str, Any]:
    data = load_ui_prefs()
    data["idle_self_dev"] = bool(enabled)
    save_ui_prefs(data)
    return get_idle_prefs()


def load_stamp(project_root: str | Path) -> dict[str, Any]:
    path = stamp_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_stamp(project_root: str | Path, blob: dict[str, Any]) -> Path:
    path = stamp_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(blob)
    payload["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _drill_ok_counts(
    project_root: str | Path | None = None,
    *,
    stamp: dict[str, Any] | None = None,
    ok_counts: dict[str, Any] | None = None,
) -> dict[str, int]:
    if isinstance(ok_counts, dict):
        raw = ok_counts
    else:
        blob = stamp if isinstance(stamp, dict) else None
        if blob is None and project_root is not None:
            blob = load_stamp(project_root)
        raw = blob.get("drill_ok") if isinstance(blob, dict) else {}
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            out[str(key)] = int(value or 0)
        except (TypeError, ValueError):
            continue
    return out


def bump_drill_ok(stamp: dict[str, Any], drill_id: str) -> dict[str, Any]:
    """Return stamp payload with ``drill_ok[drill]`` incremented."""
    drill = str(drill_id or "").strip().lower()
    payload = dict(stamp or {})
    counts = _drill_ok_counts(ok_counts=payload.get("drill_ok"))
    if drill:
        counts[drill] = int(counts.get(drill) or 0) + 1
    payload["drill_ok"] = counts
    return payload


def drill_is_saturated(
    drill_id: str,
    *,
    project_root: str | Path | None = None,
    stamp: dict[str, Any] | None = None,
    ok_counts: dict[str, Any] | None = None,
    min_success: int = SATURATED_MIN_SUCCESS,
    stats: dict[str, Any] | None = None,
) -> bool:
    """True when a deterministic drill has ≥min_success idle successes.

    ``stats`` is accepted for backward-compatible tests but ignored — anti-tread
    is idle-local (``drill_ok`` in stamp), not lifetime learning.
    """
    del stats  # unused — kept for call-site compatibility
    drill = str(drill_id or "").strip().lower()
    if drill not in DETERMINISTIC_DRILLS:
        return False
    counts = _drill_ok_counts(project_root, stamp=stamp, ok_counts=ok_counts)
    return int(counts.get(drill) or 0) >= max(1, int(min_success))


def next_drill(
    last_drill: str | None,
    *,
    project_root: str | Path | None = None,
    stamp: dict[str, Any] | None = None,
    ok_counts: dict[str, Any] | None = None,
    min_success: int = SATURATED_MIN_SUCCESS,
    stats: dict[str, Any] | None = None,
) -> str:
    """Next idle drill after ``last_drill``.

    Prefer unsaturated drills (anti-tread). If ≤1 unsaturated remains,
    fall back to full round-robin so idle does not hammer one file forever.
    """
    del stats
    last = str(last_drill or "").strip().lower()
    if last in IDLE_DRILLS:
        start = (IDLE_DRILLS.index(last) + 1) % len(IDLE_DRILLS)
    else:
        start = 0
    counts = _drill_ok_counts(project_root, stamp=stamp, ok_counts=ok_counts)

    def _sat(drill: str) -> bool:
        return drill_is_saturated(
            drill,
            ok_counts=counts,
            min_success=min_success,
        )

    unsaturated = [d for d in IDLE_DRILLS if not _sat(d)]
    if len(unsaturated) <= 1:
        return IDLE_DRILLS[start]

    for offset in range(len(IDLE_DRILLS)):
        candidate = IDLE_DRILLS[(start + offset) % len(IDLE_DRILLS)]
        if not _sat(candidate):
            return candidate
    return IDLE_DRILLS[start]


def stamp_last_drill(*, attempted: str, ok: bool) -> str | None:
    """Cursor for ``next_drill``: advance only on success; retry same drill on failure."""
    drill = str(attempted or "").strip().lower()
    if ok:
        return drill if drill in IDLE_DRILLS else IDLE_DRILLS[0]
    if drill not in IDLE_DRILLS:
        return None
    idx = IDLE_DRILLS.index(drill)
    if idx == 0:
        return None
    return IDLE_DRILLS[idx - 1]


def is_due(
    project_root: str | Path,
    *,
    now_ms: int | None = None,
    min_interval_ms: int = MIN_INTERVAL_MS,
) -> bool:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    last = load_stamp(project_root).get("last_ms")
    try:
        last_ms = int(last) if last is not None else 0
    except (TypeError, ValueError):
        last_ms = 0
    if last_ms <= 0:
        return True
    return now - last_ms >= max(60_000, int(min_interval_ms))


def pending_has_unresolved(project_root: str | Path) -> bool:
    from eurika.orchestration.team_mode import load_pending_plan

    plan = load_pending_plan(Path(project_root).resolve())
    if not plan:
        return False
    ops = plan.get("operations")
    if not isinstance(ops, list):
        return False
    for op in ops:
        if not isinstance(op, dict):
            continue
        decision = str(op.get("team_decision") or "pending").strip().lower()
        if decision == "pending":
            return True
    return False


def market_wants_llm_soon(
    project_root: str | Path,
    *,
    market_llm_enabled: bool = False,
    portfolio_enabled: bool = False,
    now_ms: int | None = None,
) -> str | None:
    """Return skip reason if an enabled Market LLM cycle is due."""
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    if market_llm_enabled:
        from eurika.ml.cursor_hourly import is_due as hourly_due

        if hourly_due(root, now_ms=now):
            return "market_llm_due"
    if portfolio_enabled:
        from eurika.ml.portfolio_agent import is_due as portfolio_due

        if portfolio_due(root, now_ms=now):
            return "portfolio_due"
    return None


def drill_detail(drill_id: str) -> str:
    drill = str(drill_id or "").strip().lower()
    return DRILL_SUMMARY.get(drill, f"polygon drill `{drill or 'unknown'}`")


def _announce_progress(root: Path, title: str) -> None:
    try:
        from eurika.agent.live_activity import publish_progress

        publish_progress(
            root,
            method="idle_self_dev",
            title=title,
            client="idle_self_dev",
        )
    except Exception:
        pass


def status(
    project_root: str | Path,
    *,
    quiet_ms: int = DEFAULT_QUIET_MS,
    min_interval_ms: int = MIN_INTERVAL_MS,
    now_ms: int | None = None,
    market_llm_enabled: bool = False,
    portfolio_enabled: bool = False,
    market_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    stamp = load_stamp(root)
    lease = lease_status(root, quiet_ms=quiet_ms, now_ms=now)
    yield_root = Path(market_root).resolve() if market_root else root
    yield_reason = market_wants_llm_soon(
        yield_root,
        market_llm_enabled=market_llm_enabled,
        portfolio_enabled=portfolio_enabled,
        now_ms=now,
    )
    return {
        "stamp": stamp,
        "due": is_due(root, now_ms=now, min_interval_ms=min_interval_ms),
        "idle": bool(lease.get("idle")),
        "pending_unresolved": pending_has_unresolved(root),
        "next_drill": next_drill(
            str(stamp.get("last_drill") or ""),
            project_root=root,
            stamp=stamp,
        ),
        "yield_market": yield_reason,
        "lease": lease,
        "quiet_ms": int(quiet_ms),
        "min_interval_ms": int(min_interval_ms),
    }


def maybe_run(
    project_root: str | Path,
    *,
    force: bool = False,
    quiet_ms: int = DEFAULT_QUIET_MS,
    min_interval_ms: int = MIN_INTERVAL_MS,
    now_ms: int | None = None,
    market_llm_enabled: bool = False,
    portfolio_enabled: bool = False,
    market_root: str | Path | None = None,
    keep_sandbox: bool = False,
    run_propose: Any | None = None,
) -> dict[str, Any]:
    """One idle C.14 propose+sandbox step, or a skip dict.

    Never calls ``fix --apply-approved``.
    """
    root = Path(project_root).resolve()
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    base: dict[str, Any] = {
        "ok": True,
        "idle_self_dev": True,
        "skipped": None,
        "drill_id": None,
        "persisted": False,
    }
    if not force and not is_due(root, now_ms=now, min_interval_ms=min_interval_ms):
        return {**base, "skipped": "not_due"}
    if pending_has_unresolved(root):
        return {**base, "skipped": "pending_exists"}
    if not is_idle_for(root, quiet_ms=quiet_ms, now_ms=now):
        return {**base, "skipped": "llm_busy_or_quiet"}
    yield_root = Path(market_root).resolve() if market_root else root
    yield_reason = market_wants_llm_soon(
        yield_root,
        market_llm_enabled=market_llm_enabled,
        portfolio_enabled=portfolio_enabled,
        now_ms=now,
    )
    if yield_reason:
        return {**base, "skipped": yield_reason}

    stamp = load_stamp(root)
    drill_id = next_drill(
        str(stamp.get("last_drill") or ""),
        project_root=root,
        stamp=stamp,
    )
    detail = drill_detail(drill_id)
    holder = f"{HOLDER_PREFIX}:{os.getpid()}"
    got = acquire(
        root,
        holder=holder,
        priority="self_dev",
        purpose="idle_self_dev",
        now_ms=now,
    )
    if not got.get("ok"):
        return {
            **base,
            "skipped": "lease_denied",
            "lease": got,
            "drill_id": drill_id,
        }

    propose_fn = run_propose or run_prove_propose
    publish_done = None
    started: dict[str, Any] | None = None
    try:
        try:
            from eurika.agent.live_activity import publish_done, publish_start

            started = publish_start(
                root,
                method="idle_self_dev",
                params={
                    "drill": drill_id,
                    "sandbox": True,
                    "detail": detail,
                    "message": detail,
                },
                client="idle_self_dev",
            )
        except Exception:
            started = None
            publish_done = None  # type: ignore[assignment]

        _announce_progress(
            root,
            f"саморазвитие: sandbox apply+verify для drill `{drill_id}`…",
        )
        try:
            if run_propose is not None:
                payload = run_propose(
                    root,
                    dry_run=False,
                    drill=drill_id,
                    require_llm=False,
                    sandbox=True,
                    keep_sandbox=keep_sandbox,
                )
            elif drill_id == "bug_hunt":
                from eurika.orchestration.bug_hunt import (
                    bug_hunt_web_enabled,
                    run_bug_hunt_propose,
                )

                payload = run_bug_hunt_propose(
                    root,
                    dry_run=False,
                    sandbox=True,
                    web=True if bug_hunt_web_enabled() else None,
                    keep_sandbox=keep_sandbox,
                )
            else:
                payload = propose_fn(
                    root,
                    dry_run=False,
                    drill=drill_id,
                    require_llm=False,
                    sandbox=True,
                    keep_sandbox=keep_sandbox,
                )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            # Stamp failures too — otherwise Qt retries every quiet window.
            # Keep rotation cursor so the same drill is retried next due window.
            save_stamp(
                root,
                {
                    "last_ms": now,
                    "last_drill": stamp_last_drill(attempted=drill_id, ok=False),
                    "last_ok": False,
                    "last_attempted": drill_id,
                    "drill_ok": _drill_ok_counts(stamp=stamp),
                    "last_result": {"ok": False, "error": err, "sandbox": True},
                },
            )
            message = f"саморазвитие: сбой drill `{drill_id}` — {err}"
            try:
                from eurika.api.chat_context import record_c14_approvals_outcome

                record_c14_approvals_outcome(
                    root,
                    drill=drill_id,
                    target="",
                    ok=False,
                    source="idle_self_dev",
                    error=err,
                )
            except Exception:
                pass
            if started is not None and publish_done is not None:
                try:
                    publish_done(
                        root,
                        started,
                        ok=False,
                        result={"text": message, "approvalsQueued": 0},
                        error=err,
                    )
                except Exception:
                    pass
            return {
                "ok": False,
                "idle_self_dev": True,
                "skipped": None,
                "drill_id": drill_id,
                "message": message,
                "kind": "idle_self_dev",
                "error": err,
                "persisted": True,
                "approvalsQueued": 0,
            }

        ok = bool(payload.get("ok", True)) and not payload.get("error")
        target = str(payload.get("target_file") or "").strip()
        sandbox_mode = str(payload.get("sandbox_mode") or "").strip()
        queued = 1 if ok and payload.get("pending_plan") else 0
        if ok and queued:
            message = (
                f"саморазвитие: drill `{drill_id}` — {detail}"
                + (f" → Approvals ({target})" if target else " → Approvals")
                + (f"; sandbox={sandbox_mode}" if sandbox_mode else "")
            )
        elif ok:
            message = f"саморазвитие: drill `{drill_id}` ok, но pending_plan не записан"
        else:
            message = (
                f"саморазвитие: drill `{drill_id}` не прошёл"
                + (f" — {payload.get('error')}" if payload.get("error") else "")
            )
        result = {
            "ok": ok,
            "idle_self_dev": True,
            "skipped": None,
            "drill_id": drill_id,
            "message": message,
            "kind": "idle_self_dev",
            "propose": payload,
            "pending_plan": payload.get("pending_plan"),
            "persisted": True,
            "approvalsQueued": queued,
        }
        stamp_payload: dict[str, Any] = {
            "last_ms": now,
            "last_drill": stamp_last_drill(attempted=drill_id, ok=ok),
            "last_ok": ok,
            "last_attempted": drill_id,
            "drill_ok": _drill_ok_counts(stamp=stamp),
            "last_result": {
                "ok": ok,
                "pending_plan": payload.get("pending_plan"),
                "error": payload.get("error"),
                "sandbox": payload.get("sandbox"),
                "target_file": target or None,
                "sandbox_mode": sandbox_mode or None,
            },
        }
        if ok:
            stamp_payload = bump_drill_ok(stamp_payload, drill_id)
        save_stamp(root, stamp_payload)
        try:
            from eurika.api.chat_context import record_c14_approvals_outcome

            record_c14_approvals_outcome(
                root,
                drill=drill_id,
                target=target,
                ok=ok,
                source="idle_self_dev",
                error=None if ok else str(payload.get("error") or ""),
            )
        except Exception:
            pass
        if started is not None and publish_done is not None:
            try:
                publish_done(
                    root,
                    started,
                    ok=ok,
                    result={
                        "text": message,
                        "approvalsQueued": result["approvalsQueued"],
                    },
                    error=None if ok else str(payload.get("error") or "propose failed"),
                )
            except Exception:
                pass
        return result
    finally:
        release(root, holder=holder, now_ms=now)
