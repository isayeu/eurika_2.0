"""Workspace-scoped live log of API / agent work for Chat, Terminal, Desktop."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVITY_FILE = "live_activity.jsonl"
MAX_BYTES = 1_500_000
LIVE_RPC_METHODS = frozenset(
    {
        "session/chat",
        "tool/call",
        "agent/run",
        "command/run",
        "proposal/apply",
        "proposal/reject",
        "context/decide",
        "approval/apply",
    }
)
SILENT_HTTP_PATHS = frozenset({"/api/activity"})
# These already emit start/done from chat/exec/RPC handlers.
COVERED_POST_PATHS = frozenset({"/api/chat", "/api/exec", "/rpc", "/chat"})
_LOCK = threading.Lock()


def activity_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".eurika" / ACTIVITY_FILE


def chat_history_path(workspace: Path) -> Path:
    try:
        from eurika.api.chat_sessions import transcript_path

        return transcript_path(workspace)
    except Exception:
        return Path(workspace).expanduser().resolve() / ".eurika" / "chat_history" / "chat.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clip(value: Any, limit: int = 400) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def consume_jsonl(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    """Read new JSON objects from ``offset``. Returns (records, new_offset)."""
    if offset < 0:
        offset = 0
    if not path.is_file():
        return ([], 0)
    records: list[dict[str, Any]] = []
    try:
        size = path.stat().st_size
        if offset > size:
            offset = 0
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(offset)
            for line in stream:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
            new_offset = stream.tell()
    except OSError:
        return ([], offset)
    return (records, new_offset)


def file_end(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def recent(workspace: Path, *, after_offset: int = 0, limit: int = 80) -> dict[str, Any]:
    events, offset = consume_jsonl(activity_path(workspace), after_offset)
    if limit > 0:
        events = events[-limit:]
    return {"events": events, "offset": offset}


def _title(method: str, params: dict[str, Any]) -> str:
    if method in {"session/chat", "POST /api/chat"}:
        msg = params.get("message")
        if isinstance(msg, str) and msg.strip():
            return f"{method} — «{_clip(msg, 160)}»"
        return f"{method} (продолжение)"
    if method == "tool/call":
        tool = str(params.get("tool") or params.get("name") or "tool")
        path = ""
        args = params.get("arguments")
        if isinstance(args, dict):
            path = str(args.get("path") or "")
        return f"tool/call {tool} {path}".strip()
    if method == "POST /api/exec":
        return f"exec {_clip(params.get('command'), 160)}"
    return method


def publish(workspace: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Append one activity event. Never raises into the request path."""
    record = dict(event)
    record.setdefault("id", uuid.uuid4().hex[:12])
    record.setdefault("ts", _now())
    path = activity_path(workspace)
    encoded = json.dumps(record, ensure_ascii=False) + "\n"
    try:
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file() and path.stat().st_size > MAX_BYTES:
                try:
                    path.write_text("", encoding="utf-8")
                except OSError:
                    pass
            with path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
    except OSError:
        return record
    return record


def publish_start(
    workspace: Path,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    client: str = "http",
) -> dict[str, Any]:
    params = params or {}
    message = params.get("message") if isinstance(params.get("message"), str) else ""
    return publish(
        workspace,
        {
            "phase": "start",
            "kind": "chat" if "chat" in method else "rpc",
            "client": client,
            "method": method,
            "title": _title(method, params),
            "message": _clip(message, 500) if message else "",
        },
    )


def publish_done(
    workspace: Path,
    started: dict[str, Any] | None,
    *,
    ok: bool,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    method = str((started or {}).get("method") or "")
    payload: dict[str, Any] = {
        "id": (started or {}).get("id") or uuid.uuid4().hex[:12],
        "phase": "done",
        "kind": (started or {}).get("kind") or "rpc",
        "client": (started or {}).get("client") or "http",
        "method": method,
        "title": (started or {}).get("title") or method,
        "ok": bool(ok),
    }
    if error:
        payload["error"] = _clip(error, 300)
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str) and text.strip():
            payload["text"] = _clip(text, 400)
        for key in ("terminal_cmd", "terminal_output", "terminal_exit_code"):
            if key in result:
                value = result[key]
                payload[key] = _clip(value, 2000) if key != "terminal_exit_code" else value
        if "approvalsQueued" in result:
            try:
                payload["approvalsQueued"] = int(result.get("approvalsQueued") or 0)
            except (TypeError, ValueError):
                payload["approvalsQueued"] = 0
        output = result.get("output")
        if isinstance(output, str) and output.strip() and "terminal_output" not in payload:
            payload["terminal_output"] = _clip(output, 2000)
            payload["terminal_cmd"] = payload.get("terminal_cmd") or f"$ {method}"
    return publish(workspace, payload)


def should_mirror_http(path: str, http_method: str = "GET") -> bool:
    normalized = (path or "").rstrip("/") or "/"
    if normalized in SILENT_HTTP_PATHS:
        return False
    if http_method.upper() == "POST" and normalized in COVERED_POST_PATHS:
        return False
    return True


def publish_http(
    workspace: Path,
    http_method: str,
    path: str,
    *,
    client: str = "http",
    ok: bool = True,
    status: int = 200,
    detail: str = "",
) -> dict[str, Any] | None:
    """One-shot visible hit for GET/POST (health, /api/*, …)."""
    normalized = (path or "").rstrip("/") or "/"
    if not should_mirror_http(normalized, http_method):
        return None
    title = f"{http_method} {normalized}"
    if detail:
        title = f"{title} — {_clip(detail, 160)}"
    return publish(
        workspace,
        {
            "phase": "done",
            "kind": "http",
            "client": client,
            "method": f"{http_method} {normalized}",
            "title": title,
            "ok": bool(ok),
            "status": int(status),
        },
    )


def should_mirror_rpc(method: str) -> bool:
    return method in LIVE_RPC_METHODS
