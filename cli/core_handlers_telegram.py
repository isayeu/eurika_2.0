"""CLI handler for Telegram → chat_send bridge (VISION C.12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_telegram_bot(args: Any) -> int:
    from eurika.integrations.telegram_bot import run_telegram_bot

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    once = bool(getattr(args, "once", False))
    allow_any = True if bool(getattr(args, "allow_any", False)) else None
    if not once:
        print(
            "telegram-bot: long-poll → chat_send (Ctrl+C to stop). "
            "HITL apply stays in Approvals / eurika fix . --apply-approved"
        )
    payload = run_telegram_bot(
        path,
        token=getattr(args, "token", None),
        chat_ids=getattr(args, "chat_ids", None),
        allow_any=allow_any,
        once=once,
        poll_timeout=int(getattr(args, "poll_timeout", 25) or 25),
    )
    if once or not payload.get("ok", True):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return int(payload.get("return_code") or (0 if payload.get("ok") else 1))
