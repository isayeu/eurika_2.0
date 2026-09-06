"""C.14 v1.5 bug-hunt: one real smell op → sandbox verify → Approvals (HITL).

Never applies on main. Web search only enriches the op description.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from eurika.orchestration.team_mode import PENDING_PLAN_FILE, has_pending_plan, save_pending_plan

BUG_HUNT_DRILL = "bug_hunt"
STAMP_NAME = "bug_hunt.json"
RECENT_PROPOSE_MAX = 8
SAFE_KINDS: frozenset[str] = frozenset(
    {
        "extract_nested_function",
        "extract_block_to_helper",
        "remove_unused_import",
    }
)
LLM_KIND = "llm_extract_block"


def stamp_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / STAMP_NAME


def load_bug_hunt_stamp(project_root: str | Path) -> dict[str, Any]:
    path = stamp_path(project_root)
    if not path.is_file():
        return {}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def recent_propose_keys(project_root: str | Path) -> set[tuple[str, str]]:
    """Recently parked (target, kind) pairs — anti-repeat for idle/manual."""
    blob = load_bug_hunt_stamp(project_root)
    raw = blob.get("recent") if isinstance(blob, dict) else None
    out: set[tuple[str, str]] = set()
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        tf = str(row.get("target_file") or "").replace("\\", "/")
        kind = str(row.get("kind") or "")
        if tf and kind:
            out.add((tf, kind))
    return out


def remember_bug_hunt_propose(
    project_root: str | Path,
    *,
    target_file: str,
    kind: str,
) -> None:
    """Record a parked proposal so the next pick prefers a different target."""
    import json
    import time

    root = Path(project_root).resolve()
    path = stamp_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = load_bug_hunt_stamp(root)
    recent = list(blob.get("recent") or []) if isinstance(blob.get("recent"), list) else []
    tf = str(target_file or "").replace("\\", "/")
    kd = str(kind or "")
    if tf and kd:
        recent = [r for r in recent if not (
            isinstance(r, dict)
            and str(r.get("target_file") or "").replace("\\", "/") == tf
            and str(r.get("kind") or "") == kd
        )]
        recent.insert(
            0,
            {
                "target_file": tf,
                "kind": kd,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
    blob["recent"] = recent[:RECENT_PROPOSE_MAX]
    blob["last_target"] = tf
    blob["last_kind"] = kd
    blob["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def smoke_bug_hunt_change(
    *,
    before: str,
    after: str,
    operation: dict[str, Any],
    modified: list[Any] | None = None,
) -> dict[str, Any]:
    """Require a real content change + kind-aware markers (post-compile)."""
    target = str(operation.get("target_file") or "").replace("\\", "/")
    kind = str(operation.get("kind") or "")
    mods = [str(x).replace("\\", "/") for x in (modified or [])]
    if before == after:
        return {"ok": False, "error": "bug_hunt: file unchanged after apply"}
    if mods and target and target not in mods and not any(target.endswith(m) or m.endswith(target) for m in mods):
        # Still ok if content changed; patch_apply may report basename-only.
        pass
    if kind == "extract_block_to_helper":
        if "def _extracted_block_" not in after and after.count("\ndef ") <= before.count("\ndef "):
            return {
                "ok": False,
                "error": "bug_hunt: extract_block expected new helper def",
            }
    elif kind == "extract_nested_function":
        params = operation.get("params") if isinstance(operation.get("params"), dict) else {}
        nested = str(params.get("nested_function_name") or "").strip()
        if nested:
            needle = f"def {nested}"
            if needle not in after:
                return {"ok": False, "error": f"bug_hunt: missing extracted `{nested}`"}
            # Prefer module-level: first occurrence should not be more indented than before parent
            # Soft check: at least one top-level-ish def (starts at column 0).
            if f"\ndef {nested}" not in after and not after.startswith(f"def {nested}"):
                return {
                    "ok": False,
                    "error": f"bug_hunt: `{nested}` not at module level",
                }
        elif after.count("\ndef ") < before.count("\ndef "):
            return {"ok": False, "error": "bug_hunt: extract_nested reduced def count unexpectedly"}
    elif kind == "remove_unused_import":
        # Content already differs; import-line heuristics are brittle on first-line imports.
        pass
    elif kind == LLM_KIND:
        if "def " not in after:
            return {"ok": False, "error": "bug_hunt: llm_extract left no defs"}
    return {"ok": True}


def bug_hunt_web_enabled(*, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = os.environ.get("EURIKA_BUG_HUNT_WEB", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _llm_extract_allowed() -> bool:
    raw = os.environ.get("EURIKA_USE_LLM_EXTRACT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_polygon_target(target: str) -> bool:
    rel = str(target or "").replace("\\", "/").lstrip("./")
    return rel.startswith("eurika/polygon/")


def _deny_keys(project_root: Path) -> set[tuple[str, str]]:
    """(target_file, kind) pairs to skip from KPI deny + recent failures."""
    out: set[tuple[str, str]] = set()
    try:
        from eurika.api.learning_api import get_learning_insights

        insights = get_learning_insights(project_root, top_n=8, polygon_only=False)
        recs = insights.get("recommendations") if isinstance(insights, dict) else {}
        if isinstance(recs, dict):
            for item in recs.get("policy_deny_candidates") or []:
                if not isinstance(item, dict):
                    continue
                tf = str(item.get("target_file") or "").replace("\\", "/")
                kind = str(item.get("action_kind") or item.get("kind") or "")
                if tf and kind:
                    out.add((tf, kind))
    except Exception:
        pass
    try:
        from eurika.storage.experience_store import get_recent_failures_enriched

        for row in get_recent_failures_enriched(project_root, limit=8):
            if not isinstance(row, dict):
                continue
            tf = str(row.get("target_file") or "").replace("\\", "/")
            kind = str(row.get("kind") or "")
            if tf and kind:
                out.add((tf, kind))
    except Exception:
        pass
    return out


def _prefer_keys(project_root: Path) -> set[tuple[str, str]]:
    """(target_file, kind) from what_worked / prioritized pairs."""
    out: set[tuple[str, str]] = set()
    try:
        from eurika.api.learning_api import get_learning_insights

        insights = get_learning_insights(project_root, top_n=8, polygon_only=False)
        if not isinstance(insights, dict):
            return out
        for item in insights.get("what_worked") or []:
            if not isinstance(item, dict):
                continue
            tf = str(item.get("target_file") or "").replace("\\", "/")
            kind = str(item.get("action_kind") or item.get("kind") or "")
            if tf and kind and not _is_polygon_target(tf):
                out.add((tf, kind))
        for item in insights.get("prioritized_smell_actions") or []:
            if not isinstance(item, dict):
                continue
            # smell|action only — boost any op with matching kind later via score
            kind = str(item.get("action_kind") or "")
            if kind:
                out.add(("*", kind))
    except Exception:
        pass
    return out


def _score_op(op: dict[str, Any], *, prefer: set[tuple[str, str]]) -> int:
    tf = str(op.get("target_file") or "").replace("\\", "/")
    kind = str(op.get("kind") or "")
    score = 0
    if kind in SAFE_KINDS:
        score += 10
    if (tf, kind) in prefer:
        score += 50
    if ("*", kind) in prefer:
        score += 5
    if kind == LLM_KIND:
        score -= 20
    return score


def filter_bug_hunt_candidates(
    operations: list[dict[str, Any]],
    *,
    deny: set[tuple[str, str]] | None = None,
    allow_llm: bool | None = None,
) -> list[dict[str, Any]]:
    """Drop polygon / denied / unsafe LLM ops; keep HITL-safe kinds."""
    llm_ok = _llm_extract_allowed() if allow_llm is None else bool(allow_llm)
    blocked = deny if deny is not None else set()
    out: list[dict[str, Any]] = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        tf = str(op.get("target_file") or "").replace("\\", "/")
        kind = str(op.get("kind") or "")
        if not tf or not kind:
            continue
        if _is_polygon_target(tf):
            continue
        if (tf, kind) in blocked:
            continue
        if kind == LLM_KIND:
            if not llm_ok:
                continue
        elif kind not in SAFE_KINDS:
            continue
        out.append(op)
    return out


def pick_bug_hunt_operation(
    project_root: Path,
    *,
    operations: list[dict[str, Any]] | None = None,
    allow_llm: bool | None = None,
) -> dict[str, Any] | None:
    """Pick one non-polygon smell op ranked by learning insights."""
    root = Path(project_root).resolve()
    if operations is None:
        from eurika.api.ops import get_code_smell_operations

        operations = list(get_code_smell_operations(root) or [])
    deny = _deny_keys(root)
    recent = recent_propose_keys(root)
    prefer = _prefer_keys(root)
    candidates = filter_bug_hunt_candidates(
        list(operations), deny=deny | recent, allow_llm=allow_llm
    )
    if not candidates and recent:
        # Nothing fresh left — allow a repeat rather than stall idle forever.
        candidates = filter_bug_hunt_candidates(
            list(operations), deny=deny, allow_llm=allow_llm
        )
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda op: (-_score_op(op, prefer=prefer), str(op.get("target_file") or "")),
    )
    return dict(ranked[0])


def _enrich_with_web(op: dict[str, Any]) -> dict[str, Any]:
    """Best-effort web note into description; never raises; never writes a patch."""
    enriched = dict(op)
    try:
        from eurika.utils.web_search import search_web, web_search_enabled

        if not web_search_enabled():
            return enriched
        kind = str(op.get("kind") or "refactor")
        smell = str(op.get("smell_type") or "")
        target = str(op.get("target_file") or "")
        query = f"python {smell} {kind} refactor {Path(target).name}".strip()
        results, _provider, _note = search_web(query, max_results=3)
        if not results:
            return enriched
        bits = []
        for row in results[:3]:
            title = getattr(row, "title", "") or ""
            url = getattr(row, "url", "") or ""
            snippet = (getattr(row, "snippet", "") or "")[:160]
            if title or url:
                bits.append(f"- {title}: {url}" + (f" — {snippet}" if snippet else ""))
        if not bits:
            return enriched
        note = "Web research (informational, not applied):\n" + "\n".join(bits)
        desc = str(enriched.get("description") or "").strip()
        enriched["description"] = f"{desc}\n\n{note}".strip() if desc else note
        enriched["research_note"] = note
    except Exception:
        return enriched
    return enriched


def _materialize_target(main_root: Path, sandbox_root: Path, target_rel: str) -> None:
    """Ensure target exists in sandbox (needed for copy-mode empty trees)."""
    rel = str(target_rel or "").replace("\\", "/").lstrip("./")
    if not rel:
        raise RuntimeError("bug-hunt: empty target_file")
    src = main_root / rel
    dst = sandbox_root / rel
    if dst.is_file():
        return
    if not src.is_file():
        raise RuntimeError(f"bug-hunt: missing target on main: {rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def format_bug_hunt_summary(payload: dict[str, Any]) -> str:
    """Human-readable summary for CLI / Chat."""
    if not payload.get("ok"):
        err = payload.get("error") or "unknown error"
        return f"Bug-hunt propose: fail — {err}"
    if payload.get("dry_run"):
        op = (payload.get("operations") or [{}])[0]
        return (
            "Bug-hunt dry-run (не записано):\n"
            f"- kind: `{op.get('kind')}`\n"
            f"- target: `{op.get('target_file')}`\n"
            f"- pending would be: `{PENDING_PLAN_FILE}`"
        )
    lines = [
        "Bug-hunt propose → Approvals (без apply на main):",
        f"- kind: `{payload.get('kind')}`",
        f"- target: `{payload.get('target_file')}`",
        f"- pending: `{payload.get('pending_plan') or PENDING_PLAN_FILE}`",
    ]
    if payload.get("sandbox"):
        lines.append(
            f"- sandbox: ok"
            + (f" ({payload.get('sandbox_mode')})" if payload.get("sandbox_mode") else "")
        )
    if payload.get("web"):
        lines.append("- web: research note attached to description")
    oss_n = int(payload.get("oss_examples") or 0)
    if oss_n:
        lines.append(f"- OSS examples on op: {oss_n}")
    elif payload.get("oss_missing"):
        lines.append(
            "- OSS: нет `.eurika/pattern_library.json` — "
            "«обнови паттерны» / `eurika learn-github . --light --limit-repos 2 --scan --build-patterns`"
        )
    lines.append(
        "Дальше: Approve в Approvals, затем `eurika fix . --apply-approved`."
    )
    return "\n".join(lines)


def run_bug_hunt_propose(
    project_root: Path,
    *,
    dry_run: bool = False,
    sandbox: bool = True,
    web: bool | None = None,
    keep_sandbox: bool = False,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pick one real-code op, optionally sandbox-verify, park in Approvals.

    Never applies on main. If ``sandbox`` and verify fails — do not write pending.
    """
    path = Path(project_root).resolve()
    base: dict[str, Any] = {
        "ok": False,
        "bug_hunt": True,
        "propose": True,
        "drill_id": BUG_HUNT_DRILL,
        "modified": [],
        "verify_success": None,
        "return_code": 1,
        "sandbox": bool(sandbox),
        "web": False,
    }
    if has_pending_plan(path):
        return {
            **base,
            "error": "pending_plan already exists — resolve Approvals first",
            "pending_plan": PENDING_PLAN_FILE,
        }

    picked = pick_bug_hunt_operation(path, operations=operations)
    if not picked:
        return {
            **base,
            "error": "no eligible non-polygon smell op (scan empty or all skipped)",
        }

    use_web = bug_hunt_web_enabled(explicit=web)
    operation = _enrich_with_web(picked) if use_web else dict(picked)
    operation.setdefault("approval_state", "pending")
    operation.setdefault("critic_verdict", "allow")
    operation.setdefault("decision_source", "bug_hunt_propose")
    operation.setdefault("team_decision", "pending")
    target_rel = str(operation.get("target_file") or "")
    kind = str(operation.get("kind") or "")
    oss_examples = operation.get("oss_examples")
    oss_n = len(oss_examples) if isinstance(oss_examples, list) else 0
    lib_path = path / ".eurika" / "pattern_library.json"
    oss_missing = not lib_path.is_file()

    if dry_run:
        return {
            **base,
            "ok": True,
            "dry_run": True,
            "kind": kind,
            "target_file": target_rel,
            "operations": [operation],
            "pending_plan": PENDING_PLAN_FILE,
            "return_code": 0,
            "web": use_web and bool(operation.get("research_note")),
            "oss_examples": oss_n,
            "oss_missing": oss_missing,
        }

    sandbox_meta: dict[str, Any] | None = None
    sandbox_verify: dict[str, Any] | None = None
    build_root = path
    try:
        if sandbox:
            from eurika.orchestration.propose_sandbox import (
                apply_and_smoke_verify,
                create_propose_sandbox,
                remove_propose_sandbox,
            )

            try:
                sandbox_meta = create_propose_sandbox(path, drill_id=BUG_HUNT_DRILL)
                build_root = Path(sandbox_meta["path"])
                _materialize_target(path, build_root, target_rel)
            except Exception as exc:
                return {
                    **base,
                    "error": f"sandbox create failed: {exc}",
                    "verify_success": False,
                }

            sandbox_verify = apply_and_smoke_verify(
                build_root, operation, drill_id=BUG_HUNT_DRILL
            )
            if not sandbox_verify.get("ok"):
                return {
                    **base,
                    "error": (
                        "sandbox verify failed: "
                        f"{sandbox_verify.get('error') or 'unknown'}"
                    ),
                    "sandbox_path": str(build_root),
                    "sandbox_mode": (sandbox_meta or {}).get("mode"),
                    "sandbox_verify": sandbox_verify,
                    "kind": kind,
                    "target_file": target_rel,
                    "verify_success": False,
                }

        operations_out = [operation]
        patch_plan = {
            "operations": operations_out,
            "source": "bug_hunt_propose",
            "summary": f"C.14 bug-hunt propose ({kind} → {target_rel})",
            "drill": BUG_HUNT_DRILL,
        }
        pending_path = save_pending_plan(
            path,
            patch_plan,
            operations_out,
            policy_decisions=[
                {"index": 1, "decision": "allow", "reason": "bug_hunt_propose"}
            ],
            session_id="bug_hunt_propose",
        )
        try:
            remember_bug_hunt_propose(path, target_file=target_rel, kind=kind)
        except Exception:
            pass
        try:
            pending_rel = str(pending_path.relative_to(path))
        except ValueError:
            pending_rel = str(pending_path)
        out: dict[str, Any] = {
            "ok": True,
            "bug_hunt": True,
            "propose": True,
            "drill_id": BUG_HUNT_DRILL,
            "kind": kind,
            "target_file": target_rel,
            "pending_plan": pending_rel,
            "pending_plan_path": str(pending_path),
            "operations": operations_out,
            "modified": [],
            "verify_success": True if sandbox else None,
            "return_code": 0,
            "sandbox": bool(sandbox),
            "web": use_web and bool(operation.get("research_note")),
            "oss_examples": oss_n,
            "oss_missing": oss_missing,
            "instructions": (
                "Review Approvals / .eurika/pending_plan.json, set team_decision=approve, "
                "then: eurika fix . --apply-approved"
            ),
        }
        if sandbox and sandbox_meta:
            out["sandbox_path"] = str(build_root)
            out["sandbox_mode"] = sandbox_meta.get("mode")
            out["sandbox_verify"] = sandbox_verify
            out["sandbox_kept"] = bool(keep_sandbox)
        return out
    finally:
        if sandbox and sandbox_meta and not keep_sandbox:
            from eurika.orchestration.propose_sandbox import remove_propose_sandbox

            try:
                remove_propose_sandbox(
                    path,
                    Path(sandbox_meta["path"]),
                    mode=str(sandbox_meta.get("mode") or ""),
                )
            except Exception:
                pass
