"""Doctor-cycle helpers for orchestration layer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def knowledge_topics_from_env_or_summary(summary: Any) -> list[str]:
    """Topics for Knowledge: from EURIKA_KNOWLEDGE_TOPIC or derived from summary."""
    env = os.environ.get("EURIKA_KNOWLEDGE_TOPIC", "").strip()
    if env:
        return [t.strip() for t in env.split(",") if t.strip()]
    # Default to the current Python line for knowledge lookups.
    topics = ["python", "python_3_14"]
    sys_info = summary.get("system") or {}
    if (sys_info.get("cycles") or 0) > 0:
        topics.append("cyclic_imports")
    risks = summary.get("risks") or []
    risk_str = " ".join(str(r) for r in risks).lower()
    if "god" in risk_str or "hub" in risk_str or "bottleneck" in risk_str:
        topics.append("architecture_refactor")
    if "deprecated" in risk_str:
        topics.append("version_migration")
    return topics


def run_doctor_cycle(
    path: Path,
    *,
    window: int = 5,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Run diagnostics cycle: summary + history + patch_plan + architect. No I/O to stdout/stderr."""
    from eurika.api import get_summary, get_history, get_patch_plan, get_recent_events
    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
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
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=86400),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=86400),
    ])
    knowledge_topic = knowledge_topics_from_env_or_summary(summary)
    architect_text = interpret_architecture(
        summary, history, use_llm=use_llm, patch_plan=patch_plan,
        knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic,
        recent_events=recent_events,
    )
    return {
        "summary": summary,
        "history": history,
        "patch_plan": patch_plan,
        "architect_text": architect_text,
    }
