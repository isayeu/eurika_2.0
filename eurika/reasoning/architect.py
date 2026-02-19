"""
Architect interpretation (ROADMAP §7 — мини-AI).

Produces a short "architect's take" on the codebase from summary + history + patch-plan.
- Template-based by default (no API key, deterministic).
- Optional LLM: set OPENAI_API_KEY; supports OpenAI and OpenRouter (OPENAI_BASE_URL, OPENAI_MODEL).
- Optional Knowledge Layer: pass knowledge_provider + knowledge_topic to inject curated snippets into the prompt.
- ROADMAP 3.2.3: recent_events (patch, learn) for context in prompt.
- --no-llm: use template only (deterministic, no API key, faster; useful for CI or when LLM unavailable).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from eurika.knowledge import KnowledgeProvider
    from eurika.storage.events import Event


def _format_recent_events(events: List["Event"], max_chars: int = 500) -> str:
    """Format recent patch/learn events for architect prompt (ROADMAP 3.2.3)."""
    if not events:
        return ""
    lines: List[str] = []
    for e in events[:10]:
        if e.type == "patch":
            modified = e.output.get("modified", [])
            res = e.result
            lines.append(f"patch: modified {len(modified)} file(s), verify={res}")
        elif e.type == "learn":
            modules = e.input.get("modules", [])
            res = e.result
            mods = ", ".join(modules[:3]) + ("..." if len(modules) > 3 else "")
            lines.append(f"learn: modules [{mods}], success={res}")
        else:
            lines.append(f"{e.type}: result={e.result}")
    out = "; ".join(lines)
    return out[:max_chars] + ("..." if len(out) > max_chars else "")


def _format_knowledge_fragments(fragments: List[Dict[str, Any]]) -> str:
    """Format knowledge fragments for inclusion in prompt or template."""
    if not fragments:
        return ""
    lines: List[str] = []
    for i, f in enumerate(fragments[:10], 1):
        if not isinstance(f, dict):
            continue
        title = f.get("title") or f.get("name") or f"Fragment {i}"
        content = f.get("content") or f.get("text") or str(f)
        lines.append(f"- {title}: {content[:500]}" + ("..." if len(str(content)) > 500 else ""))
    return "\n".join(lines) if lines else ""


def _summarize_patch_plan(patch_plan: Optional[Dict[str, Any]]) -> tuple[int, Dict[str, int], List[str]]:
    """Extract count/kind breakdown/targets from patch plan."""
    if not (patch_plan and patch_plan.get("operations")):
        return 0, {}, []
    ops = patch_plan["operations"]
    kind_counts: Dict[str, int] = {}
    for o in ops:
        k = o.get("kind", "refactor")
        kind_counts[k] = kind_counts.get(k, 0) + 1
    targets = list({o.get("target_file", "") for o in ops if o.get("target_file")})[:5]
    return len(ops), kind_counts, targets


def _format_template_patch_plan_sentence(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Template sentence describing planned refactorings."""
    total, kind_counts, targets = _summarize_patch_plan(patch_plan)
    if not (total and targets):
        return ""
    kinds = ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items()))
    return f"Planned refactorings: {total} ops ({kinds}); top targets: {', '.join(targets[:3])}."


def _build_llm_patch_desc(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Prompt block with patch-plan context for LLM."""
    total, _kind_counts, targets = _summarize_patch_plan(patch_plan)
    if total == 0:
        return ""
    kinds = [o.get("kind", "refactor") for o in patch_plan["operations"]]
    return (
        f"\n\nPlanned patch operations: {total} total. Kinds: {kinds[:10]}. "
        f"Top target modules: {targets[:5]}. "
        "Consider these in your recommendation."
    )


def _resolve_knowledge_snippet(
    knowledge_provider: Optional["KnowledgeProvider"],
    knowledge_topic: Optional[Union[str, List[str]]],
) -> str:
    """Resolve and format knowledge snippets from provider/topics."""
    if not (knowledge_provider and knowledge_topic):
        return ""
    from eurika.knowledge import StructuredKnowledge

    topics = [knowledge_topic] if isinstance(knowledge_topic, str) else knowledge_topic
    all_fragments: List[Dict[str, Any]] = []
    for t in topics:
        if not t:
            continue
        kn = knowledge_provider.query(t.strip())
        if isinstance(kn, StructuredKnowledge) and not kn.is_empty():
            all_fragments.extend(kn.fragments)
    return _format_knowledge_fragments(all_fragments) if all_fragments else ""


def _template_interpret(
    summary: Dict[str, Any],
    history: Dict[str, Any],
    patch_plan: Optional[Dict[str, Any]] = None,
    knowledge_snippet: str = "",
    recent_events_snippet: str = "",
) -> str:
    """Deterministic 2–4 sentence take from summary and history."""
    sys = summary.get("system") or {}
    modules = sys.get("modules", 0)
    deps = sys.get("dependencies", 0)
    cycles = sys.get("cycles", 0)
    maturity = summary.get("maturity", "unknown")
    risks = summary.get("risks") or []
    central = summary.get("central_modules") or []

    trend_complexity = (history.get("trends") or {}).get("complexity", "unknown")
    trend_smells = (history.get("trends") or {}).get("smells", "unknown")
    regressions = history.get("regressions") or []

    parts: list[str] = []
    # Structure
    if cycles == 0:
        parts.append(
            f"The codebase has {modules} modules and {deps} dependencies with no cycles."
        )
    else:
        parts.append(
            f"The codebase has {modules} modules, {deps} dependencies and {cycles} cycles."
        )
    # Maturity and risks
    parts.append(f"Syntactic maturity is {maturity}.")
    if risks:
        top = risks[:3]
        risk_str = "; ".join(top) if len(top) <= 2 else top[0] + " and " + str(len(risks) - 1) + " more"
        parts.append(f"Main risks: {risk_str}.")
    elif central:
        names = [c.get("name", "") for c in central[:3] if isinstance(c, dict)]
        parts.append(f"Central modules: {', '.join(names)}.")
    # Trends
    if trend_complexity != "unknown" or trend_smells != "unknown":
        parts.append(f"Trends: complexity {trend_complexity}, smells {trend_smells}.")
    if regressions:
        parts.append(f"Potential regressions: {'; '.join(regressions[:2])}.")
    # Patch plan summary (ROADMAP §7 — связка с patch-plan)
    patch_sentence = _format_template_patch_plan_sentence(patch_plan)
    if patch_sentence:
        parts.append(patch_sentence)
    if recent_events_snippet:
        parts.append(f"Recent actions: {recent_events_snippet}.")
    if knowledge_snippet:
        parts.append(f"Reference: {knowledge_snippet[:300]}" + ("..." if len(knowledge_snippet) > 300 else ""))
    return " ".join(parts)


def _llm_interpret(
    summary: Dict[str, Any],
    history: Dict[str, Any],
    patch_plan: Optional[Dict[str, Any]] = None,
    knowledge_snippet: str = "",
    recent_events_snippet: str = "",
) -> tuple[str | None, str | None]:
    """Call LLM for a short architect take. Returns (text, None) on success, (None, reason) on failure.

    Env: OPENAI_API_KEY (required), OPENAI_BASE_URL (e.g. OpenRouter), OPENAI_MODEL (e.g. mistralai/...).
    knowledge_snippet: optional pre-formatted reference knowledge to append to the prompt.
    """
    import os

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY not set (add to .env or export; pip install python-dotenv to load .env)"
    try:
        from openai import OpenAI
    except ImportError:
        return None, "openai package not installed (pip install openai)"
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key, base_url=base_url)

    patch_desc = _build_llm_patch_desc(patch_plan)

    ref_block = ""
    if knowledge_snippet:
        ref_block = "\n\nReference knowledge (use if relevant):\n" + knowledge_snippet
    events_block = ""
    if recent_events_snippet:
        events_block = "\n\nRecent refactoring events (for context): " + recent_events_snippet
    prompt = (
        "You are a software architect. In 2-4 short sentences, summarize the state of this codebase "
        "and the main recommendation. Be concrete and concise. If patch operations are planned, "
        "mention the most impactful refactorings.\n\n"
        f"Summary: {summary}\n\n"
        f"History (trends/regressions): {history.get('trends')}, regressions: {history.get('regressions', [])[:3]}"
        f"{patch_desc}"
        f"{events_block}"
        f"{ref_block}"
    )
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
        )
        if r.choices and r.choices[0].message.content:
            return r.choices[0].message.content.strip(), None
        return None, "empty LLM response"
    except Exception as e:
        return None, str(e)


def interpret_architecture(
    summary: Dict[str, Any],
    history: Dict[str, Any],
    use_llm: bool = True,
    verbose: bool = True,
    patch_plan: Optional[Dict[str, Any]] = None,
    knowledge_provider: Optional["KnowledgeProvider"] = None,
    knowledge_topic: Optional[Union[str, List[str]]] = None,
    recent_events: Optional[List["Event"]] = None,
) -> str:
    """
    Return a short architect's interpretation (2–4 sentences).

    If use_llm is True and OPENAI_API_KEY is set, attempts an LLM call;
    on failure or missing key, falls back to template-based text.
    If verbose is True, prints the fallback reason to stderr.
    patch_plan: optional operations dict from get_patch_plan (ROADMAP §7).
    knowledge_provider + knowledge_topic: optional Knowledge Layer. knowledge_topic may be
    a single topic (str) or a list of topics; all fragments are merged and injected.
    recent_events: optional list of Event (patch, learn) for context (ROADMAP 3.2.3).
    """
    import sys

    knowledge_snippet = _resolve_knowledge_snippet(knowledge_provider, knowledge_topic)

    recent_snippet = _format_recent_events(recent_events) if recent_events else ""
    if use_llm:
        llm_text, reason = _llm_interpret(
            summary, history, patch_plan, knowledge_snippet, recent_snippet
        )
        if llm_text:
            return llm_text
        if verbose and reason:
            print(f"eurika: architect: using template — {reason}", file=sys.stderr)
    return _template_interpret(
        summary, history, patch_plan, knowledge_snippet, recent_snippet
    )


# TODO (eurika): refactor long_function '_template_interpret' — consider extracting helper


# TODO (eurika): refactor long_function '_llm_interpret' — consider extracting helper
