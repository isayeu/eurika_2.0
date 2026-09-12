"""Persist the last Chat quality-check so a follow-up can see the real log.

Cursor-like: run mypy/ruff/pytest → store full output → «исправь ошибки»
reads that log, not the truncated Chat bubble.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

LAST_CHECK_LOG = ".eurika/last_check.log"
LAST_CHECK_META = ".eurika/last_check.json"
LOG_CAP = 400_000
CHAT_OUTPUT_CAP = 4000
PREVIEW_CAP = 2000


def _command_text(command: object) -> str:
    if isinstance(command, list) and command:
        return " ".join(str(part) for part in command)
    if isinstance(command, str):
        return command.strip()
    return ""


def last_check_files(output: str) -> list[str]:
    """Workspace-relative files named in a mypy/ruff/pytest log."""
    found: list[str] = []
    seen: set[str] = set()
    for line in (output or "").splitlines():
        if ": error:" not in line and ": error " not in line and not line.startswith("FAILED "):
            continue
        raw = line.split(":", 1)[0].strip()
        if line.startswith("FAILED "):
            raw = line[7:].split("::", 1)[0].strip()
        path = raw.replace("\\", "/").lstrip("./")
        if not path or path in seen:
            continue
        if "/" not in path and not path.endswith(".py"):
            continue
        seen.add(path)
        found.append(path)
    return found


def count_diagnostics(output: str) -> int:
    text = output or ""
    found = re.search(r"Found (\d+) errors?\b", text)
    if found:
        return int(found.group(1))
    n = 0
    for line in text.splitlines():
        if ": error:" in line or ": error " in line:
            n += 1
        elif line.startswith("FAILED ") or line.startswith("E   "):
            n += 1
    return n


def persist_last_check(root: Path, verification: Dict[str, Any]) -> Dict[str, Any]:
    """Write full check output. Returns compact meta merged into verification."""
    if not isinstance(verification, dict):
        return {}
    output = str(verification.get("output") or verification.get("error") or "")
    command = verification.get("command")
    runner = str(verification.get("runner") or "").strip()
    if not output and not command and not runner:
        return {}
    eurika = Path(root) / ".eurika"
    try:
        eurika.mkdir(parents=True, exist_ok=True)
        log_text = output[:LOG_CAP]
        (eurika / "last_check.log").write_text(log_text, encoding="utf-8")
        meta = {
            "ok": bool(verification.get("ok")),
            "runner": runner,
            "command": command if isinstance(command, list) else _command_text(command),
            "exit_code": verification.get("exit_code"),
            "error_count": count_diagnostics(output),
            "log_path": LAST_CHECK_LOG,
            "output_chars": len(output),
        }
        (eurika / "last_check.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return {}
    extras = {
        "log_path": LAST_CHECK_LOG,
        "error_count": meta["error_count"],
        "output_chars": len(output),
        "output_truncated": len(output) > CHAT_OUTPUT_CAP,
    }
    return extras


_QUALITY_CMD_RE = re.compile(
    r"(?:release_check(?:\.sh)?|(?:^|[/\s.])pytest(?:\s|$)|(?:^|[/\s.])mypy(?:\s|$)|(?:^|[/\s.])ruff(?:\s|$))",
    re.I,
)


def looks_like_quality_check_command(command: str) -> bool:
    return bool(_QUALITY_CMD_RE.search(command or ""))


def quality_check_runner(command: str, output: str = "") -> str:
    blob = f"{command}\n{output}".lower()
    if "release_check" in blob:
        return "release_check"
    if "pytest" in blob:
        return "pytest"
    if "mypy" in blob:
        return "mypy"
    if "ruff" in blob:
        return "ruff"
    return "check"


def maybe_seal_terminal_quality_check(
    root: Path,
    *,
    command: str,
    output: str,
    exit_code: int,
) -> Optional[Dict[str, Any]]:
    """Persist Terminal/Commands quality-check output as last_check.

    Typed ``./scripts/release_check.sh`` / pytest / mypy / ruff must land in
    ``.eurika/last_check.log`` the same way Chat ``release_check`` does.
    """
    cmd = (command or "").strip()
    if not looks_like_quality_check_command(cmd):
        return None
    text = output or ""
    ok = int(exit_code or 0) == 0
    try:
        from eurika.api.chat_utils import quality_check_succeeded

        if text.strip():
            ok = ok and quality_check_succeeded(text)
    except Exception:
        pass
    return seal_check_verification(
        root,
        {
            "ok": ok,
            "runner": quality_check_runner(cmd, text),
            "command": cmd,
            "exit_code": exit_code,
            "output": text,
        },
    )


def seal_check_verification(root: Path, verification: Dict[str, Any]) -> Dict[str, Any]:
    """Persist the full log, then cap ``output`` for Chat / Terminal mirror."""
    out = dict(verification)
    raw = str(out.get("output") or "")
    extras = persist_last_check(root, out)
    out.update(extras)
    if len(raw) > CHAT_OUTPUT_CAP:
        out["output"] = raw[:CHAT_OUTPUT_CAP]
        out["output_truncated"] = True
    return out


def load_last_check_meta(root: Path) -> Optional[Dict[str, Any]]:
    path = Path(root) / LAST_CHECK_META
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def attach_last_check_context(root: Path, context: Dict[str, Any]) -> Dict[str, Any]:
    """Put lastCheck into agent EDITOR_CONTEXT. Does not overwrite an explicit one."""
    merged = dict(context or {})
    if merged.get("lastCheck"):
        return merged
    meta = load_last_check_meta(root)
    if not meta:
        return merged
    preview = ""
    log_path = Path(root) / LAST_CHECK_LOG
    try:
        preview = log_path.read_text(encoding="utf-8")[:PREVIEW_CAP]
    except OSError:
        preview = ""
    merged["lastCheck"] = {
        "ok": bool(meta.get("ok")),
        "runner": meta.get("runner") or "",
        "command": meta.get("command"),
        "exitCode": meta.get("exit_code"),
        "errorCount": meta.get("error_count") or 0,
        "logPath": LAST_CHECK_LOG,
        "outputPreview": preview,
        "files": last_check_files(preview),
    }
    return merged


def last_check_is_the_task(message: str) -> bool:
    """True only when the user asked to fix the sealed check — not docs/plan."""
    raw = (message or "").strip()
    if not raw:
        return False
    return bool(
        re.search(
            r"(?is)исправ|поправ|пофикси|fix\s+the|fix\s+(?:error|mypy|ruff)",
            raw,
        )
    )


def docs_plan_is_the_task(message: str) -> bool:
    """True when the user asked about docs / backlog / what is next."""
    if last_check_is_the_task(message):
        return False
    raw = (message or "").strip()
    if not raw:
        return False
    return bool(
        re.search(
            r"(?is)документ|docs/|VISION|ROADMAP|DEVELOPMENT|"
            r"бэклог|backlog|"
            r"что\s+(?:дальше|далее)|следующ\w*\s+шаг|"
            r"текущ\w*\s+фокус|по\s+плану|"
            r"какие\s+план|план\w*.{0,40}развит",
            raw,
        )
    )


def last_check_observation(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Synthetic tool observation: previous Chat check, like a prior tool result."""
    check = context.get("lastCheck") if isinstance(context, dict) else None
    if not isinstance(check, dict):
        return None
    if check.get("ok"):
        return None
    files = check.get("files")
    if not isinstance(files, list):
        files = last_check_files(str(check.get("outputPreview") or ""))
    return {
        "tool": "last_check",
        "path": check.get("logPath") or LAST_CHECK_LOG,
        "result": {
            "ok": False,
            "runner": check.get("runner"),
            "command": check.get("command"),
            "exitCode": check.get("exitCode"),
            "errorCount": check.get("errorCount"),
            "preview": check.get("outputPreview") or "",
            "paths": [p for p in files if isinstance(p, str)],
            "source": check.get("source") or "disk",
            "note": (
                "Previous Chat quality-check failed. Read logPath for the full log. "
                "Fix only those diagnostics with surgical edits "
                "(oldText/newText around the failing lines). "
                "Do not rewrite whole files or invent extra refactors. "
                "Emit tool=edit for those files — do not type:final with only a file list. "
                "If errorCount is large, keep editing until every file in the log "
                "is addressed, or name the remaining files in type:final — "
                "do not stop after the first few."
                + (
                    " lastCheck came from the Terminal pane, not a stale disk log."
                    if check.get("source") == "terminal"
                    else ""
                )
            ),
        },
    }


def last_check_prompt_block(root: Path) -> str:
    """Short block for the regular Chat LLM path (same last check)."""
    meta = load_last_check_meta(root)
    if not meta or meta.get("ok"):
        return ""
    runner = str(meta.get("runner") or "check")
    count = int(meta.get("error_count") or 0)
    cmd = meta.get("command")
    cmd_text = _command_text(cmd) if not isinstance(cmd, str) else cmd
    lines = [
        f"[Last check FAILED] runner={runner} errors={count} log={LAST_CHECK_LOG}",
    ]
    if cmd_text:
        lines.append(f"$ {cmd_text}")
    return "\n".join(lines)


def try_park_last_check_import_fixes(root: Path) -> Optional[Dict[str, Any]]:
    """If last_check is a relocated-import pytest failure, park HITL ops. No LLM."""
    meta = load_last_check_meta(root)
    if not meta or meta.get("ok"):
        return None
    log_path = Path(root) / LAST_CHECK_LOG
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except OSError:
        return None
    from eurika.refactor.fix_import_from_verify import suggest_fixes_from_verify_log

    ops = suggest_fixes_from_verify_log(root, log_text)
    if not ops:
        return None
    from eurika.orchestration.team_mode import save_pending_plan

    save_pending_plan(
        Path(root),
        {
            "source": "last-check-import-fix",
            "summary": f"{len(ops)} relocated import(s) from last_check",
        },
        ops,
        [],
        session_id="last-check-import-fix",
    )
    files = [str(op.get("target_file") or "") for op in ops if op.get("target_file")]
    listed = ", ".join(files) if files else "pending_plan"
    return {
        "text": (
            f"Нашла {len(ops)} переехавших импорт(а) в `.eurika/last_check.log` "
            f"и поставила в Approvals: {listed}.\n\n"
            "Load pending plan → просмотр diff → Approve → Save → Run apply-approved."
        ),
        "error": None,
        "approvalsQueued": len(ops),
    }
