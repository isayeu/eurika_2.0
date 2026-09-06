"""Telegram channel to the same Eurika chat agent (VISION C.12 v1).

Long-poll Bot API → ``chat_send`` → reply text. Does **not** auto-apply patches:
HITL stays in Approvals — Telegram can **/approve** / **/reject** decisions
(and inline buttons on push), then Qt/Desktop or ``eurika fix . --apply-approved``.

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
NOTIFY_STAMP_REL = ".eurika/telegram_notify.json"


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


def format_telegram_bot_status(project_root: Path) -> str:
    """Human-readable status for Chat / Telegram «бот жив?»."""
    st = telegram_bot_status(project_root)
    token_ok = bool(_env_token())
    allowed = parse_allowed_chat_ids()
    if allowed is None:
        allow_bit = "allowlist: any (EURIKA_TELEGRAM_ALLOW_ANY)"
    elif not allowed:
        allow_bit = "allowlist: empty (задайте EURIKA_TELEGRAM_CHAT_IDS)"
    else:
        allow_bit = f"allowlist: {len(allowed)} chat_id(s)"
    lines = [
        "Telegram-bot (C.12):",
        f"- running: **{bool(st.get('running'))}**"
        + (f" (pid {st.get('pid')})" if st.get("pid") else ""),
        f"- token: {'задан' if token_ok else 'нет (EURIKA_TELEGRAM_BOT_TOKEN)'}",
        f"- {allow_bit}",
    ]
    if st.get("stale") and st.get("pid"):
        lines.append("- pid file stale (процесс не жив)")
    if st.get("log_file"):
        lines.append(f"- log: `{st.get('log_file')}`")
    if not st.get("running"):
        lines.append("- старт: «запусти telegram-bot»")
    else:
        lines.append("- стоп: «останови telegram-bot»")
    return "\n".join(lines)


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
        return result
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
        chat_id_raw = chat.get("id")
        update_id_raw = update.get("update_id")
        if chat_id_raw is None or update_id_raw is None:
            return None
        chat_id = int(chat_id_raw)
        update_id = int(update_id_raw)
    except (TypeError, ValueError):
        return None
    text = msg.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return chat_id, update_id, text.strip()


def telegram_slash_command(text: str) -> str | None:
    """Return a canned reply for Bot API slash commands; else None.

    Approvals HITL (``/approve`` / ``/reject`` / ``/approvals``) is handled in
    ``handle_text_message`` (needs project root) — not here.
    """
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
            "• четвёртый полигон\n"
            "• статус apply / получилось?\n"
            "• /status — жив ли long-poll процесс\n"
            "• /approvals — что в очереди\n"
            "• /approve — отметить все ops approve (без apply)\n"
            "• /reject — отметить все ops reject\n\n"
            "Новые Approvals приходят push + кнопки Approve/Reject.\n"
            "Apply на диск — только Qt/Desktop или "
            "`eurika fix . --apply-approved`."
        )
    if cmd in {"/approve", "/reject", "/approvals"}:
        return None  # handled with project root
    return (
        f"Команда `{cmd}` не используется. Напишите обычный запрос текстом "
        "(без ведущего `/`), или /help."
    )


def approvals_inline_keyboard() -> str:
    """JSON ``reply_markup`` for Approvals HITL (no apply)."""
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": "Approve all", "callback_data": "eurika:approve"},
                    {"text": "Reject all", "callback_data": "eurika:reject"},
                ]
            ]
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def format_approvals_status(project_root: Path) -> str:
    """Short Approvals queue summary for Telegram."""
    from eurika.orchestration.team_mode import load_pending_plan

    root = Path(project_root).resolve()
    plan = load_pending_plan(root)
    if not plan:
        return "Approvals: пусто (нет `.eurika/pending_plan.json`)."
    ops = plan.get("operations") if isinstance(plan.get("operations"), list) else []
    pending = n_appr = n_rej = 0
    lines = ["Approvals (pending_plan):"]
    for op in ops:
        if not isinstance(op, dict):
            continue
        dec = str(op.get("team_decision") or "pending").strip().lower()
        kind = str(op.get("kind") or "op")
        target = str(op.get("target_file") or "")
        if dec == "approve":
            n_appr += 1
            mark = "approve"
        elif dec == "reject":
            n_rej += 1
            mark = "reject"
        else:
            pending += 1
            mark = "pending"
        bit = f"• [{mark}] `{kind}`"
        if target:
            bit += f" — `{target}`"
        lines.append(bit)
    lines.append(f"итог: pending={pending}, approve={n_appr}, reject={n_rej}")
    if n_appr:
        lines.append("дальше: `eurika fix . --apply-approved` (Telegram не apply)")
    elif pending:
        lines.append("команды: /approve или /reject (только решения, не apply)")
    return "\n".join(lines)


def handle_approvals_decision(
    project_root: Path,
    *,
    decision: str,
    approved_by: str = "telegram",
) -> str:
    """Approve/reject all pending ops; never apply patches.

    Also mirrors the decision into Chat/Goals (Qt transcript poll) so a remote
    HITL choice is visible when the desktop UI is open.
    """
    from eurika.api.fix_status import announce_approvals_decision
    from eurika.orchestration.team_mode import decide_all_pending

    root = Path(project_root).resolve()
    out = decide_all_pending(
        root,
        decision=decision,
        approved_by=approved_by,
    )
    if not out.get("ok"):
        return f"Approvals: не вышло — {out.get('error') or 'error'}"
    choice = str(out.get("decision") or decision)
    n = int(out.get("n") or 0)
    announced = announce_approvals_decision(
        root,
        decision=choice,
        n=n,
        approved_by=approved_by,
        client="telegram",
        publish_activity=True,
    )
    return str(announced.get("text") or "").strip() or (
        f"Approvals: {choice} ×{n} (by {approved_by})"
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
        # Avoid Telegram seeing bare "error: error".
        err_s = str(err).strip() or "unknown"
        if err_s.lower() in {"error", "err", "failed"}:
            parts.append(
                "Не удалось получить ответ агента. "
                "Попробуй ещё раз или напиши конкретный запрос "
                "(«что за проект?», «найди баг», «статус telegram-bot»)."
            )
        else:
            parts.append(f"error: {err_s}")
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


def _notify_enabled() -> bool:
    from eurika.utils.env import env_bool

    # Default on when token+allowlist exist; EURIKA_TELEGRAM_NOTIFY_APPROVALS=0 disables.
    if os.environ.get("EURIKA_TELEGRAM_NOTIFY_APPROVALS") is None:
        return True
    return env_bool("EURIKA_TELEGRAM_NOTIFY_APPROVALS")


def _approvals_fingerprint(
    operations: list[dict[str, Any]],
    *,
    created_at: str = "",
) -> str:
    import hashlib

    parts: list[str] = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        parts.append(
            f"{op.get('kind')}|{op.get('target_file')}|{op.get('team_decision')}"
        )
    parts.sort()
    raw = created_at + "\n" + "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def format_approvals_notify_message(
    project_root: Path,
    operations: list[dict[str, Any]],
    *,
    patch_plan: dict[str, Any] | None = None,
) -> str:
    """Human text for a push when Approvals gains pending ops."""
    root = Path(project_root).resolve()
    pending = [
        op
        for op in operations
        if isinstance(op, dict)
        and str(op.get("team_decision") or "pending").strip().lower() == "pending"
    ]
    plan = patch_plan if isinstance(patch_plan, dict) else {}
    source = str(
        plan.get("source")
        or plan.get("summary")
        or plan.get("drill")
        or plan.get("kind")
        or "pending_plan"
    ).strip()
    lines = [
        f"Eurika Approvals: {len(pending)} op(s) ждут review",
        f"проект: `{root.name}`",
    ]
    if source:
        lines.append(f"источник: {source}")
    for op in pending[:8]:
        kind = str(op.get("kind") or "op").strip()
        target = str(op.get("target_file") or "").strip()
        desc = str(op.get("description") or "").strip()
        bit = f"• `{kind}`"
        if target:
            bit += f" — `{target}`"
        elif desc:
            bit += f" — {desc[:80]}"
        lines.append(bit)
    if len(pending) > 8:
        lines.append(f"… и ещё {len(pending) - 8}")
    lines.append("→ /approve или /reject здесь (только решения)")
    lines.append("→ apply: Qt/Desktop или `eurika fix . --apply-approved`")
    lines.append("(Telegram сам патчи на диск не пишет)")
    out = "\n".join(lines)
    if len(out) > 3900:
        out = out[:3850] + "\n…"
    return out


def notify_approvals_pending(
    project_root: Path,
    *,
    operations: list[dict[str, Any]] | None = None,
    patch_plan: dict[str, Any] | None = None,
    created_at: str = "",
    token: str | None = None,
    chat_ids: str | None = None,
    allow_any: bool | None = None,
    api: Callable[..., Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Push Approvals notice to allowlisted chats (best-effort; never raises).

    Skips when token/allowlist missing, notify disabled, allow-any mode (no ids),
    or the same fingerprint was already sent. Does **not** apply patches.
    """
    root = Path(project_root).resolve()
    base: dict[str, Any] = {
        "ok": True,
        "sent": 0,
        "skipped": None,
        "chat_ids": [],
    }
    try:
        if not force and not _notify_enabled():
            return {**base, "skipped": "notify_disabled"}
        tok = _env_token(token)
        if not tok:
            return {**base, "skipped": "no_token"}
        allowed = parse_allowed_chat_ids(chat_ids, allow_any=allow_any)
        if allowed is None:
            return {**base, "skipped": "allow_any_no_targets"}
        if not allowed:
            return {**base, "skipped": "empty_allowlist"}

        ops = list(operations or [])
        if not ops:
            from eurika.orchestration.team_mode import load_pending_plan

            plan = load_pending_plan(root) or {}
            raw_ops = plan.get("operations")
            ops = [o for o in raw_ops if isinstance(o, dict)] if isinstance(raw_ops, list) else []
            if patch_plan is None and isinstance(plan.get("patch_plan"), dict):
                patch_plan = plan.get("patch_plan")  # type: ignore[assignment]
            if not created_at:
                created_at = str(plan.get("created_at") or "")
        pending = [
            op
            for op in ops
            if str(op.get("team_decision") or "pending").strip().lower() == "pending"
        ]
        if not pending:
            return {**base, "skipped": "no_pending_ops"}

        fp = _approvals_fingerprint(pending, created_at=created_at)
        stamp_path = root / NOTIFY_STAMP_REL
        if not force and stamp_path.is_file():
            try:
                prev = json.loads(stamp_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prev = {}
            if isinstance(prev, dict) and prev.get("fingerprint") == fp:
                return {**base, "skipped": "already_notified", "fingerprint": fp}

        text = format_approvals_notify_message(
            root, pending, patch_plan=patch_plan if isinstance(patch_plan, dict) else {}
        )
        api_fn = api or telegram_api
        sent: list[int] = []
        errors: list[str] = []
        for chat_id in sorted(allowed):
            try:
                api_fn(
                    tok,
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": text,
                        "reply_markup": approvals_inline_keyboard(),
                    },
                )
                sent.append(chat_id)
            except Exception as exc:
                errors.append(f"{chat_id}: {exc}")
        try:
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            stamp_path.write_text(
                json.dumps(
                    {
                        "fingerprint": fp,
                        "sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "sent": sent,
                        "n_ops": len(pending),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return {
            "ok": not errors or bool(sent),
            "sent": len(sent),
            "chat_ids": sent,
            "errors": errors,
            "fingerprint": fp,
            "skipped": None if sent else ("send_failed" if errors else "no_sent"),
            "text": text[:200],
        }
    except Exception as exc:
        return {**base, "ok": False, "skipped": "error", "error": str(exc)}


def _apply_fingerprint(*, run_id: str, ok: bool, modified: list[Any], exit_code: int | None) -> str:
    import hashlib

    mods = ",".join(str(x) for x in modified[:20])
    raw = f"{run_id}|{ok}|{exit_code}|{mods}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def format_apply_notify_message(
    project_root: Path,
    *,
    text: str,
    ok: bool,
) -> str:
    """Push text after apply-approved (same facts as Chat итог)."""
    root = Path(project_root).resolve()
    mark = "ok" if ok else "fail"
    header = f"Eurika apply-approved [{mark}] — `{root.name}`"
    body = (text or "").strip() or format_last_fix_status(root)
    out = f"{header}\n\n{body}"
    if len(out) > 3900:
        out = out[:3850] + "\n…"
    return out


def notify_apply_result(
    project_root: Path,
    *,
    text: str,
    ok: bool,
    exit_code: int | None = None,
    run_id: str = "",
    modified: list[Any] | None = None,
    token: str | None = None,
    chat_ids: str | None = None,
    allow_any: bool | None = None,
    api: Callable[..., Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Push apply-approved outcome to allowlisted chats (best-effort; never raises).

    Same gate as Approvals push (``EURIKA_TELEGRAM_NOTIFY_APPROVALS``). Does **not**
    apply patches — only reports verify/modified after HITL apply elsewhere.
    """
    root = Path(project_root).resolve()
    base: dict[str, Any] = {
        "ok": True,
        "sent": 0,
        "skipped": None,
        "chat_ids": [],
    }
    try:
        if not force and not _notify_enabled():
            return {**base, "skipped": "notify_disabled"}
        tok = _env_token(token)
        if not tok:
            return {**base, "skipped": "no_token"}
        allowed = parse_allowed_chat_ids(chat_ids, allow_any=allow_any)
        if allowed is None:
            return {**base, "skipped": "allow_any_no_targets"}
        if not allowed:
            return {**base, "skipped": "empty_allowlist"}

        mods = list(modified or [])
        rid = str(run_id or "").strip()
        if not rid:
            try:
                report = json.loads(
                    (root / "eurika_fix_report.json").read_text(encoding="utf-8")
                )
                if isinstance(report, dict):
                    rid = str(report.get("run_id") or "")
                    if not mods and isinstance(report.get("modified"), list):
                        mods = list(report.get("modified") or [])
            except Exception:
                rid = ""
        fp = _apply_fingerprint(
            run_id=rid or "unknown",
            ok=bool(ok),
            modified=mods,
            exit_code=exit_code,
        )
        stamp_path = root / NOTIFY_STAMP_REL
        if not force and stamp_path.is_file():
            try:
                prev = json.loads(stamp_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prev = {}
            if isinstance(prev, dict) and prev.get("apply_fingerprint") == fp:
                return {**base, "skipped": "already_notified", "fingerprint": fp}

        msg = format_apply_notify_message(root, text=text, ok=bool(ok))
        api_fn = api or telegram_api
        sent: list[int] = []
        errors: list[str] = []
        for chat_id in sorted(allowed):
            try:
                api_fn(tok, "sendMessage", {"chat_id": chat_id, "text": msg})
                sent.append(chat_id)
            except Exception as exc:
                errors.append(f"{chat_id}: {exc}")
        try:
            stamp_path.parent.mkdir(parents=True, exist_ok=True)
            prev_blob: dict[str, Any] = {}
            if stamp_path.is_file():
                try:
                    loaded = json.loads(stamp_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        prev_blob = loaded
                except (OSError, json.JSONDecodeError):
                    prev_blob = {}
            prev_blob.update(
                {
                    "apply_fingerprint": fp,
                    "apply_sent_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "apply_sent": sent,
                    "apply_ok": bool(ok),
                }
            )
            stamp_path.write_text(
                json.dumps(prev_blob, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        return {
            "ok": not errors or bool(sent),
            "sent": len(sent),
            "chat_ids": sent,
            "errors": errors,
            "fingerprint": fp,
            "skipped": None if sent else ("send_failed" if errors else "no_sent"),
            "text": msg[:200],
        }
    except Exception as exc:
        return {**base, "ok": False, "skipped": "error", "error": str(exc)}


def extract_callback_update(
    update: dict[str, Any],
) -> tuple[int, int, str, str] | None:
    """Return (chat_id, update_id, callback_data, callback_query_id) or None."""
    cq = update.get("callback_query")
    if not isinstance(cq, dict):
        return None
    data = str(cq.get("data") or "").strip()
    cq_id = str(cq.get("id") or "").strip()
    msg = cq.get("message")
    chat: dict[str, Any] | None = None
    if isinstance(msg, dict) and isinstance(msg.get("chat"), dict):
        chat = msg.get("chat")  # type: ignore[assignment]
    else:
        frm = cq.get("from")
        if isinstance(frm, dict) and frm.get("id") is not None:
            chat = {"id": frm.get("id")}
    if not isinstance(chat, dict):
        return None
    try:
        chat_id = int(chat.get("id"))
        update_id = int(update.get("update_id") or 0)
    except (TypeError, ValueError):
        return None
    if not data or not cq_id:
        return None
    return chat_id, update_id, data, cq_id


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
    root = Path(project_root).resolve()
    raw = (text or "").strip()
    if raw.startswith("/"):
        cmd = raw.split()[0].lower().split("@", 1)[0]
        if cmd == "/status":
            return format_telegram_bot_status(root)
        if cmd == "/approvals":
            return format_approvals_status(root)
        if cmd == "/approve":
            return handle_approvals_decision(
                root, decision="approve", approved_by=f"telegram:{chat_id}"
            )
        if cmd == "/reject":
            return handle_approvals_decision(
                root, decision="reject", approved_by=f"telegram:{chat_id}"
            )
    slash = telegram_slash_command(text)
    if slash is not None:
        return slash
    if is_apply_result_question(text):
        return format_last_fix_status(root)
    # «бот жив?» without going through full chat_send (works offline from Bot API).
    try:
        from eurika.api.chat_direct import is_telegram_bot_status_request

        if is_telegram_bot_status_request(text):
            return format_telegram_bot_status(root)
    except Exception:
        pass
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
    api: Callable[..., Any] | None = None,
) -> int:
    """Handle a batch of updates; return highest update_id processed (0 if none)."""
    max_id = 0
    api_fn = api or telegram_api
    sender = send_message or (
        lambda tok, cid, text: api_fn(
            tok, "sendMessage", {"chat_id": cid, "text": text}
        )
    )
    root = Path(project_root).resolve()
    for update in updates:
        if not isinstance(update, dict):
            continue
        try:
            uid = int(update.get("update_id") or 0)
        except (TypeError, ValueError):
            uid = 0
        if uid > max_id:
            max_id = uid

        cb = extract_callback_update(update)
        if cb is not None:
            chat_id, _uid, data, cq_id = cb
            if allowed_chat_ids is not None and chat_id not in allowed_chat_ids:
                reply = "Этот chat_id не в allowlist (EURIKA_TELEGRAM_CHAT_IDS)."
            elif data == "eurika:approve":
                reply = handle_approvals_decision(
                    root, decision="approve", approved_by=f"telegram:{chat_id}"
                )
            elif data == "eurika:reject":
                reply = handle_approvals_decision(
                    root, decision="reject", approved_by=f"telegram:{chat_id}"
                )
            else:
                reply = f"Неизвестная кнопка `{data}`."
            try:
                api_fn(
                    token,
                    "answerCallbackQuery",
                    {"callback_query_id": cq_id, "text": reply[:180]},
                )
            except Exception:
                pass
            sender(token, chat_id, reply)
            continue

        extracted = extract_text_update(update)
        if extracted is None:
            continue
        chat_id, _upd, text = extracted
        reply = handle_text_message(
            root,
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
    stopping = {"flag": False}

    def _shutdown_cursor(_signum=None, _frame=None) -> None:
        stopping["flag"] = True
        try:
            from eurika.agent.cursor_bridge_gc import shutdown_cursor_sdk

            shutdown_cursor_sdk()
        except Exception:
            pass

    prev_term = signal.signal(signal.SIGTERM, _shutdown_cursor)
    prev_int = signal.signal(signal.SIGINT, _shutdown_cursor)
    try:
        while True:
            if stopping["flag"]:
                return {
                    "ok": True,
                    "offset": current_offset,
                    "processed_batches": processed,
                    "return_code": 0,
                    "stopped": True,
                }
            try:
                result = api_fn(
                    tok,
                    "getUpdates",
                    {
                        "timeout": int(poll_timeout),
                        "offset": current_offset,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
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
                    api=api_fn,
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
    finally:
        signal.signal(signal.SIGTERM, prev_term)
        signal.signal(signal.SIGINT, prev_int)
        _shutdown_cursor()
