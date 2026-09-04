"""Prove-cycle CLI handler — deterministic patch→verify→learning without LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_prove_cycle(args: Any) -> int:
    from eurika.orchestration.prove_cycle import format_prove_cycle_summary, run_prove_cycle

    path = Path(getattr(args, "path", ".") or ".").resolve()
    if _check_path(path) != 0:
        return 1
    dry_run = bool(getattr(args, "dry_run", False))
    propose = bool(getattr(args, "propose", False))
    quiet = bool(getattr(args, "quiet", False))
    timeout = getattr(args, "verify_timeout", None)
    payload = run_prove_cycle(
        path,
        dry_run=dry_run,
        quiet=quiet,
        verify_timeout=timeout,
        propose=propose,
    )
    summary = format_prove_cycle_summary(payload)
    if quiet:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(summary)
        if not dry_run:
            print()
            snippet = {
                "verify_success": payload.get("verify_success"),
                "modified": payload.get("modified"),
                "return_code": payload.get("return_code"),
            }
            if propose:
                snippet["propose"] = True
                snippet["pending_plan"] = payload.get("pending_plan")
                snippet["target_file"] = payload.get("target_file")
            print(json.dumps(snippet, ensure_ascii=False, indent=2))
    rc = payload.get("return_code")
    if rc is None:
        if propose:
            rc = 0 if payload.get("ok", True) else 1
        else:
            rc = 0 if payload.get("verify_success") else 1
    return int(rc)
