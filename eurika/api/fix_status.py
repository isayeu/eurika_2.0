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
