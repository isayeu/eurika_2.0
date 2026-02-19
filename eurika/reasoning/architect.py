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


def _template_structure_sentence(modules: int, deps: int, cycles: int) -> str:
    """Sentence describing structural graph size and cyclicity."""
    if cycles == 0:
        return f"The codebase has {modules} modules and {deps} dependencies with no cycles."
    return f"The codebase has {modules} modules, {deps} dependencies and {cycles} cycles."


def _template_risks_sentence(
    risks: List[str],
    central_modules: List[Dict[str, Any]],
) -> str:
    """Sentence about top risks; fallback to central modules when risks absent."""
    if risks:
        top = risks[:3]
        risk_str = "; ".join(top) if len(top) <= 2 else top[0] + " and " + str(len(risks) - 1) + " more"
        return f"Main risks: {risk_str}."
    if central_modules:
        names = [c.get("name", "") for c in central_modules[:3] if isinstance(c, dict)]
        return f"Central modules: {', '.join(names)}."
    return ""


def _template_trends_sentences(
    trend_complexity: str,
    trend_smells: str,
    regressions: List[str],
) -> List[str]:
    """Optional trend and regression sentences."""
    out: List[str] = []
    if trend_complexity != "unknown" or trend_smells != "unknown":
        out.append(f"Trends: complexity {trend_complexity}, smells {trend_smells}.")
    if regressions:
        out.append(f"Potential regressions: {'; '.join(regressions[:2])}.")
    return out


def _template_context_sentences(
    patch_plan: Optional[Dict[str, Any]],
    knowledge_snippet: str,
    recent_events_snippet: str,
) -> List[str]:
    """Optional sentences for patch-plan, recent events and knowledge."""
    out: List[str] = []
    patch_sentence = _format_template_patch_plan_sentence(patch_plan)
    if patch_sentence:
        out.append(patch_sentence)
    if recent_events_snippet:
        out.append(f"Recent actions: {recent_events_snippet}.")
    if knowledge_snippet:
        out.append(
            f"Reference: {knowledge_snippet[:300]}"
            + ("..." if len(knowledge_snippet) > 300 else "")
        )
    return out


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
    parts.append(_template_structure_sentence(modules, deps, cycles))
    parts.append(f"Syntactic maturity is {maturity}.")
    risks_sentence = _template_risks_sentence(risks, central)
    if risks_sentence:
        parts.append(risks_sentence)
    parts.extend(_template_trends_sentences(trend_complexity, trend_smells, regressions))
    parts.extend(_template_context_sentences(patch_plan, knowledge_snippet, recent_events_snippet))
    return " ".join(parts)


def _build_openai_client(
    api_key: str,
    base_url: str | None,
) -> tuple[Any | None, str | None]:
    """Build OpenAI client instance. Returns (client, reason)."""
    from urllib.parse import urlparse

    try:
        from openai import OpenAI
    except ImportError:
        return None, "openai package not installed (pip install openai)"
    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if base_url:
        try:
            host = (urlparse(base_url).hostname or "").lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                import httpx

                # Local Ollama should bypass inherited proxy env vars.
                kwargs["http_client"] = httpx.Client(trust_env=False)
        except Exception:
            pass
    return OpenAI(**kwargs), None


def _init_primary_openai_client() -> tuple[Any | None, str | None, str | None]:
    """Initialize primary LLM client from OPENAI_* env (typically OpenRouter)."""
    import os

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None, "OPENAI_API_KEY not set (add to .env or export; pip install python-dotenv to load .env)"
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client, reason = _build_openai_client(api_key, base_url)
    return client, model, reason


def _init_ollama_fallback_client() -> tuple[Any | None, str | None, str | None]:
    """Initialize local Ollama fallback client from OLLAMA_OPENAI_* env (or defaults)."""
    import os

    api_key = os.environ.get("OLLAMA_OPENAI_API_KEY", "ollama")
    base_url = os.environ.get("OLLAMA_OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("OLLAMA_OPENAI_MODEL", "qwen2.5:1.5b")
    client, reason = _build_openai_client(api_key, base_url)
    return client, model, reason


def _build_llm_prompt(
    summary: Dict[str, Any],
    history: Dict[str, Any],
    patch_plan: Optional[Dict[str, Any]],
    knowledge_snippet: str,
    recent_events_snippet: str,
) -> str:
    """Assemble a concise architect prompt for LLM."""
    patch_desc = _build_llm_patch_desc(patch_plan)
    ref_block = ""
    if knowledge_snippet:
        ref_block = "\n\nReference knowledge (use if relevant):\n" + knowledge_snippet
    events_block = ""
    if recent_events_snippet:
        events_block = "\n\nRecent refactoring events (for context): " + recent_events_snippet
    return (
        "You are a software architect. In 2-4 short sentences, summarize the state of this codebase "
        "and the main recommendation. Be concrete and concise. If patch operations are planned, "
        "mention the most impactful refactorings.\n\n"
        f"Summary: {summary}\n\n"
        f"History (trends/regressions): {history.get('trends')}, regressions: {history.get('regressions', [])[:3]}"
        f"{patch_desc}"
        f"{events_block}"
        f"{ref_block}"
    )


def _build_ollama_cli_prompt(
    summary: Dict[str, Any],
    history: Dict[str, Any],
    patch_plan: Optional[Dict[str, Any]],
) -> str:
    """Compact prompt for local CLI fallback to avoid long generation stalls."""
    sys_info = summary.get("system") or {}
    modules = sys_info.get("modules", 0)
    deps = sys_info.get("dependencies", 0)
    cycles = sys_info.get("cycles", 0)
    maturity = summary.get("maturity", "unknown")
    top_risk = (summary.get("risks") or ["none"])[0]
    trends = history.get("trends") or {}
    patch_desc = _build_llm_patch_desc(patch_plan)
    return (
        "You are a software architect. Reply in exactly 2 short sentences.\n"
        "Sentence 1: architecture risk level. Sentence 2: one highest-impact refactoring.\n\n"
        f"Metrics: modules={modules}, dependencies={deps}, cycles={cycles}, maturity={maturity}\n"
        f"Top risk: {top_risk}\n"
        f"Trends: complexity={trends.get('complexity', 'unknown')}, "
        f"smells={trends.get('smells', 'unknown')}, "
        f"centralization={trends.get('centralization', 'unknown')}"
        f"{patch_desc}"
    )


def _call_llm_architect(client: Any, model: str, prompt: str) -> tuple[str | None, str | None]:
    """Call OpenAI chat completions and normalize response shape."""
    import os

    timeout_sec = float(os.environ.get("EURIKA_LLM_TIMEOUT_SEC", "20"))
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            timeout=timeout_sec,
        )
        if r.choices and r.choices[0].message.content:
            return r.choices[0].message.content.strip(), None
        return None, "empty LLM response"
    except Exception as e:
        return None, str(e)


def _call_ollama_cli(model: str, prompt: str) -> tuple[str | None, str | None]:
    """Fallback path via local `ollama run` CLI when HTTP endpoints are unavailable."""
    import os
    import subprocess
    import time

    cli_timeout_sec = int(os.environ.get("EURIKA_OLLAMA_CLI_TIMEOUT_SEC", "45"))

    def _run_once(timeout_sec: int | None = None) -> tuple[str | None, str | None]:
        if timeout_sec is None:
            timeout_sec = cli_timeout_sec
        try:
            r = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except FileNotFoundError:
            return None, "ollama CLI not found in PATH"
        except Exception as e:  # pragma: no cover - defensive
            return None, str(e)
        if r.returncode != 0:
            reason = (r.stderr or r.stdout or "").strip() or f"ollama exited with code {r.returncode}"
            return None, reason
        text = (r.stdout or "").strip()
        if not text:
            return None, "empty ollama CLI response"
        return text, None

    def _model_ready_reason() -> str | None:
        try:
            r = subprocess.run(
                ["ollama", "show", model],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as e:  # pragma: no cover - defensive
            return str(e)
        if r.returncode == 0:
            return None
        reason = (r.stderr or r.stdout or "").strip() or "unknown model check failure"
        lowered = reason.lower()
        if "not found" in lowered or "no such model" in lowered:
            return f"ollama model '{model}' is not available; run `ollama pull {model}`"
        return f"ollama model check failed: {reason}"

    try:
        text, reason = _run_once()
        if text:
            return text, None
        if reason and "could not connect to ollama server" in reason.lower():
            # Try to self-heal: start local daemon and retry once.
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(2.0)
            readiness_issue = _model_ready_reason()
            if readiness_issue:
                return None, readiness_issue
            return _run_once()
        if reason and "timed out" in reason.lower():
            readiness_issue = _model_ready_reason()
            if readiness_issue:
                return None, readiness_issue
            return None, f"{reason} (cli timeout={cli_timeout_sec}s)"
        return None, reason
    except Exception as e:  # pragma: no cover - defensive
        return None, str(e)


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
    primary_client, primary_model, init_reason = _init_primary_openai_client()
    prompt = _build_llm_prompt(
        summary=summary,
        history=history,
        patch_plan=patch_plan,
        knowledge_snippet=knowledge_snippet,
        recent_events_snippet=recent_events_snippet,
    )
    primary_reason = init_reason
    if primary_client and primary_model:
        llm_text, primary_call_reason = _call_llm_architect(primary_client, primary_model, prompt)
        if llm_text:
            return llm_text, None
        primary_reason = primary_call_reason
    fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
    fallback_reason = fallback_init_reason
    if fallback_client and fallback_model:
        fallback_text, fallback_call_reason = _call_llm_architect(
            fallback_client, fallback_model, prompt
        )
        if fallback_text:
            return fallback_text, None
        fallback_reason = fallback_call_reason
    cli_model = fallback_model or "qwen2.5:1.5b"
    cli_prompt = _build_ollama_cli_prompt(summary, history, patch_plan)
    cli_text, cli_reason = _call_ollama_cli(cli_model, cli_prompt)
    if cli_text:
        return cli_text, None
    return None, (
        f"primary LLM failed ({primary_reason or 'unknown'}); "
        f"ollama HTTP fallback failed ({fallback_reason or 'unknown'}); "
        f"ollama CLI fallback failed ({cli_reason or 'unknown'})"
    )


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
