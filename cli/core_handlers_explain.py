"""Explain, architect, suggest-plan handlers (P0.4 split)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path, _err


def handle_explain(args: Any) -> int:
    """Explain role and risks of a given module (3.1-arch.5 thin)."""
    module_arg = getattr(args, "module", None)
    if not module_arg:
        _err("module path or name is required")
        return 1
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from report.explain_format import explain_module

    text, err = explain_module(path, module_arg, window=getattr(args, "window", 5))
    if err:
        _err(err)
        return 1
    print(text)
    return 0


def handle_architect(args: Any) -> int:
    """Print architect's interpretation (template or optional LLM), with patch-plan context."""
    from cli.orchestrator import _knowledge_topics_from_env_or_summary
    from eurika.api import get_summary, get_history, get_patch_plan, get_recent_events
    from eurika.reasoning.architect import interpret_architecture
    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
        OSSPatternProvider,
        PEPProvider,
        ReleaseNotesProvider,
    )

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    summary = get_summary(path)
    if summary.get("error"):
        _err(summary.get("error", "unknown"))
        return 1
    window = getattr(args, "window", 5)
    history = get_history(path, window=window)
    patch_plan = get_patch_plan(path, window=window)
    recent_events = get_recent_events(path, limit=5, types=("patch", "learn"))
    use_llm = not getattr(args, "no_llm", False)
    cache_dir = path / ".eurika" / "knowledge_cache"
    online = getattr(args, "online", False)
    ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
    rate_limit = float(os.environ.get("EURIKA_KNOWLEDGE_RATE_LIMIT", "1.0" if online else "0"))
    knowledge_provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(path / "eurika_knowledge.json"),
        OSSPatternProvider(path / ".eurika" / "pattern_library.json"),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
    ])
    knowledge_topic = _knowledge_topics_from_env_or_summary(summary)
    text = interpret_architecture(
        summary, history, use_llm=use_llm, patch_plan=patch_plan,
        knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic, recent_events=recent_events
    )
    print(text)
    return 0


def handle_suggest_plan(args: Any) -> int:
    """Print heuristic refactoring plan (3.1-arch.5 thin)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from report.suggest_plan_format import get_suggest_plan_text

    plan = get_suggest_plan_text(path, window=getattr(args, "window", 5))
    if plan.startswith("Error:"):
        _err(plan)
        return 1
    print(plan)
    return 0
