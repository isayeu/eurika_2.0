"""Campaign checkpoint storage and undo helpers (ROADMAP 3.6.4)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


def _checkpoints_dir(project_root: Path) -> Path:
    root = Path(project_root).resolve()
    return root / ".eurika" / "campaign_checkpoints"


def _checkpoint_path(project_root: Path, checkpoint_id: str) -> Path:
    return _checkpoints_dir(project_root) / f"{checkpoint_id}.json"


def _now_ts() -> float:
    return float(time.time())


def _new_checkpoint_id() -> str:
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{int((time.time() % 1) * 1000):03d}"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _latest_checkpoint_path_for_session(project_root: Path, session_id: str) -> Path | None:
    base = _checkpoints_dir(project_root)
    if not base.exists():
        return None
    for p in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        data = _load_json(p) or {}
        if str(data.get("session_id") or "") != session_id:
            continue
        if str(data.get("status") or "") == "undone":
            continue
        return p
    return None


def create_campaign_checkpoint(
    project_root: Path,
    *,
    operations: list[dict[str, Any]],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Create checkpoint before apply stage and persist metadata."""
    if session_id:
        existing_path = _latest_checkpoint_path_for_session(project_root, session_id)
        if existing_path is not None:
            existing = _load_json(existing_path) or {}
            existing["updated_at"] = _now_ts()
            existing["status"] = "active"
            existing["operations_total"] = int(existing.get("operations_total") or 0) + len(operations)
            existing["targets"] = list(
                dict.fromkeys(
                    [str(x) for x in (existing.get("targets") or []) if str(x)]
                    + [
                        str(op.get("target_file") or "")
                        for op in operations
                        if str(op.get("target_file") or "")
                    ]
                )
            )
            existing["reused"] = True
            _save_json(existing_path, existing)
            return existing

    checkpoint_id = _new_checkpoint_id()
    payload: dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "created_at": _now_ts(),
        "session_id": session_id,
        "status": "pending",
        "run_ids": [],
        "operations_total": len(operations),
        "targets": [
            str(op.get("target_file") or "")
            for op in operations
            if str(op.get("target_file") or "")
        ],
        "reused": False,
    }
    _save_json(_checkpoint_path(project_root, checkpoint_id), payload)
    return payload


def attach_run_to_checkpoint(
    project_root: Path,
    checkpoint_id: str,
    *,
    run_id: str | None,
    verify_success: bool | None,
    modified: list[str] | None,
) -> dict[str, Any] | None:
    """Attach run metadata after apply to an existing campaign checkpoint."""
    if not checkpoint_id:
        return None
    path = _checkpoint_path(project_root, checkpoint_id)
    data = _load_json(path)
    if not data:
        return None
    run_ids = list(data.get("run_ids") or [])
    if run_id and run_id not in run_ids:
        run_ids.append(run_id)
    data["run_ids"] = run_ids
    data["verify_success"] = verify_success
    data["modified_count"] = len(modified or [])
    data["updated_at"] = _now_ts()
    data["status"] = "completed"
    _save_json(path, data)
    return data


def list_campaign_checkpoints(project_root: Path, *, limit: int = 20) -> dict[str, Any]:
    """List recent campaign checkpoints."""
    base = _checkpoints_dir(project_root)
    if not base.exists():
        return {"checkpoints": [], "path": str(base)}
    rows: list[dict[str, Any]] = []
    for p in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        data = _load_json(p) or {}
        rows.append(
            {
                "checkpoint_id": str(data.get("checkpoint_id") or p.stem),
                "status": str(data.get("status") or "unknown"),
                "run_ids": list(data.get("run_ids") or []),
                "operations_total": int(data.get("operations_total") or 0),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
        )
        if len(rows) >= limit:
            break
    return {"checkpoints": rows, "path": str(base)}


def latest_campaign_checkpoint(project_root: Path) -> dict[str, Any] | None:
    """Return latest checkpoint summary or None."""
    info = list_campaign_checkpoints(project_root, limit=1)
    rows = info.get("checkpoints") or []
    if not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    return row


def undo_campaign_checkpoint(
    project_root: Path,
    *,
    checkpoint_id: str | None = None,
    rollback_fn: Callable[[Path, str | None], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rollback all runs from a campaign checkpoint in reverse order."""
    root = Path(project_root).resolve()
    base = _checkpoints_dir(root)
    if not base.exists():
        return {"errors": [f"Checkpoint dir not found: {base}"], "checkpoint_id": checkpoint_id}

    selected: Path | None = None
    if checkpoint_id:
        p = _checkpoint_path(root, checkpoint_id)
        if p.exists():
            selected = p
    else:
        files = sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if files:
            selected = files[0]
    if selected is None:
        return {"errors": [f"Checkpoint not found: {checkpoint_id or 'latest'}"], "checkpoint_id": checkpoint_id}

    data = _load_json(selected) or {}
    cid = str(data.get("checkpoint_id") or selected.stem)
    run_ids = [str(x) for x in (data.get("run_ids") or []) if str(x)]
    if rollback_fn is None:
        from patch_engine import rollback_patch

        rollback_fn = rollback_patch

    restored: list[str] = []
    errors: list[str] = []
    rollback_reports: list[dict[str, Any]] = []
    for run_id in reversed(run_ids):
        rr = rollback_fn(root, run_id)
        rollback_reports.append({"run_id": run_id, "report": rr})
        restored.extend([str(x) for x in (rr.get("restored") or [])])
        errors.extend([str(x) for x in (rr.get("errors") or [])])

    data["status"] = "undone" if run_ids else "noop"
    data["undone_at"] = _now_ts()
    _save_json(selected, data)
    return {
        "checkpoint_id": cid,
        "run_ids": run_ids,
        "restored": restored,
        "errors": errors,
        "status": data["status"],
        "rollback_reports": rollback_reports,
    }
