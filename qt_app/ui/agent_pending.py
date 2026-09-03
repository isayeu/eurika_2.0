"""Pure helpers for Qt local-agent HITL (pendingToolCalls)."""

from __future__ import annotations

from typing import Any


_GIT_TOOLS = frozenset({"git_commit", "git_push"})
_SIDE_EFFECT_TOOLS = frozenset({"git_commit", "git_push", "tests"})


def wants_local_agent(message: str) -> bool:
    """Route implement/fix requests to the Desktop coding-agent loop."""
    from eurika.agent.local_runtime_chat import _wants_code_mutation

    return _wants_code_mutation([{"role": "user", "content": message}])


def first_side_effect_call(pending_tool_calls: Any) -> dict[str, Any] | None:
    if not isinstance(pending_tool_calls, list):
        return None
    for item in pending_tool_calls:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "")
        if tool in _SIDE_EFFECT_TOOLS:
            return item
    return None


def first_edit_proposal_call(pending_tool_calls: Any) -> dict[str, Any] | None:
    if not isinstance(pending_tool_calls, list):
        return None
    for item in pending_tool_calls:
        if not isinstance(item, dict):
            continue
        if str(item.get("tool") or "") != "edit":
            continue
        proposal = item.get("proposal")
        if isinstance(proposal, dict) and proposal.get("proposalId"):
            return item
    return None


def first_pending_hitl_call(pending_tool_calls: Any) -> dict[str, Any] | None:
    return first_side_effect_call(pending_tool_calls) or first_edit_proposal_call(
        pending_tool_calls
    )


def proposal_paths(call: dict[str, Any]) -> list[str]:
    proposal = call.get("proposal") if isinstance(call.get("proposal"), dict) else {}
    files = proposal.get("files") if isinstance(proposal, dict) else None
    paths: list[str] = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item["path"]))
            elif isinstance(item, str) and item.strip():
                paths.append(item)
    return paths


def format_proposal_preview(files: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip() or "(unknown)"
        created = bool(item.get("created"))
        deleted = bool(item.get("deleted"))
        flag = "created" if created else "deleted" if deleted else "modified"
        parts.append(f"--- {path} ({flag})")
        before = item.get("before")
        after = item.get("after")
        if isinstance(before, str) and before:
            parts.append("before:")
            parts.append(before.rstrip()[:4000])
        if isinstance(after, str) and after:
            parts.append("after:")
            parts.append(after.rstrip()[:4000])
        parts.append("")
    return "\n".join(parts).strip()


def approval_button_label(tool: str) -> str:
    if tool == "git_commit":
        return "Commit"
    if tool == "git_push":
        return "Push"
    if tool == "tests":
        return "Run tests"
    return "Apply"


def approval_details(call: dict[str, Any]) -> str:
    tool = str(call.get("tool") or "")
    arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
    if tool == "git_commit":
        message = str(arguments.get("message") or "").strip() or "(empty message)"
        raw_paths = arguments.get("paths")
        paths = [str(item) for item in raw_paths] if isinstance(raw_paths, list) else []
        listed = ", ".join(paths) if paths else "(safe dirty files)"
        return f"message: {message}\npaths: {listed}"
    if tool == "git_push":
        return "Push current branch to origin.\nNever --force / --force-with-lease."
    if tool == "edit":
        paths = proposal_paths(call)
        return "Proposed files: " + (", ".join(paths) if paths else "(none)")
    return ""


def with_approval(arguments: Any) -> dict[str, Any]:
    payload = dict(arguments) if isinstance(arguments, dict) else {}
    payload["approval"] = True
    return payload


def is_git_tool(tool: str) -> bool:
    return tool in _GIT_TOOLS
