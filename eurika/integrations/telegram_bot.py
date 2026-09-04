"""Telegram channel to the same Eurika chat agent (VISION C.12 v1).

Long-poll Bot API → ``chat_send`` → reply text. Does **not** auto-apply patches:
HITL stays in Qt Approvals / ``eurika fix . --apply-approved``.

Env:
  EURIKA_TELEGRAM_BOT_TOKEN   — required
  EURIKA_TELEGRAM_CHAT_IDS    — comma-separated allowlist (required unless
                                EURIKA_TELEGRAM_ALLOW_ANY=1 for local dogfood)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

ChatSendFn = Callable[..., dict[str, Any]]


def _env_token(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("EURIKA_TELEGRAM_BOT_TOKEN") or "").strip()


def parse_allowed_chat_ids(
    raw: str | None = None,
    *,
    allow_any: bool | None = None,
) -> set[int] | None:
    """Return allowlist set, or None when any chat is allowed (dogfood only)."""
    if allow_any is None:
        from eurika.utils.env import env_bool

        allow_any = env_bool("EURIKA_TELEGRAM_ALLOW_ANY")
    if allow_any:
        return None
    text = (raw if raw is not None else os.environ.get("EURIKA_TELEGRAM_CHAT_IDS") or "").strip()
    if not text:
        return set()
    out: set[int] = set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        out.add(int(part))
    return out


def telegram_api(
    token: str,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> Any:
    """Call ``https://api.telegram.org/bot<token>/<method>`` (POST form)."""
    if not token:
        raise ValueError("Telegram bot token is empty")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if params:
        data = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        ).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Telegram API {method} HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Telegram API {method} network error: {exc}") from exc
    payload = json.loads(body)
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {payload!r}"[:500])
    result = payload.get("result")
    if isinstance(result, (dict, list)):
        return result  # type: ignore[return-value]
    return {"result": result}


def extract_text_update(update: dict[str, Any]) -> tuple[int, int, str] | None:
    """Return (chat_id, update_id, text) for a plain text message, else None."""
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat")
    if not isinstance(chat, dict):
        return None
    try:
        chat_id = int(chat.get("id"))
        update_id = int(update.get("update_id"))
    except (TypeError, ValueError):
        return None
    text = msg.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return chat_id, update_id, text.strip()


def format_telegram_reply(payload: dict[str, Any]) -> str:
    """Turn chat_send result into a Telegram-sized reply."""
    text = str(payload.get("text") or "").strip()
    err = payload.get("error")
    queued = payload.get("approvalsQueued")
    parts: list[str] = []
    if text:
        parts.append(text)
    if err and not text:
        parts.append(f"error: {err}")
    elif err and text:
        parts.append(f"(note: {err})")
    try:
        q = int(queued or 0)
    except (TypeError, ValueError):
        q = 0
    if q > 0:
        parts.append(
            f"\n→ {q} op(s) in Approvals (Qt). Apply only after review: "
            "`eurika fix . --apply-approved`."
        )
    out = "\n".join(parts).strip() or "(empty response)"
    if len(out) > 3900:
        out = out[:3850] + "\n…"
    return out


def handle_text_message(
    project_root: Path,
    chat_id: int,
    text: str,
    *,
    allowed_chat_ids: set[int] | None,
    chat_send: ChatSendFn | None = None,
) -> str:
    """Run one inbound Telegram text through Eurika chat; return reply text."""
    if allowed_chat_ids is not None and chat_id not in allowed_chat_ids:
        return "Этот chat_id не в allowlist (EURIKA_TELEGRAM_CHAT_IDS)."
    if chat_send is None:
        from eurika.api.chat import chat_send as _chat_send

        chat_send = _chat_send
    payload = chat_send(Path(project_root).resolve(), text)
    if not isinstance(payload, dict):
        return "chat_send returned unexpected payload"
    return format_telegram_reply(payload)


def process_updates(
    project_root: Path,
    updates: Iterable[dict[str, Any]],
    *,
    token: str,
    allowed_chat_ids: set[int] | None,
    chat_send: ChatSendFn | None = None,
    send_message: Callable[[str, int, str], Any] | None = None,
) -> int:
    """Handle a batch of updates; return highest update_id processed (0 if none)."""
    max_id = 0
    sender = send_message or (
        lambda tok, cid, text: telegram_api(
            tok, "sendMessage", {"chat_id": cid, "text": text}
        )
    )
    for update in updates:
        if not isinstance(update, dict):
            continue
        try:
            uid = int(update.get("update_id") or 0)
        except (TypeError, ValueError):
            uid = 0
        if uid > max_id:
            max_id = uid
        extracted = extract_text_update(update)
        if extracted is None:
            continue
        chat_id, _upd, text = extracted
        reply = handle_text_message(
            project_root,
            chat_id,
            text,
            allowed_chat_ids=allowed_chat_ids,
            chat_send=chat_send,
        )
        sender(token, chat_id, reply)
    return max_id


def run_telegram_bot(
    project_root: Path,
    *,
    token: str | None = None,
    chat_ids: str | None = None,
    allow_any: bool | None = None,
    once: bool = False,
    poll_timeout: int = 25,
    offset: int = 0,
    sleep_on_error: float = 2.0,
    chat_send: ChatSendFn | None = None,
    api: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """
    Long-poll Telegram and forward text to ``chat_send``.

    With ``once=True``: one getUpdates call then return (for CLI/tests).
    """
    tok = _env_token(token)
    if not tok:
        return {
            "ok": False,
            "error": "Set EURIKA_TELEGRAM_BOT_TOKEN (or --token)",
            "return_code": 1,
        }
    allowed = parse_allowed_chat_ids(chat_ids, allow_any=allow_any)
    if allowed is not None and not allowed:
        return {
            "ok": False,
            "error": (
                "Set EURIKA_TELEGRAM_CHAT_IDS to an allowlist, "
                "or EURIKA_TELEGRAM_ALLOW_ANY=1 for local dogfood only"
            ),
            "return_code": 1,
        }
    api_fn = api or telegram_api
    root = Path(project_root).resolve()
    current_offset = int(offset)
    processed = 0
    while True:
        try:
            result = api_fn(
                tok,
                "getUpdates",
                {
                    "timeout": int(poll_timeout),
                    "offset": current_offset,
                    "allowed_updates": json.dumps(["message"]),
                },
                timeout=float(poll_timeout) + 10.0,
            )
            updates = result if isinstance(result, list) else result.get("result") or []
            if not isinstance(updates, list):
                updates = []
            max_id = process_updates(
                root,
                updates,
                token=tok,
                allowed_chat_ids=allowed,
                chat_send=chat_send,
                send_message=lambda _t, cid, text: api_fn(
                    tok, "sendMessage", {"chat_id": cid, "text": text}
                ),
            )
            if max_id:
                current_offset = max_id + 1
                processed += 1
        except Exception as exc:
            if once:
                return {
                    "ok": False,
                    "error": str(exc),
                    "offset": current_offset,
                    "return_code": 1,
                }
            time.sleep(sleep_on_error)
            continue
        if once:
            return {
                "ok": True,
                "offset": current_offset,
                "processed_batches": processed,
                "return_code": 0,
            }
