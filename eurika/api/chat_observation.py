"""CR-H1: one workspace observation for Chat and the coding-agent.

Both ``chat_send`` and ``session/chat`` must see the same scene: Terminal
pane, last_check (with stale), last user command, short git hint.
Successful mypy on disk must not look like the current release-check pane.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from eurika.api.chat_utils import looks_like_quality_check_output, quality_check_succeeded
from eurika.api.last_check import (
    LAST_CHECK_LOG,
    PREVIEW_CAP,
    attach_last_check_context,
    count_diagnostics,
    last_check_files,
    load_last_check_meta,
    maybe_seal_terminal_quality_check,
    quality_check_runner,
)

TERMINAL_CAP = 12_000
GIT_HINT_LINES = 16


def last_user_cmd(terminal: str, fallback: str = "") -> str:
    """Last ``$ cmd`` line from the Terminal pane."""
    found = ""
    for line in (terminal or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("$ ") and len(stripped) > 2:
            cmd = stripped[2:].strip()
            if cmd and cmd != "$":
                found = cmd
    return found or (fallback or "").strip()


def _git_hint(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "status", "-sb"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    return "\n".join(lines[:GIT_HINT_LINES])


def last_check_is_stale(terminal: str, meta: Optional[Dict[str, Any]], preview: str) -> tuple[bool, str]:
    """True when the pane is a different quality-check than ``last_check`` on disk."""
    if not meta:
        return False, ""
    pane = (terminal or "").strip()
    if not pane or not looks_like_quality_check_output(pane):
        return False, ""
    cmd = last_user_cmd(pane)
    pane_runner = quality_check_runner(cmd, pane)
    check_runner = str(meta.get("runner") or "").strip() or quality_check_runner(
        str(meta.get("command") or ""), preview
    )
    if (
        pane_runner
        and check_runner
        and pane_runner != "check"
        and check_runner != "check"
        and pane_runner != check_runner
    ):
        return True, f"pane={pane_runner} last_check={check_runner}"
    pane_ok = quality_check_succeeded(pane)
    if bool(meta.get("ok")) != pane_ok:
        return True, "pane outcome differs from last_check"
    return False, ""


def _disk_last_check(root: Path) -> tuple[Optional[Dict[str, Any]], str]:
    context = attach_last_check_context(root, {})
    check = context.get("lastCheck")
    if not isinstance(check, dict):
        return None, ""
    return check, str(check.get("outputPreview") or "")


def _last_check_from_terminal(terminal: str, command: str) -> Dict[str, Any]:
    preview = (terminal or "")[:PREVIEW_CAP]
    ok = quality_check_succeeded(terminal)
    return {
        "ok": ok,
        "runner": quality_check_runner(command, terminal),
        "command": command,
        "exitCode": 0 if ok else 1,
        "errorCount": count_diagnostics(terminal),
        "logPath": LAST_CHECK_LOG,
        "outputPreview": preview,
        "files": last_check_files(preview),
        "source": "terminal",
    }


def build_workspace_observation(
    root: Path,
    *,
    terminal_text: Optional[str] = None,
    git: bool = True,
) -> Dict[str, Any]:
    """Assemble the CR-H1 bundle. Does not write disk unless caller reseals."""
    terminal = str(terminal_text or "").strip()[-TERMINAL_CAP:]
    disk, preview = _disk_last_check(root)
    meta = load_last_check_meta(root)
    fallback_cmd = ""
    if disk:
        raw_cmd = disk.get("command")
        fallback_cmd = raw_cmd if isinstance(raw_cmd, str) else ""
    cmd = last_user_cmd(terminal, fallback_cmd)
    stale, reason = last_check_is_stale(terminal, meta, preview)
    if stale and looks_like_quality_check_output(terminal):
        check = _last_check_from_terminal(terminal, cmd)
    elif disk:
        check = dict(disk)
        check.setdefault("source", "disk")
    else:
        check = None
    return {
        "terminal": terminal,
        "lastCheck": check,
        "lastCheckStale": stale,
        "lastCheckStaleReason": reason,
        "lastUserCmd": cmd,
        "gitHint": _git_hint(Path(root)) if git else "",
    }


def maybe_refresh_last_check_from_terminal(root: Path, observation: Dict[str, Any]) -> None:
    """If the pane is a newer quality-check than disk, seal it as last_check."""
    if not observation.get("lastCheckStale"):
        return
    terminal = str(observation.get("terminal") or "")
    command = str(observation.get("lastUserCmd") or "")
    if not command or not looks_like_quality_check_output(terminal):
        return
    raw_check = observation.get("lastCheck")
    check: Dict[str, Any] = raw_check if isinstance(raw_check, dict) else {}
    exit_code = 0 if check.get("ok") else 1
    maybe_seal_terminal_quality_check(
        Path(root),
        command=command,
        output=terminal,
        exit_code=int(exit_code),
    )


def observation_prompt_block(observation: Dict[str, Any]) -> str:
    """Plain-text block for the regular Chat LLM path."""
    lines = ["[Workspace observation]"]
    cmd = str(observation.get("lastUserCmd") or "").strip()
    if cmd:
        lines.append(f"lastUserCmd: {cmd}")
    git_hint = str(observation.get("gitHint") or "").strip()
    if git_hint:
        lines.append("git:")
        lines.append(git_hint)
    check = observation.get("lastCheck") if isinstance(observation.get("lastCheck"), dict) else None
    if check:
        stale = "yes" if observation.get("lastCheckStale") else "no"
        source = check.get("source") or "disk"
        lines.append(
            f"lastCheck stale={stale} source={source} ok={check.get('ok')} "
            f"runner={check.get('runner')} errors={check.get('errorCount')} "
            f"log={check.get('logPath') or LAST_CHECK_LOG}"
        )
        if observation.get("lastCheckStale"):
            reason = str(observation.get("lastCheckStaleReason") or "").strip()
            extra = f" ({reason})" if reason else ""
            lines.append(
                "last_check on disk is NOT this Terminal run — "
                f"prefer [Terminal output]{extra}."
            )
        elif check.get("ok"):
            lines.append(
                "last_check on disk succeeded; do not treat it as current failures."
            )
        else:
            lines.append(
                "last_check FAILED — use that log if the user asks to fix."
            )
    elif observation.get("terminal"):
        lines.append("No last_check on disk; answer from [Terminal output] if present.")
    return "\n".join(lines)


def attach_workspace_observation(
    root: Path,
    context: Dict[str, Any],
    *,
    terminal_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge the bundle into agent EDITOR_CONTEXT."""
    merged = dict(context or {})
    incoming = terminal_text
    if incoming is None:
        incoming = str(merged.get("terminalText") or "")
    obs = build_workspace_observation(root, terminal_text=incoming)
    maybe_refresh_last_check_from_terminal(root, obs)
    merged["terminalText"] = obs["terminal"]
    if obs.get("lastCheck"):
        merged["lastCheck"] = obs["lastCheck"]
    merged["lastCheckStale"] = bool(obs.get("lastCheckStale"))
    merged["lastUserCmd"] = obs.get("lastUserCmd") or ""
    if obs.get("gitHint"):
        merged["gitHint"] = obs["gitHint"]
    merged["observation"] = {
        "lastCheckStale": obs.get("lastCheckStale"),
        "lastCheckStaleReason": obs.get("lastCheckStaleReason"),
        "lastUserCmd": obs.get("lastUserCmd"),
        "source": (obs.get("lastCheck") or {}).get("source") if obs.get("lastCheck") else None,
    }
    return merged
