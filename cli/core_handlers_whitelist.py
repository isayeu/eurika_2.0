"""Whitelist-draft and campaign-undo handlers (P0.4 split)."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .core_handlers_common import _WHITELIST_DRAFT_ALLOWED_KINDS, _check_path, _err


def handle_whitelist_draft(args: Any) -> int:
    """Generate operation whitelist draft from campaign success candidates."""
    from eurika.storage import SessionMemory

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1

    output_path = getattr(args, "output", None)
    if output_path is None:
        output_path = path / ".eurika" / "operation_whitelist.draft.json"
    elif not output_path.is_absolute():
        output_path = path / output_path

    min_success = int(getattr(args, "min_success", 2) or 2)
    allow_auto = bool(getattr(args, "allow_auto", False))
    all_kinds = bool(getattr(args, "all_kinds", False))
    raw_kinds = str(getattr(args, "kinds", "extract_block_to_helper") or "")
    kind_filter = {part.strip() for part in raw_kinds.split(",") if part.strip()}
    unknown_kinds = sorted(k for k in kind_filter if k not in _WHITELIST_DRAFT_ALLOWED_KINDS)
    if unknown_kinds:
        _err(
            "unknown --kinds values: "
            + ", ".join(unknown_kinds)
            + f". Allowed: {', '.join(sorted(_WHITELIST_DRAFT_ALLOWED_KINDS))}"
        )
        return 1

    mem = SessionMemory(path)
    raw = mem._load()
    campaign = raw.get("campaign") or {}
    success_keys = [str(k) for k in (campaign.get("verify_success_keys") or [])]
    fail_keys = [str(k) for k in (campaign.get("verify_fail_keys") or [])]
    success_counts = Counter(success_keys)
    fail_counts = Counter(fail_keys)

    candidates = sorted(mem.campaign_whitelist_candidates(min_success=min_success))
    operations: list[dict[str, Any]] = []
    for key in candidates:
        parts = key.split("|", 2)
        if len(parts) != 3:
            continue
        target_file, kind, location = parts
        if not target_file or not kind:
            continue
        if not all_kinds and kind_filter and kind not in kind_filter:
            continue
        item: dict[str, Any] = {
            "kind": kind,
            "target_file": target_file,
            "allow_in_hybrid": True,
            "allow_in_auto": allow_auto,
            "evidence": {
                "verify_success_count": int(success_counts.get(key, 0)),
                "verify_fail_count": int(fail_counts.get(key, 0)),
                "source": "campaign_memory",
            },
        }
        if location:
            item["location"] = location
        operations.append(item)

    payload = {
        "meta": {
            "generated_by": "eurika whitelist-draft",
            "min_success": min_success,
            "allow_auto": allow_auto,
            "all_kinds": all_kinds,
            "kinds": sorted(kind_filter) if kind_filter else [],
            "candidates_count": len(operations),
        },
        "operations": operations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"written": str(output_path), "operations": len(operations)}, ensure_ascii=False))
    return 0


def handle_campaign_undo(args: Any) -> int:
    """Undo campaign checkpoint (ROADMAP 3.6.4)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.storage.campaign_checkpoint import list_campaign_checkpoints, undo_campaign_checkpoint

    if getattr(args, "list", False):
        info = list_campaign_checkpoints(path)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    out = undo_campaign_checkpoint(path, checkpoint_id=getattr(args, "checkpoint_id", None))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if out.get("errors") else 0
