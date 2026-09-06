"""C.14 v1.5 bug-hunt CLI — real smell → sandbox → Approvals (no apply)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_bug_hunt(args: Any) -> int:
    from eurika.orchestration.bug_hunt import format_bug_hunt_summary, run_bug_hunt_propose

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    propose = bool(getattr(args, "propose", False))
    if not propose:
        print("bug-hunt: use --propose (sandbox → Approvals; never applies on main)")
        return 2
    dry_run = bool(getattr(args, "dry_run", False))
    sandbox = bool(getattr(args, "sandbox", True))
    if getattr(args, "no_sandbox", False):
        sandbox = False
    web = bool(getattr(args, "web", False))
    keep_sandbox = bool(getattr(args, "keep_sandbox", False))
    quiet = bool(getattr(args, "quiet", False))
    payload = run_bug_hunt_propose(
        path,
        dry_run=dry_run,
        sandbox=sandbox,
        web=web if web else None,
        keep_sandbox=keep_sandbox,
    )
    summary = format_bug_hunt_summary(payload)
    if quiet:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(summary)
        snippet = {
            "ok": payload.get("ok"),
            "kind": payload.get("kind"),
            "target_file": payload.get("target_file"),
            "pending_plan": payload.get("pending_plan"),
            "sandbox": payload.get("sandbox"),
            "return_code": payload.get("return_code"),
        }
        if payload.get("error"):
            snippet["error"] = payload.get("error")
        if payload.get("web"):
            snippet["web"] = True
        print()
        print(json.dumps(snippet, ensure_ascii=False, indent=2))
    return int(payload.get("return_code") if payload.get("return_code") is not None else (0 if payload.get("ok") else 1))
