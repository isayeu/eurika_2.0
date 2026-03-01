"""Semantic context sources for patch planning (ROADMAP 3.6.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _target_from_operation_key(raw: str) -> str | None:
    """Extract target file from operation key: target|kind|location."""
    if not raw:
        return None
    target = str(raw).split("|", 1)[0].strip()
    return target or None


def _load_session_memory(project_root: Path) -> dict[str, Any]:
    path = project_root / ".eurika" / "session_memory.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recent_patch_modified(project_root: Path, limit: int = 5) -> list[str]:
    try:
        from eurika.storage import ProjectMemory

        events = ProjectMemory(project_root).events.recent_events(limit=20, types=("patch",))
        seen: list[str] = []
        for e in events:
            out = (e.output or {}) if hasattr(e, "output") else {}
            for m in (out.get("modified") or []):
                ms = str(m)
                if ms and ms not in seen:
                    seen.append(ms)
                if len(seen) >= limit:
                    return seen
        return seen
    except Exception:
        return []


def _related_tests(project_root: Path, target_file: str, limit: int = 3) -> list[str]:
    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        return []
    stem = Path(target_file).stem
    if not stem:
        return []
    matches: list[str] = []
    for p in tests_dir.rglob("test_*.py"):
        ps = str(p.relative_to(project_root))
        if stem in p.stem:
            matches.append(ps)
        if len(matches) >= limit:
            break
    return matches


def _neighbor_modules(project_root: Path, target_file: str, limit: int = 5) -> list[str]:
    self_map = project_root / "self_map.json"
    if not self_map.exists():
        return []
    try:
        data = json.loads(self_map.read_text(encoding="utf-8"))
    except Exception:
        return []
    deps = data.get("dependencies") or {}
    if not isinstance(deps, dict):
        return []

    neighbors: list[str] = []
    # outgoing
    for v in deps.get(target_file, []) or []:
        vs = str(v)
        if vs and vs not in neighbors:
            neighbors.append(vs)
        if len(neighbors) >= limit:
            return neighbors
    # incoming
    for src, dsts in deps.items():
        if not isinstance(dsts, list):
            continue
        if target_file in [str(d) for d in dsts]:
            ss = str(src)
            if ss and ss not in neighbors:
                neighbors.append(ss)
            if len(neighbors) >= limit:
                return neighbors
    return neighbors


def _target_learning_rates(root: Path, operations: list[dict[str, Any]]) -> dict[str, float]:
    """Map target -> min verify_success_rate across ops targeting it (KPI A.4)."""
    try:
        from eurika.api import get_learning_insights

        insights = get_learning_insights(root, top_n=30)
        by_target_list = insights.get("by_target") or []
        rate_by_key: dict[str, float] = {}
        for r in by_target_list:
            k = f"{r.get('smell_type') or '?'}|{r.get('action_kind') or '?'}|{r.get('target_file') or '?'}"
            rate_by_key[k] = float(r.get("verify_success_rate", 0) or 0)
        target_mins: dict[str, float] = {}
        for op in operations:
            target = str(op.get("target_file") or "").replace("\\", "/")
            if not target:
                continue
            kind = str(op.get("kind") or "")
            smell = str(op.get("smell_type") or "")
            key = f"{smell}|{kind}|{target}"
            rate = rate_by_key.get(key, 0.0)
            if target not in target_mins:
                target_mins[target] = 1.0
            target_mins[target] = min(target_mins[target], rate)
        return target_mins
    except Exception:
        return {}


def build_context_sources(project_root: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Build semantic context payload and per-target signals for planner/reporting."""
    root = Path(project_root).resolve()
    session = _load_session_memory(root)
    campaign = session.get("campaign") or {}
    rejected_keys = campaign.get("rejected_keys") or []
    fail_keys = campaign.get("verify_fail_keys") or []

    rejected_targets: list[str] = []
    for k in rejected_keys:
        t = _target_from_operation_key(str(k))
        if t and t not in rejected_targets:
            rejected_targets.append(t)

    verify_fail_targets: list[str] = []
    for k in fail_keys:
        t = _target_from_operation_key(str(k))
        if not t or t in verify_fail_targets:
            continue
        # Skip targets for files that no longer exist (e.g. polygon.py → polygon/ migration)
        if not (root / t.replace("\\", "/")).exists():
            continue
        verify_fail_targets.append(t)

    target_rates = _target_learning_rates(root, operations)

    by_target: dict[str, dict[str, Any]] = {}
    for op in operations:
        target = str(op.get("target_file") or "").replace("\\", "/")
        if not target:
            continue
        if target in by_target:
            continue
        entry: dict[str, Any] = {
            "related_tests": _related_tests(root, target),
            "neighbor_modules": _neighbor_modules(root, target),
        }
        rate = target_rates.get(target)
        if rate is not None:
            entry["verify_success_rate"] = round(rate, 4)
        by_target[target] = entry

    prioritized_smell_actions: list[dict[str, Any]] = []
    try:
        from eurika.api import get_learning_insights
        insights = get_learning_insights(root, top_n=10)
        prioritized_smell_actions = (insights.get("prioritized_smell_actions") or [])[:6]
    except Exception:
        pass
    return {
        "recent_verify_fail_targets": verify_fail_targets[:10],
        "campaign_rejected_targets": rejected_targets[:10],
        "recent_patch_modified": _recent_patch_modified(root, limit=10),
        "by_target": by_target,
        "prioritized_smell_actions": prioritized_smell_actions,
    }
