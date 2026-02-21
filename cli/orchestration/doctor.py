"""Doctor-cycle helpers for orchestration layer. ROADMAP 2.9.3: smell→topic mapping."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# smell_type → knowledge topics (ROADMAP 2.9.3). Used when EURIKA_KNOWLEDGE_TOPIC not set.
SMELL_TO_KNOWLEDGE_TOPICS: dict[str, list[str]] = {
    "god_module": ["architecture_refactor", "module_structure"],
    "bottleneck": ["architecture_refactor"],
    "hub": ["architecture_refactor", "module_structure"],
    "cyclic_dependency": ["cyclic_imports"],
    "long_function": ["pep_8"],
    "deep_nesting": ["pep_8"],
}


def _parse_smell_for_knowledge(risk: str) -> str | None:
    """Extract smell type from risk for knowledge mapping (broader than architect's)."""
    if not risk or not isinstance(risk, str):
        return None
    parts = risk.strip().split()
    if not parts:
        return None
    first = parts[0].lower()
    return first if first in SMELL_TO_KNOWLEDGE_TOPICS else None


def knowledge_topics_from_env_or_summary(summary: Any) -> list[str]:
    """Topics for Knowledge: from EURIKA_KNOWLEDGE_TOPIC or derived from summary (ROADMAP 2.9.3)."""
    env = os.environ.get("EURIKA_KNOWLEDGE_TOPIC", "").strip()
    if env:
        return [t.strip() for t in env.split(",") if t.strip()]
    topics: list[str] = ["python", "python_3_14"]
    sys_info = summary.get("system") or {}
    if (sys_info.get("cycles") or 0) > 0:
        topics.append("cyclic_imports")
    risks = summary.get("risks") or []
    seen_topics: set[str] = set(topics)
    for r in risks:
        smell = _parse_smell_for_knowledge(str(r))
        if smell and smell in SMELL_TO_KNOWLEDGE_TOPICS:
            for t in SMELL_TO_KNOWLEDGE_TOPICS[smell]:
                if t not in seen_topics:
                    seen_topics.add(t)
                    topics.append(t)
    risk_str = " ".join(str(r) for r in risks).lower()
    if "deprecated" in risk_str and "version_migration" not in seen_topics:
        topics.append("version_migration")
    return topics


def load_suggested_policy_for_apply(path: Path) -> dict[str, str]:
    """Load suggested policy from doctor or fix report for --apply-suggested-policy (ROADMAP 2.9.4)."""
    doctor_path = path / "eurika_doctor_report.json"
    if doctor_path.exists():
        try:
            doc = json.loads(doctor_path.read_text(encoding="utf-8"))
            sugg = (doc.get("suggested_policy") or {}).get("suggested") or {}
            if isinstance(sugg, dict):
                return {k: str(v) for k, v in sugg.items()}
        except Exception:
            pass
    fix_path = path / "eurika_fix_report.json"
    if fix_path.exists():
        try:
            fix = json.loads(fix_path.read_text(encoding="utf-8"))
            telemetry = fix.get("telemetry") or {}
            if telemetry:
                from eurika.agent.config import suggest_policy_from_telemetry

                return suggest_policy_from_telemetry(telemetry)
        except Exception:
            pass
    return {}


def _suggested_policy_from_last_fix(path: Path) -> dict[str, Any]:
    """Load last fix telemetry and suggest policy (ROADMAP 2.9.4)."""
    fix_path = path / "eurika_fix_report.json"
    if not fix_path.exists():
        return {}
    try:
        fix = json.loads(fix_path.read_text(encoding="utf-8"))
        telemetry = fix.get("telemetry") or {}
        if not telemetry:
            return {}
        from eurika.agent.config import suggest_policy_from_telemetry

        suggested = suggest_policy_from_telemetry(telemetry)
        return {
            "suggested": suggested,
            "telemetry": {
                "apply_rate": telemetry.get("apply_rate"),
                "rollback_rate": telemetry.get("rollback_rate"),
            },
        }
    except Exception:
        return {}


def run_doctor_cycle(
    path: Path,
    *,
    window: int = 5,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Run diagnostics cycle: summary + history + patch_plan + architect. No I/O to stdout/stderr. ROADMAP 2.9.4: suggested_policy."""
    from eurika.api import get_summary, get_history, get_patch_plan, get_recent_events
    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
        PEPProvider,
        ReleaseNotesProvider,
    )
    from eurika.reasoning.architect import interpret_architecture

    summary = get_summary(path)
    if summary.get("error"):
        return {"error": summary.get("error", "unknown")}
    history = get_history(path, window=window)
    patch_plan = get_patch_plan(path, window=window)
    recent_events = get_recent_events(path, limit=5, types=("patch", "learn"))
    use_llm = not no_llm
    cache_dir = path / ".eurika" / "knowledge_cache"
    knowledge_provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(path / "eurika_knowledge.json"),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=86400),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=86400),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=86400),
    ])
    knowledge_topic = knowledge_topics_from_env_or_summary(summary)
    architect_text = interpret_architecture(
        summary, history, use_llm=use_llm, patch_plan=patch_plan,
        knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic,
        recent_events=recent_events,
    )
    out: dict[str, Any] = {
        "summary": summary,
        "history": history,
        "patch_plan": patch_plan,
        "architect_text": architect_text,
    }
    suggested_info = _suggested_policy_from_last_fix(path)
    if suggested_info.get("suggested"):
        out["suggested_policy"] = suggested_info
    return out
