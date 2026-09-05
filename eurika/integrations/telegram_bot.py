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
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

from eurika.api.fix_status import format_last_fix_status, is_apply_result_question

ChatSendFn = Callable[..., dict[str, Any]]

PID_REL = ".eurika/telegram_bot.pid"
LOG_REL = ".eurika/telegram_bot.log"


def _pid_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / PID_REL


def _log_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / LOG_REL


def telegram_bot_status(project_root: Path) -> dict[str, Any]:
    """Return whether a background telegram-bot process is alive."""
    path = _pid_path(project_root)
    if not path.is_file():
        return {"running": False, "pid": None, "pid_file": str(path)}
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return {"running": False, "pid": None, "pid_file": str(path), "stale": True}
    try:
        os.kill(pid, 0)
        running = True
    except OSError:
        running = False
    return {
        "running": running,
        "pid": pid,
        "pid_file": str(path),
        "log_file": str(_log_path(project_root)),
        "stale": not running,
    }


def start_telegram_bot_background(project_root: Path) -> dict[str, Any]:
    """Spawn ``eurika telegram-bot`` detached; idempotent if already running."""
    root = Path(project_root).resolve()
    try:
        from eurika.utils.env import load_project_dotenv

        load_project_dotenv(root)
    except Exception:
        pass
    if not _env_token():
        return {
            "ok": False,
            "error": "Set EURIKA_TELEGRAM_BOT_TOKEN in .env (or environment)",
            "return_code": 1,
        }
    allowed = parse_allowed_chat_ids()
    if allowed is not None and not allowed:
        return {
            "ok": False,
            "error": (
                "Set EURIKA_TELEGRAM_CHAT_IDS or EURIKA_TELEGRAM_ALLOW_ANY=1"
            ),
            "return_code": 1,
        }
    st = telegram_bot_status(root)
    if st.get("running"):
        return {
            "ok": True,
            "already_running": True,
            "pid": st.get("pid"),
            "log_file": st.get("log_file"),
            "return_code": 0,
        }
    eurika_dir = root / ".eurika"
    eurika_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_path(root)
    pid_path = _pid_path(root)
    cmd = [sys.executable, "-m", "eurika_cli", "telegram-bot", str(root)]
    try:
        log_f = open(log_path, "a", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"cannot open log: {exc}", "return_code": 1}
    try:
        log_f.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_f.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        log_f.close()
        return {"ok": False, "error": str(exc), "return_code": 1}
    try:
        pid_path.write_text(str(proc.pid), encoding="utf-8")
    except OSError:
        pass
    time.sleep(0.4)
    if proc.poll() is not None:
        snippet = ""
        try:
            snippet = log_path.read_text(encoding="utf-8")[-500:]
        except OSError:
            pass
        return {
            "ok": False,
            "error": f"telegram-bot exited immediately (code {proc.returncode})",
            "log_tail": snippet,
            "return_code": int(proc.returncode or 1),
        }
    return {
        "ok": True,
        "pid": proc.pid,
        "log_file": str(log_path),
        "pid_file": str(pid_path),
        "command": " ".join(cmd),
        "return_code": 0,
    }


def stop_telegram_bot_background(project_root: Path) -> dict[str, Any]:
    """Stop background telegram-bot if the pid file points at a live process."""
    root = Path(project_root).resolve()
    st = telegram_bot_status(root)
    pid = st.get("pid")
    if not st.get("running") or not isinstance(pid, int):
        path = _pid_path(root)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        return {
            "ok": True,
            "stopped": False,
            "message": "telegram-bot was not running",
            "return_code": 0,
        }
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "return_code": 1}
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except OSError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        _pid_path(root).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True, "stopped": True, "pid": pid, "return_code": 0}


def looks_like_telegram_bot_command(command: str) -> bool:
    """True when a run_command target is the telegram-bot CLI (any form)."""
    raw = (command or "").strip().lower()
    if not raw:
        return False
    if raw in {"telegram-bot", "telegram_bot", "telegrambot"}:
        return True
    if "telegram-bot" in raw or "telegram_bot" in raw:
        return True
    return False



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


def telegram_slash_command(text: str) -> str | None:
    """Return a canned reply for Bot API slash commands; else None."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    cmd = raw.split()[0].lower().split("@", 1)[0]
    if cmd in {"/start", "/help"}:
        return (
            "Eurika — coding-агент этого проекта (Telegram-канал C.12).\n\n"
            "Пишите обычным текстом, например:\n"
            "• hi / что за проект?\n"
            "• проведи ритуал\n"
            "• четвёртый полигон\n\n"
            "Патчи из Telegram не применяются — только Approvals в Qt → "
            "`eurika fix . --apply-approved`."
        )
    return (
        f"Команда `{cmd}` не используется. Напишите обычный запрос текстом "
        "(без ведущего `/`)."
    )


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
    slash = telegram_slash_command(text)
    if slash is not None:
        return slash
    root = Path(project_root).resolve()
    if is_apply_result_question(text):
        return format_last_fix_status(root)
    if chat_send is None:
        from eurika.api.chat import chat_send as _chat_send

        chat_send = _chat_send
    payload = chat_send(root, text)
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
