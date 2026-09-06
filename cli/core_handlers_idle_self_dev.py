"""CLI: idle-self-dev — C.14 propose+sandbox when LLM lease is quiet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_idle_self_dev(args: Any) -> int:
    from eurika.orchestration.idle_self_dev import maybe_run, status

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    quiet = bool(getattr(args, "quiet", False))
    if bool(getattr(args, "prune_sandboxes", False)):
        from eurika.orchestration.propose_sandbox import prune_propose_sandboxes

        payload = prune_propose_sandboxes(path, keep_latest=0)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0 if payload.get("ok", True) else 1
    do_status = bool(getattr(args, "status", False))
    if do_status and not bool(getattr(args, "once", False)):
        payload = status(path)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    force = bool(getattr(args, "force", False))
    keep_sandbox = bool(getattr(args, "keep_sandbox", False))
    payload = maybe_run(
        path,
        force=force,
        keep_sandbox=keep_sandbox,
        market_llm_enabled=bool(getattr(args, "yield_market_llm", False)),
        portfolio_enabled=bool(getattr(args, "yield_portfolio", False)),
    )
    if quiet:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        if payload.get("skipped"):
            print(f"idle-self-dev: skipped ({payload.get('skipped')})")
        else:
            print(payload.get("message") or json.dumps(payload, ensure_ascii=False, default=str))
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if payload.get("skipped"):
        return 0
    return 0 if payload.get("ok", True) else 1
