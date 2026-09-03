"""Queue local-agent edits into Approvals (.eurika/pending_plan.json)."""

from __future__ import annotations

import hashlib
from typing import Any

from eurika.orchestration.team_mode import save_pending_plan

from .proposals import ProposalStore, _digest
from .protocol import ERR_INVALID_PARAMS, ERR_TOOL_FAILED, RpcError


def try_review_in_approvals_call(
    tools: Any,
    session: Any,
    *,
    name: str,
    arguments: dict[str, Any],
    call_id: str,
) -> dict[str, Any] | None:
    """Handle Qt Approvals-mode read overlay, deferred git, and parked edit.

    Returns an observation dict if this path consumed the call.
    Returns None so the chat loop can execute a normal disk read.
    Raises RpcError for bad edit/read overlay.
    """
    if name == "read":
        overlay = overlay_read(tools, session, arguments)
        if overlay is None:
            return None
        return {"callId": call_id, "tool": name, "result": overlay}
    if name in {"git_commit", "git_push"}:
        return {
            "callId": call_id,
            "tool": name,
            "error": "deferredUntilApprovalsApply",
            "hint": (
                "Apply the Approvals plan first; git HITL is after "
                "the patch is on disk."
            ),
        }
    if name == "edit":
        parked = park_edit(tools, session, arguments)
        return {"callId": call_id, "tool": name, "result": parked}
    return None


def park_edit(tools: Any, session: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Compose an edit against the in-memory overlay; do not write the workspace."""
    edits = arguments.get("edits")
    if edits is None:
        edits = [arguments]
    if not isinstance(edits, list) or not edits or not all(isinstance(item, dict) for item in edits):
        raise RpcError(ERR_INVALID_PARAMS, "edits must be a non-empty array of objects")
    paths: list[str] = []
    for item in edits:
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise RpcError(ERR_INVALID_PARAMS, "Every edit requires a workspace-relative path")
        target = tools.resolve(path_value)
        relative = target.relative_to(tools.root).as_posix()
        if relative not in session.staged_before:
            if target.exists() and not target.is_file():
                raise RpcError(ERR_INVALID_PARAMS, f"Edit target is not a file: {relative}")
            try:
                before = target.read_bytes() if target.is_file() else None
                if before is not None:
                    before.decode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise RpcError(ERR_TOOL_FAILED, f"Could not read edit target: {exc}") from exc
            session.staged_before[relative] = before
            session.staged_after[relative] = before
        current = session.staged_after.get(relative)
        expected = item.get("expectedVersion")
        if expected is not None and expected != _digest(current):
            raise RpcError(
                ERR_TOOL_FAILED,
                "File changed since it was read",
                {
                    "path": relative,
                    "expectedVersion": expected,
                    "actualVersion": _digest(current),
                },
            )
        after = ProposalStore._transform(current, item, relative)
        if after is None:
            raise RpcError(
                ERR_INVALID_PARAMS,
                "delete=true is not queued in Approvals; omit delete or use Chat Apply",
            )
        session.staged_after[relative] = after
        paths.append(relative)
    return {"status": "queuedForApprovals", "paths": paths}


def overlay_read(tools: Any, session: Any, args: dict[str, Any]) -> dict[str, Any] | None:
    """Return a synthetic read result from the overlay, or None to hit disk."""
    path_value = args.get("path")
    if not isinstance(path_value, str):
        return None
    target = tools.resolve(path_value)
    relative = target.relative_to(tools.root).as_posix()
    if relative not in session.staged_after:
        return None
    after = session.staged_after[relative]
    if after is None:
        raise RpcError(ERR_TOOL_FAILED, f"Queued delete for {relative}")
    try:
        text = after.decode("utf-8")
    except UnicodeError as exc:
        raise RpcError(ERR_TOOL_FAILED, f"Could not read UTF-8 overlay: {exc}") from exc
    lines = text.splitlines(keepends=True)
    start = max(1, int(args.get("startLine", 1)))
    end = min(len(lines), int(args.get("endLine", len(lines))))
    content = "".join(lines[start - 1 : end]) if end >= start else ""
    return {
        "path": relative,
        "content": content,
        "startLine": start,
        "endLine": end,
        "totalLines": len(lines),
        "version": hashlib.sha256(after).hexdigest(),
        "overlay": True,
    }


def flush_agent_pending_plan(root: Any, session: Any) -> int:
    """Write composed overlay files to pending_plan.json. Returns operation count."""
    operations: list[dict[str, Any]] = []
    for relative, after in list(session.staged_after.items()):
        before = session.staged_before.get(relative)
        if after is None or after == (before or b""):
            continue
        try:
            new_content = after.decode("utf-8")
        except UnicodeError:
            continue
        operations.append(
            {
                "target_file": relative,
                "kind": "agent_edit",
                "risk": "medium",
                "explainability": {"risk": "medium", "source": "local-agent"},
                "params": {"new_content": new_content},
                "critic_verdict": "allow",
            }
        )
    session.staged_before.clear()
    session.staged_after.clear()
    if not operations:
        return 0
    save_pending_plan(
        root,
        {
            "source": "local-agent",
            "summary": f"{len(operations)} file(s) from Chat agent",
        },
        operations,
        [],
        session_id=getattr(session, "id", None),
    )
    return len(operations)


def with_approvals_ready(text: str, n_ops: int) -> str:
    if n_ops <= 0:
        return text
    footer = (
        f"Готово: {n_ops} файл(ов) в плане. Approvals → Load pending plan → "
        "просмотр diff → Approve → Save → Run apply-approved."
    )
    lowered = text.lower()
    if "load pending plan" in lowered:
        return text.strip() or footer
    if text.strip():
        return text.rstrip() + "\n\n" + footer
    return footer
