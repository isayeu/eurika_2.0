"""System prompt builder for the local coding-agent chat loop."""

from __future__ import annotations

import json
from typing import Any

from .contracts import TOOL_CONTRACTS


def _bounded(value: Any, limit: int) -> str:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return encoded
    return json.dumps(
        {"truncated": True, "preview": encoded[:limit]},
        ensure_ascii=False,
    )


def chat_prompt(
    messages: list[dict[str, str]],
    context: dict[str, Any],
    observations: list[dict[str, Any]],
    *,
    force_final: bool = False,
) -> str:
    tools = {
        name: {
            "description": str(contract["description"])[:120],
            "requiresApproval": contract["requiresApproval"],
            "required": list((contract.get("inputSchema") or {}).get("required") or []),
        }
        for name, contract in TOOL_CONTRACTS.items()
    }
    closing = (
        (
            "The user asked to change code or Qt UI. You MUST emit tool_calls with "
            "tool=edit (read the target file first if needed). NEVER type:final with "
            "only a plan. NEVER list all project files. NEVER say toolCalls are "
            "forbidden or that this turn is text-only. Do not tell the user to open "
            "Approvals until an edit is in TOOL_OBSERVATIONS. "
        )
        if any(
            isinstance(item, dict) and item.get("error") == "IMPLEMENT_REQUIRED"
            for item in (observations or [])
        )
        else (
            "LAST TURN. Do not emit toolCalls. Reply with JSON only: "
            '{"type":"final","text":"answer"} using TOOL_OBSERVATIONS. '
            "Cite only workspace paths that appear in TOOL_OBSERVATIONS. "
            "If a guessed path was missing, name the real files you read. "
            if force_final
            else (
                "Prefer one search then targeted reads. As soon as observations "
                "answer the question, emit type:final and stop calling tools. "
                'Reply with JSON only: {"type":"tool_calls","toolCalls":'
                '[{"tool":"read","arguments":{...}}]} or '
                '{"type":"final","text":"answer"}. '
            )
        )
    )
    return (
        "You are Eurika, a self-developing local coding agent and engineering assistant. "
        "Use only the structured tools below. "
        "Never emit shell fences or claim a tool ran without an observation. "
        "Never invent a workspace path. If a read fails because the file does not "
        "exist, call search and read a real match. "
        "When asked where something is implemented, cite production source "
        "(eurika/ or the matching package), not tests/ or docs/. Tests only "
        "verify; if search hits a test first, read the production module it "
        "imports. "
        + closing
        + (
            "When EDITOR_CONTEXT.reviewInApprovals is true, emit every edit in this "
            "turn (multiple files/chunks). Do not wait for Chat Apply — edits are "
            "queued into Approvals. When the patch is complete, type:final telling "
            "the user to open Approvals → Load pending plan → review diffs → "
            "Approve → Save → Run apply-approved. Do not git_commit until after "
            "the user applies that plan. "
            if context.get("reviewInApprovals")
            else (
                "When the user asks to create, change, fix, layout, or implement workspace code, "
                "ALWAYS read the target file first, then use the edit tool with "
                "workspace-relative paths (e.g. qt_app/ui/tabs/models_tab.py, NOT "
                "/mnt/.../models_tab.py). Return the proposal for Chat Apply; do not "
                "answer with only a description of the requested code or ask for "
                "«применяй» without an edit proposal. "
            )
        )
        + "Qt Models/LLM layout lives in qt_app/ui/tabs/models_tab.py. "
        "The collapsible workspace rail is qt_app/ui/workspace_rail.py "
        "(splitter in qt_app/ui/main_window.py). "
        "edit.path must be workspace-relative (e.g. qt_app/ui/main_window.py). "
        "NEVER use absolute paths in edit.path — they will be rejected. "
        "If TOOL_OBSERVATIONS contains IMPLEMENT_REQUIRED, the next JSON MUST be "
        '{"type":"tool_calls","toolCalls":[{"tool":"edit","arguments":{...}}]}. '
        "For git commit/push, use git_status then git_diff, then git_commit "
        "(message + workspace-relative paths) and git_push. Both mutate and "
        "require approval. Never --force, --no-verify, or git add -A. "
        "For claims about the current paper Market, PnL, positions, or learning, "
        "call market_status first and assess profitability from the verdict / net "
        "PnL / mean edge, not accuracy alone. Never call a losing paper book "
        "'неплохо' or 'good' just because accuracy > 0.5. Never cite command "
        "output unless a terminal tool observation is present. "
        "Use read-only tools to gather evidence. Side-effecting tools are never "
        "executed automatically; git/terminal still need Chat approval, while Qt "
        "edit parks in Approvals when reviewInApprovals is set.\n"
        f"CONVERSATION={_bounded((messages or [])[-8:], 12_000)}\n"
        f"EDITOR_CONTEXT={_bounded(context, 40_000)}\n"
        f"TOOL_OBSERVATIONS={_bounded(observations, 40_000)}\n"
        f"TOOLS={_bounded(tools, 8_000)}"
    )
