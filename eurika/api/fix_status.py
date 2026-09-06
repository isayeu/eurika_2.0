"""Last-apply status from ``eurika_fix_report.json`` (C.12 / C.14 dogfood)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def format_last_fix_status(project_root: Path) -> str:
    """Short factual summary of the latest ``eurika_fix_report.json``."""
    path = Path(project_root).resolve() / "eurika_fix_report.json"
    if not path.is_file():
        return "Отчёта fix ещё нет (`eurika_fix_report.json`)."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "Не удалось прочитать `eurika_fix_report.json`."
    if not isinstance(data, dict):
        return "Некорректный `eurika_fix_report.json`."
    raw_verify = data.get("verify")
    verify: dict[str, Any] = raw_verify if isinstance(raw_verify, dict) else {}
    ok = verify.get("success")
    if ok is None:
        ok = data.get("verify_success")
    modified = data.get("modified") or []
    if not isinstance(modified, list):
        modified = []
    run_id = data.get("run_id") or "?"
    ms = data.get("verify_duration_ms")
    errors = data.get("errors") or []
    lines = [
        f"Последний apply (`{run_id}`):",
        f"- verify: **{ok}**" + (f" (~{ms} ms)" if ms is not None else ""),
        f"- modified: {', '.join(str(x) for x in modified) if modified else '(none)'}",
    ]
    if errors:
        lines.append(f"- errors: {errors!r}"[:300])
    pending = Path(project_root).resolve() / ".eurika" / "pending_plan.json"
    lines.append(
        "- pending_plan: есть (ещё ждут approve)"
        if pending.is_file()
        else "- pending_plan: нет (снят после apply — норма)"
    )
    return "\n".join(lines)


def announce_apply_approved(
    project_root: Path,
    *,
    exit_code: int | None = None,
    client: str = "approvals",
    publish_activity: bool = True,
) -> dict[str, Any]:
    """After ``fix --apply-approved``: Chat line + Goals итог (+ optional live_activity).

    Best-effort; never raises into the apply path. Qt/Desktop pick up the Chat
    line via transcript poll (``append_chat_history``).
    """
    root = Path(project_root).resolve()
    text = format_last_fix_status(root)
    if exit_code is not None:
        text = f"apply-approved (exit {exit_code})\n\n{text}"
    else:
        text = f"apply-approved\n\n{text}"
    ok = True
    modified: list[Any] = []
    try:
        path = root / "eurika_fix_report.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                verify = data.get("verify") if isinstance(data.get("verify"), dict) else {}
                if "success" in verify:
                    ok = bool(verify.get("success"))
                elif "verify_success" in data:
                    ok = bool(data.get("verify_success"))
                if isinstance(data.get("modified"), list):
                    modified = list(data.get("modified") or [])
        if exit_code is not None and int(exit_code) != 0:
            ok = False
    except Exception:
        if exit_code is not None:
            ok = int(exit_code) == 0

    try:
        from eurika.api.chat_context import (
            load_dialog_state,
            release_active_goal_keep_execution,
            save_dialog_state,
            store_last_execution,
        )

        state = load_dialog_state(root)
        state["active_goal"] = {
            "intent": "apply_approved",
            "source": client,
            "target": str(modified[0]) if modified else "pending_plan",
        }
        store_last_execution(
            state,
            {
                "ok": ok,
                "summary": "apply-approved ok" if ok else "apply-approved failed",
                "verification": {"ok": ok},
                "artifacts_changed": [str(x) for x in modified[:12]],
            },
        )
        release_active_goal_keep_execution(state)
        save_dialog_state(root, state)
    except Exception:
        pass

    if publish_activity:
        try:
            from eurika.agent.live_activity import publish_done, publish_start

            started = publish_start(
                root,
                method="approval/apply",
                params={"detail": "apply-approved", "message": "apply-approved → диск"},
                client=client,
            )
            if isinstance(started, dict):
                started["title"] = "apply-approved → диск"
            publish_done(
                root,
                started,
                ok=ok,
                result={"text": text, "approvalsQueued": 0},
                error=None if ok else f"apply-approved exit={exit_code}",
            )
        except Exception:
            pass

    try:
        from eurika.api.chat import _append_chat_history_safe

        _append_chat_history_safe(root, "assistant", text, None)
    except Exception:
        pass

    try:
        from eurika.integrations.telegram_bot import notify_apply_result

        run_id = ""
        try:
            report = json.loads((root / "eurika_fix_report.json").read_text(encoding="utf-8"))
            if isinstance(report, dict):
                run_id = str(report.get("run_id") or "")
        except Exception:
            run_id = ""
        notify_apply_result(
            root,
            text=text,
            ok=ok,
            exit_code=exit_code,
            run_id=run_id,
            modified=modified,
        )
    except Exception:
        pass

    return {"ok": ok, "text": text, "exit_code": exit_code}


def announce_approvals_decision(
    project_root: Path,
    *,
    decision: str,
    n: int,
    approved_by: str = "telegram",
    client: str = "telegram",
    publish_activity: bool = True,
) -> dict[str, Any]:
    """After Telegram/Qt HITL approve|reject (no apply): Chat line + Goals итог.

    Best-effort; never raises. Qt/Desktop pick up via transcript poll.
    """
    root = Path(project_root).resolve()
    choice = str(decision or "").strip().lower()
    if choice in {"approve", "approved", "yes"}:
        choice = "approve"
    elif choice in {"reject", "rejected", "no"}:
        choice = "reject"
    else:
        choice = choice or "unknown"
    by = str(approved_by or client or "user").strip() or "user"
    count = max(0, int(n or 0))
    if choice == "approve":
        text = (
            f"Approvals: **approve** на {count} op(s) (by {by}).\n"
            "Патчи ещё не на диске — Run apply-approved в Qt/Desktop\n"
            "или: `eurika fix . --apply-approved`"
        )
        summary = f"approvals approve ×{count} ({by})"
    elif choice == "reject":
        text = (
            f"Approvals: **reject** на {count} op(s) (by {by}).\n"
            "Apply не нужен; очередь можно сбросить apply-approved "
            "или новым propose."
        )
        summary = f"approvals reject ×{count} ({by})"
    else:
        text = f"Approvals: decision={choice!r} n={count} (by {by})"
        summary = text

    try:
        from eurika.api.chat_context import (
            load_dialog_state,
            release_active_goal_keep_execution,
            save_dialog_state,
            store_last_execution,
        )

        state = load_dialog_state(root)
        state["active_goal"] = {
            "intent": f"approvals_{choice}",
            "source": client,
            "target": "pending_plan",
        }
        store_last_execution(
            state,
            {
                "ok": True,
                "summary": summary,
                "verification": {"ok": True},
                "artifacts_changed": [],
            },
        )
        release_active_goal_keep_execution(state)
        save_dialog_state(root, state)
    except Exception:
        pass

    if publish_activity:
        try:
            from eurika.agent.live_activity import publish_done, publish_start

            started = publish_start(
                root,
                method="approval/decide",
                params={
                    "detail": choice,
                    "message": summary,
                    "n": count,
                },
                client=client,
            )
            if isinstance(started, dict):
                started["title"] = summary
            publish_done(
                root,
                started,
                ok=True,
                result={"text": text, "approvalsQueued": 0},
                error=None,
            )
        except Exception:
            pass

    try:
        from eurika.api.chat import _append_chat_history_safe

        _append_chat_history_safe(root, "assistant", text, None)
    except Exception:
        pass

    return {"ok": True, "text": text, "decision": choice, "n": count}


def is_apply_result_question(text: str) -> bool:
    """True when the user asks whether the last apply/approve worked.

    Does **not** steal goal reflection («что получилось?» / «итог цели»).
    """
    msg = " ".join((text or "").strip().lower().split())
    if not msg:
        return False
    goal_phrases = (
        "что получилось",
        "итог цели",
        "итог выполнения",
        "результат цели",
        "как прошла цель",
        "goal reflection",
        "what was the outcome",
        "what happened with the goal",
    )
    if any(g in msg for g in goal_phrases):
        return False
    needles = (
        "статус apply",
        "apply approved",
        "apply-approved",
        "run apply",
        "проверить apply",
        "verify успех",
        "verify success",
        "получилось?",
        "а получилось",
        "ну получилось",
    )
    if any(n in msg for n in needles):
        return True
    if msg in {"получилось", "получилось?", "получилось ли?"}:
        return True
    if "approve" in msg and any(w in msg for w in ("ok", "успех", "выйшло", "сработало")):
        return True
    return False
