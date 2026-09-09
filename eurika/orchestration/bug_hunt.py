"""C.14 v1.5 bug-hunt: one real smell op → sandbox verify → Approvals (HITL).

Never applies on main. Web search only enriches the op description.
"""

from __future__ import annotations

import ast
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
        discarded = _bare_extracted_calls_discarding_return(after)
        if discarded:
            return {
                "ok": False,
                "error": (
                    "bug_hunt: extract call discards helper result "
                    f"(bare `{discarded[0]}()` — expected assign)"
                ),
            }
        lost = _bare_extracted_calls_with_lost_name_assigns(after)
        if lost:
            return {
                "ok": False,
                "error": (
                    "bug_hunt: extract call discards helper result "
                    f"(bare `{lost[0]}()` assigns locals without return)"
                ),
            }
        missing_ret = _extracted_helpers_missing_return(after)
        if missing_ret:
            return {
                "ok": False,
                "error": (
                    "bug_hunt: helper "
                    f"`{missing_ret[0]}` has no return but result is assigned"
                ),
            }
        churn = _extract_diff_line_count(before, after)
        if churn > 80:
            return {
                "ok": False,
                "error": (
                    "bug_hunt: extract formatting churn "
                    f"({churn} diff lines; expected surgical edit)"
                ),
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
        churn = _extract_diff_line_count(before, after)
        if churn > 80:
            return {
                "ok": False,
                "error": (
                    "bug_hunt: extract formatting churn "
                    f"({churn} diff lines; expected surgical edit)"
                ),
            }
    elif kind == "remove_unused_import":
        # Content already differs; import-line heuristics are brittle on first-line imports.
        pass
    elif kind == LLM_KIND:
        if "def " not in after:
            return {"ok": False, "error": "bug_hunt: llm_extract left no defs"}
    return {"ok": True}


def _extract_diff_line_count(before: str, after: str) -> int:
    import difflib

    return sum(
        1
        for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm=""
        )
        if line.startswith("+") or line.startswith("-")
    )


def _extracted_helper_defs(source: str) -> dict[str, ast.FunctionDef]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_extracted_block_"):
            out[node.name] = node
    return out


def _bare_extracted_block_call_names(source: str) -> list[str]:
    """Names of ``_extracted_block_*`` called as a bare Expr (result discarded)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["<syntax>"]
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Name) and func.id.startswith("_extracted_block_"):
            found.append(func.id)
    return found


def _bare_extracted_calls_discarding_return(source: str) -> list[str]:
    """Bare calls to helpers that ``return`` a value (call site must assign)."""
    helpers = _extracted_helper_defs(source)
    bad: list[str] = []
    for name in _bare_extracted_block_call_names(source):
        helper = helpers.get(name)
        if helper is None:
            continue
        if any(isinstance(n, ast.Return) for n in ast.walk(helper)):
            bad.append(name)
    return bad


def _names_assigned_simple(helper: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(helper):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            names.add(node.target.id)
    return names


def _bare_extracted_calls_with_lost_name_assigns(source: str) -> list[str]:
    """Bare calls that drop values the parent still reads after the call.

    Side-effect extracts (write file, mutate params) with internal temps and no
    return are OK. Fail when a helper binds ``name = …`` without return and the
    enclosing function still loads ``name`` (outside the helper def).
    """
    helpers = _extracted_helper_defs(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    bad: list[str] = []

    def _loads_in(node: ast.AST, *, skip: ast.AST | None = None) -> set[str]:
        skip_ids = {id(n) for n in ast.walk(skip)} if skip is not None else set()
        out: set[str] = set()
        for sub in ast.walk(node):
            if id(sub) in skip_ids:
                continue
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                out.add(sub.id)
        return out

    def _scan_block(stmts: list[ast.stmt], parent_fn: ast.AST) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                _scan_block(list(stmt.body), parent_fn)
                _scan_block(list(stmt.orelse or []), parent_fn)
                continue
            if isinstance(stmt, (ast.For, ast.While, ast.With, ast.AsyncWith, ast.AsyncFor)):
                _scan_block(list(stmt.body), parent_fn)
                _scan_block(list(getattr(stmt, "orelse", None) or []), parent_fn)
                continue
            if isinstance(stmt, ast.Try):
                _scan_block(list(stmt.body), parent_fn)
                for h in stmt.handlers:
                    _scan_block(list(h.body), parent_fn)
                _scan_block(list(stmt.orelse or []), parent_fn)
                _scan_block(list(stmt.finalbody or []), parent_fn)
                continue
            if not (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id.startswith("_extracted_block_")
            ):
                continue
            name = stmt.value.func.id
            helper = helpers.get(name)
            if helper is None:
                continue
            if any(isinstance(n, ast.Return) for n in ast.walk(helper)):
                continue
            assigned = _names_assigned_simple(helper)
            if not assigned:
                continue
            parent_loads = _loads_in(parent_fn, skip=helper)
            if assigned & parent_loads:
                bad.append(name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only scan this function's body; nested defs are visited separately.
            _scan_block(list(node.body), node)

    out: list[str] = []
    seen: set[str] = set()
    for name in bad:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _extracted_helpers_missing_return(source: str) -> list[str]:
    """Helpers whose result is assigned but the def has no ``return``."""
    helpers = _extracted_helper_defs(source)
    missing: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["<syntax>"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        val = node.value
        if not isinstance(val, ast.Call) or not isinstance(val.func, ast.Name):
            continue
        name = val.func.id
        helper = helpers.get(name)
        if helper is None or not name.startswith("_extracted_block_"):
            continue
        if not any(isinstance(n, ast.Return) for n in ast.walk(helper)):
            missing.append(name)
    return missing


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


def _is_market_freeze_target(target: str) -> bool:
    """Ops window: do not park HITL refactors under Market ML (VISION freeze)."""
    rel = str(target or "").replace("\\", "/").lstrip("./")
    return rel.startswith("eurika/ml/")


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


def _score_op(
    op: dict[str, Any],
    *,
    prefer: set[tuple[str, str]],
    caution_kinds: set[str] | None = None,
    caution_weights: dict[str, int] | None = None,
    prefer_safe_delta: int = 0,
    planning_signals: dict[str, Any] | None = None,
) -> int:
    tf = str(op.get("target_file") or "").replace("\\", "/")
    kind = str(op.get("kind") or "")
    score = 0
    if kind in SAFE_KINDS:
        score += 10
        if prefer_safe_delta:
            score += int(prefer_safe_delta)
    if (tf, kind) in prefer:
        score += 50
    if ("*", kind) in prefer:
        score += 5
    if kind == LLM_KIND:
        score -= 20
    # Multi-hypothesis ranking v0: confidence-scaled caution (not deny).
    if caution_weights and kind in caution_weights:
        try:
            score += int(caution_weights[kind])
        except (TypeError, ValueError):
            score -= 40
    elif caution_kinds and kind in caution_kinds:
        score -= 40
    # Planning coupling v0: A/B + verify_by_kind soft deltas (not deny / not apply).
    if planning_signals:
        try:
            from eurika.api.planning_coupling import score_delta_for_kind

            delta, _stamp = score_delta_for_kind(kind, planning_signals)
            score += int(delta)
        except Exception:
            pass
    return score


def _target_exists_on_main(project_root: Path, target: str) -> bool:
    rel = str(target or "").replace("\\", "/").lstrip("./")
    if not rel or ".." in Path(rel).parts:
        return False
    return (Path(project_root).resolve() / rel).is_file()


def filter_bug_hunt_candidates(
    operations: list[dict[str, Any]],
    *,
    deny: set[tuple[str, str]] | None = None,
    allow_llm: bool | None = None,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Drop polygon / denied / unsafe LLM ops; keep HITL-safe kinds."""
    llm_ok = _llm_extract_allowed() if allow_llm is None else bool(allow_llm)
    blocked = deny if deny is not None else set()
    root = Path(project_root).resolve() if project_root is not None else None
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
        if _is_market_freeze_target(tf):
            continue
        if root is not None and not _target_exists_on_main(root, tf):
            continue
        if (tf, kind) in blocked:
            continue
        if kind == LLM_KIND:
            if not llm_ok:
                continue
        elif kind not in SAFE_KINDS:
            continue
        if kind in {"extract_block_to_helper", "extract_nested_function"} and _is_trivial_extract_block_op(op):
            continue
        out.append(op)
    return out


def _is_trivial_extract_block_op(op: dict[str, Any]) -> bool:
    """Skip micro-extracts (e.g. 3 dict assignments → `_extracted_block_*`)."""
    kind = str(op.get("kind") or "")
    params = op.get("params") if isinstance(op.get("params"), dict) else {}
    line_count = params.get("line_count")
    try:
        if line_count is not None and int(line_count) < 5:
            return True
    except (TypeError, ValueError):
        pass
    desc = str(op.get("description") or "")
    # Descriptions look like: "... (line 59, 3 lines) ..." or "... (_finalize) (3 lines)"
    import re

    m = re.search(r",\s*(\d+)\s+lines?\)", desc) or re.search(
        r"\((\d+)\s+lines?\)", desc
    )
    if m and int(m.group(1)) < 5:
        return True
    if kind == "extract_nested_function" and not line_count:
        # Fall back to description-only size gate above.
        pass
    return False


def pick_bug_hunt_operation(
    project_root: Path,
    *,
    operations: list[dict[str, Any]] | None = None,
    allow_llm: bool | None = None,
) -> dict[str, Any] | None:
    """Pick one non-polygon smell op ranked by learning insights."""
    ranked = list_bug_hunt_candidates(
        project_root, operations=operations, allow_llm=allow_llm
    )
    return dict(ranked[0]) if ranked else None


def list_bug_hunt_candidates(
    project_root: Path,
    *,
    operations: list[dict[str, Any]] | None = None,
    allow_llm: bool | None = None,
) -> list[dict[str, Any]]:
    """Ranked eligible ops (best first)."""
    root = Path(project_root).resolve()
    if operations is None:
        from eurika.api.ops import get_code_smell_operations

        operations = list(get_code_smell_operations(root) or [])
    deny = _deny_keys(root)
    recent = recent_propose_keys(root)
    prefer = _prefer_keys(root)
    caution_kinds: set[str] = set()
    caution_weights: dict[str, int] = {}
    prefer_safe_delta = 0
    try:
        from eurika.api.hypothesis_engine import hypothesis_ranking_signals

        hyp_signals = hypothesis_ranking_signals(root)
        raw_w = hyp_signals.get("caution_weights")
        if isinstance(raw_w, dict):
            caution_weights = {
                str(k): int(v) for k, v in raw_w.items() if k is not None
            }
            caution_kinds = set(caution_weights.keys())
        prefer_safe_delta = int(hyp_signals.get("prefer_safe_delta") or 0)
    except Exception:
        try:
            from eurika.api.hypothesis_engine import caution_action_kinds

            caution_kinds = caution_action_kinds(root)
        except Exception:
            caution_kinds = set()
    planning_signals: dict[str, Any] | None = None
    try:
        from eurika.api.planning_coupling import load_planning_signals

        planning_signals = load_planning_signals(root)
    except Exception:
        planning_signals = None
    candidates = filter_bug_hunt_candidates(
        list(operations), deny=deny | recent, allow_llm=allow_llm, project_root=root
    )
    if not candidates and recent:
        # Nothing fresh left — allow a repeat rather than stall idle forever.
        candidates = filter_bug_hunt_candidates(
            list(operations), deny=deny, allow_llm=allow_llm, project_root=root
        )
    if not candidates:
        return []
    ranked = sorted(
        candidates,
        key=lambda op: (
            -_score_op(
                op,
                prefer=prefer,
                caution_kinds=caution_kinds,
                caution_weights=caution_weights,
                prefer_safe_delta=prefer_safe_delta,
                planning_signals=planning_signals,
            ),
            str(op.get("target_file") or ""),
        ),
    )
    # Stamp ranking hints for summaries (not an apply gate).
    stamped: list[dict[str, Any]] = []
    for op in ranked:
        kind = str(op.get("kind") or "")
        row = dict(op)
        if caution_kinds and kind in caution_kinds:
            row["hypothesis_caution"] = True
            row["hypothesis_caution_kind"] = kind
            if kind in caution_weights:
                row["hypothesis_caution_delta"] = caution_weights[kind]
            row["hypothesis_ranking_v0"] = True
        if prefer_safe_delta and kind in SAFE_KINDS:
            row["hypothesis_prefer_safe_delta"] = prefer_safe_delta
            row["hypothesis_ranking_v0"] = True
        stamped.append(row)
    if planning_signals:
        try:
            from eurika.api.planning_coupling import stamp_planning_on_ops

            stamped = stamp_planning_on_ops(stamped, planning_signals)
        except Exception:
            pass
    return stamped


def _preflight_bug_hunt_op(project_root: Path, operation: dict[str, Any]) -> str | None:
    """Return error if the op would no-op on main; None if ok to sandbox."""
    kind = str(operation.get("kind") or "")
    rel = str(operation.get("target_file") or "").replace("\\", "/").lstrip("./")
    if not rel:
        return "empty target_file"
    path = Path(project_root).resolve() / rel
    if not path.is_file():
        return f"missing target on main: {rel}"
    params = operation.get("params") if isinstance(operation.get("params"), dict) else {}
    if kind == "extract_block_to_helper":
        parent = str(params.get("location") or "").strip()
        helper = str(params.get("helper_name") or "").strip()
        try:
            line = int(params.get("block_start_line") or 0)
        except (TypeError, ValueError):
            line = 0
        if not parent or not helper or line < 1:
            return "extract_block params incomplete"
        try:
            from eurika.refactor.extract_function import extract_block_to_helper

            before = path.read_text(encoding="utf-8")
            after = extract_block_to_helper(
                path,
                parent,
                line,
                helper,
                list(params.get("extra_params") or [])
                if isinstance(params.get("extra_params"), list)
                else None,
            )
        except Exception as exc:
            return f"extract preflight error: {exc}"
        if after is None:
            return "extract_block returned None (would no-op)"
        if after == before:
            return "extract_block left file unchanged"
        if _extracted_helper_is_call_wrapper(after, helper):
            return "extract_block is a trivial single-call wrapper"
        if _extracted_helper_is_presentation(after, helper):
            return "extract_block is a trivial presentation/message builder"
        if _extracted_helper_is_guard(after, helper):
            return "extract_block is a trivial guard/validation wrapper"
        if _extracted_helper_returns_loop_target(after, helper):
            return "extract_block returns a for/with loop target"
        smoke = smoke_bug_hunt_change(
            before=before,
            after=after,
            operation=operation,
            modified=[rel],
        )
        if not smoke.get("ok"):
            return str(smoke.get("error") or "extract smoke failed")
        return None
    if kind == "extract_nested_function":
        parent = str(params.get("location") or "").strip()
        nested = str(params.get("nested_function_name") or "").strip()
        if not parent or not nested:
            return "extract_nested params incomplete"
        try:
            lc = int(params.get("line_count") or 0)
        except (TypeError, ValueError):
            lc = 0
        if lc and lc < 5:
            return f"extract_nested too small ({lc} lines)"
        try:
            from eurika.refactor.extract_function import extract_nested_function

            before = path.read_text(encoding="utf-8")
            after = extract_nested_function(
                path,
                parent,
                nested,
                list(params.get("extra_params") or [])
                if isinstance(params.get("extra_params"), list)
                else None,
            )
        except Exception as exc:
            return f"extract_nested preflight error: {exc}"
        if after is None:
            return "extract_nested returned None (would no-op)"
        if after == before:
            return "extract_nested left file unchanged"
        smoke = smoke_bug_hunt_change(
            before=before,
            after=after,
            operation=operation,
            modified=[rel],
        )
        if not smoke.get("ok"):
            return str(smoke.get("error") or "extract_nested smoke failed")
        return None
    return None


def _extracted_helper_is_call_wrapper(source: str, helper_name: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == helper_name:
            from eurika.refactor.extract_function import _is_trivial_call_wrapper_body

            return _is_trivial_call_wrapper_body(list(node.body))
    return False


def _extracted_helper_is_presentation(source: str, helper_name: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == helper_name:
            from eurika.refactor.extract_function import _is_trivial_presentation_body

            return _is_trivial_presentation_body(list(node.body))
    return False


def _extracted_helper_is_guard(source: str, helper_name: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == helper_name:
            from eurika.refactor.extract_function import _is_trivial_guard_body

            return _is_trivial_guard_body(list(node.body))
    return False


def _extracted_helper_returns_loop_target(source: str, helper_name: str) -> bool:
    """True if helper ``return name`` where ``name`` is a for/with target in the helper."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    from eurika.refactor.extract_function import _loop_target_names_in_statements

    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name == helper_name):
            continue
        loop_names = _loop_target_names_in_statements(list(node.body))
        for stmt in node.body:
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name):
                if stmt.value.id in loop_names:
                    return True
    return False


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
        if not isinstance(op, dict):
            op = {}
        lines = [
            "Bug-hunt dry-run (не записано):",
            f"- kind: `{op.get('kind')}`",
            f"- target: `{op.get('target_file')}`",
            f"- pending would be: `{PENDING_PLAN_FILE}`",
        ]
        if op.get("hypothesis_caution") or payload.get("hypothesis_caution"):
            lines.append(
                f"- hypothesis caution: kind `{op.get('hypothesis_caution_kind') or op.get('kind')}`"
            )
        if op.get("planning_coupling_v0") or payload.get("planning_coupling_v0"):
            src = op if op.get("planning_coupling_v0") else payload
            lines.append(
                f"- planning coupling v0: score_delta={src.get('planning_score_delta')} "
                f"ab={src.get('planning_ab_bias')} verify_rate={src.get('planning_verify_rate')}"
            )
        return "\n".join(lines)
    lines = [
        "Bug-hunt propose → Approvals (без apply на main):",
        f"- kind: `{payload.get('kind')}`",
        f"- target: `{payload.get('target_file')}`",
        f"- pending: `{payload.get('pending_plan') or PENDING_PLAN_FILE}`",
    ]
    if payload.get("hypothesis_caution"):
        lines.append(
            f"- hypothesis caution: kind `{payload.get('hypothesis_caution_kind') or payload.get('kind')}` "
            f"delta={payload.get('hypothesis_caution_delta', -40)} "
            "(reject_pattern ranking; still proposed only as fallback)"
        )
    if payload.get("planning_coupling_v0"):
        bits = []
        if payload.get("planning_ab_bias"):
            bits.append(
                f"ab={payload.get('planning_ab_bias')}({payload.get('planning_ab_delta')})"
            )
        if payload.get("planning_verify_rate") is not None:
            bits.append(
                f"verify_rate={payload.get('planning_verify_rate')}"
                f"({payload.get('planning_verify_delta')})"
            )
        if bits:
            lines.append(
                f"- planning coupling v0: {', '.join(bits)} "
                f"(score_delta={payload.get('planning_score_delta')}; not apply gate)"
            )
    if payload.get("sandbox"):
        lines.append(
            f"- sandbox: ok"
            + (f" ({payload.get('sandbox_mode')})" if payload.get("sandbox_mode") else "")
        )
    ab = payload.get("ab_v0")
    if isinstance(ab, dict) and ab.get("winner"):
        lines.append(
            f"- A/B v0: winner=`{ab.get('winner')}` "
            f"(smoke_ok={ab.get('smoke_ok')}, graph_unchanged={ab.get('graph_unchanged')}, "
            f"rescanned={ab.get('rescanned')}, metrics_stable={ab.get('metrics_stable')})"
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
    max_attempts: int = 24,
) -> dict[str, Any]:
    """Pick one real-code op, optionally sandbox-verify, park in Approvals.

    Never applies on main. If ``sandbox`` and verify fails — try the next ranked
    candidate (up to ``max_attempts``); do not write pending on total failure.
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
    if has_pending_plan(path) and not dry_run:
        return {
            **base,
            "error": "pending_plan already exists — resolve Approvals first",
            "pending_plan": PENDING_PLAN_FILE,
        }

    ranked = list_bug_hunt_candidates(path, operations=operations)
    if not ranked:
        return {
            **base,
            "error": "no eligible non-polygon smell op (scan empty or all skipped)",
        }

    use_web = bug_hunt_web_enabled(explicit=web)
    lib_path = path / ".eurika" / "pattern_library.json"
    oss_missing = not lib_path.is_file()
    attempts = max(1, int(max_attempts or 1))
    skipped: list[dict[str, Any]] = []
    last_error = "no candidate survived preflight/sandbox"

    for picked in ranked[:attempts]:
        operation = _enrich_with_web(picked) if use_web else dict(picked)
        operation.setdefault("approval_state", "pending")
        operation.setdefault("critic_verdict", "allow")
        operation.setdefault("decision_source", "bug_hunt_propose")
        operation.setdefault("team_decision", "pending")
        target_rel = str(operation.get("target_file") or "")
        kind = str(operation.get("kind") or "")
        oss_examples = operation.get("oss_examples")
        oss_n = len(oss_examples) if isinstance(oss_examples, list) else 0

        preflight_err = _preflight_bug_hunt_op(path, operation)
        if preflight_err:
            skipped.append({"target_file": target_rel, "kind": kind, "error": preflight_err})
            try:
                remember_bug_hunt_propose(path, target_file=target_rel, kind=kind)
            except Exception:
                pass
            last_error = f"preflight failed: {preflight_err}"
            continue

        if dry_run:
            dry_out: dict[str, Any] = {
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
                "skipped": skipped,
                "hypothesis_caution": bool(operation.get("hypothesis_caution")),
                "hypothesis_caution_kind": operation.get("hypothesis_caution_kind"),
            }
            for _k in (
                "planning_coupling_v0",
                "planning_ab_bias",
                "planning_ab_delta",
                "planning_verify_rate",
                "planning_verify_delta",
                "planning_score_delta",
            ):
                if _k in operation:
                    dry_out[_k] = operation.get(_k)
            return dry_out

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
                    skipped.append(
                        {
                            "target_file": target_rel,
                            "kind": kind,
                            "error": f"sandbox create failed: {exc}",
                        }
                    )
                    last_error = f"sandbox create failed: {exc}"
                    continue

                sandbox_verify = apply_and_smoke_verify(
                    build_root, operation, drill_id=BUG_HUNT_DRILL
                )
                if not sandbox_verify.get("ok"):
                    err = str(sandbox_verify.get("error") or "unknown")
                    skipped.append(
                        {"target_file": target_rel, "kind": kind, "error": err}
                    )
                    try:
                        remember_bug_hunt_propose(path, target_file=target_rel, kind=kind)
                    except Exception:
                        pass
                    last_error = f"sandbox verify failed: {err}"
                    continue

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
            ab_trial: dict[str, Any] | None = None
            if (
                sandbox
                and sandbox_meta
                and isinstance(sandbox_verify, dict)
                and sandbox_verify.get("ok")
            ):
                try:
                    from eurika.evaluation.ab_compare import run_ab_compare

                    ab_trial = run_ab_compare(
                        path,
                        build_root,
                        smoke_ok=True,
                        sandbox_mode=str(sandbox_meta.get("mode") or ""),
                        operation=operation,
                        source="bug_hunt_propose",
                        drill=BUG_HUNT_DRILL,
                    )
                except Exception:
                    ab_trial = None
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
                "skipped": skipped,
                "hypothesis_caution": bool(operation.get("hypothesis_caution")),
                "hypothesis_caution_kind": operation.get("hypothesis_caution_kind"),
                "instructions": (
                    "Review Approvals / .eurika/pending_plan.json, set team_decision=approve, "
                    "then: eurika fix . --apply-approved"
                ),
            }
            for _k in (
                "planning_coupling_v0",
                "planning_ab_bias",
                "planning_ab_delta",
                "planning_verify_rate",
                "planning_verify_delta",
                "planning_score_delta",
            ):
                if _k in operation:
                    out[_k] = operation.get(_k)
            if sandbox and sandbox_meta:
                out["sandbox_path"] = str(build_root)
                out["sandbox_mode"] = sandbox_meta.get("mode")
                out["sandbox_verify"] = sandbox_verify
                out["sandbox_kept"] = bool(keep_sandbox)
            if ab_trial:
                out["ab_v0"] = ab_trial
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

    return {
        **base,
        "error": last_error,
        "verify_success": False,
        "skipped": skipped,
    }
