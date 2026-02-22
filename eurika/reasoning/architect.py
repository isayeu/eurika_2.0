"""
Architect interpretation (ROADMAP §7 — мини-AI; §2.9.1 — рекомендации «как»).

Produces a short "architect's take" on the codebase from summary + history + patch-plan.
- Template-based by default (no API key, deterministic).
- Optional LLM: set OPENAI_API_KEY; supports OpenAI and OpenRouter (OPENAI_BASE_URL, OPENAI_MODEL).
- Optional Knowledge Layer: pass knowledge_provider + knowledge_topic to inject curated snippets into the prompt.
- ROADMAP 3.2.3: recent_events (patch, learn) for context in prompt.
- ROADMAP 2.9.1: Recommendation block with concrete "how to fix" per smell type (god_module, bottleneck, hub); Reference from Knowledge.
- --no-llm: use template only (deterministic, no API key, faster; useful for CI or when LLM unavailable).
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
if TYPE_CHECKING:
    from eurika.knowledge import KnowledgeProvider
    from eurika.storage.events import Event

def _format_recent_events(events: List['Event'], max_chars: int=500) -> str:
    """Format recent patch/learn events for architect prompt (ROADMAP 3.2.3)."""
    if not events:
        return ''
    lines: List[str] = []
    for e in events[:10]:
        if e.type == 'patch':
            modified = e.output.get('modified', [])
            res = e.result
            lines.append(f'patch: modified {len(modified)} file(s), verify={res}')
        elif e.type == 'learn':
            modules = e.input.get('modules', [])
            res = e.result
            mods = ', '.join(modules[:3]) + ('...' if len(modules) > 3 else '')
            lines.append(f'learn: modules [{mods}], success={res}')
        else:
            lines.append(f'{e.type}: result={e.result}')
    out = '; '.join(lines)
    return out[:max_chars] + ('...' if len(out) > max_chars else '')

def _format_knowledge_fragments(fragments: List[Dict[str, Any]]) -> str:
    """Format knowledge fragments for inclusion in prompt or template."""
    if not fragments:
        return ''
    lines: List[str] = []
    for i, f in enumerate(fragments[:10], 1):
        if not isinstance(f, dict):
            continue
        title = f.get('title') or f.get('name') or f'Fragment {i}'
        content = f.get('content') or f.get('text') or str(f)
        lines.append(f'- {title}: {content[:500]}' + ('...' if len(str(content)) > 500 else ''))
    return '\n'.join(lines) if lines else ''

def _summarize_patch_plan(patch_plan: Optional[Dict[str, Any]]) -> tuple[int, Dict[str, int], List[str]]:
    """Extract count/kind breakdown/targets from patch plan."""
    if not (patch_plan and patch_plan.get('operations')):
        return (0, {}, [])
    ops = patch_plan['operations']
    kind_counts: Dict[str, int] = {}
    for o in ops:
        k = o.get('kind', 'refactor')
        kind_counts[k] = kind_counts.get(k, 0) + 1
    targets = list({o.get('target_file', '') for o in ops if o.get('target_file')})[:5]
    return (len(ops), kind_counts, targets)

def _format_template_patch_plan_sentence(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Template sentence describing planned refactorings."""
    total, kind_counts, targets = _summarize_patch_plan(patch_plan)
    if not (total and targets):
        return ''
    kinds = ', '.join((f'{k}={v}' for k, v in sorted(kind_counts.items())))
    return f"Planned refactorings: {total} ops ({kinds}); top targets: {', '.join(targets[:3])}."

def _build_llm_patch_desc(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Prompt block with patch-plan context for LLM."""
    total, _kind_counts, targets = _summarize_patch_plan(patch_plan)
    if total == 0:
        return ''
    kinds = [o.get('kind', 'refactor') for o in patch_plan['operations']]
    return f'\n\nPlanned patch operations: {total} total. Kinds: {kinds[:10]}. Top target modules: {targets[:5]}. Consider these in your recommendation.'

def _resolve_knowledge_snippet(knowledge_provider: Optional['KnowledgeProvider'], knowledge_topic: Optional[Union[str, List[str]]]) -> str:
    """Resolve and format knowledge snippets from provider/topics."""
    if not (knowledge_provider and knowledge_topic):
        return ''
    from eurika.knowledge import StructuredKnowledge
    topics = [knowledge_topic] if isinstance(knowledge_topic, str) else knowledge_topic
    all_fragments: List[Dict[str, Any]] = []
    for t in topics:
        if not t:
            continue
        kn = knowledge_provider.query(t.strip())
        if isinstance(kn, StructuredKnowledge) and (not kn.is_empty()):
            all_fragments.extend(kn.fragments)
    return _format_knowledge_fragments(all_fragments) if all_fragments else ''

def _template_structure_sentence(modules: int, deps: int, cycles: int) -> str:
    """Sentence describing structural graph size and cyclicity."""
    if cycles == 0:
        return f'The codebase has {modules} modules and {deps} dependencies with no cycles.'
    return f'The codebase has {modules} modules, {deps} dependencies and {cycles} cycles.'
_SMELL_HOW_MAP: Dict[str, str] = {'god_module': 'Split into focused modules by responsibility (e.g. core, analysis, reporting, CLI).', 'bottleneck': 'Introduce a facade so dependents use a stable interface instead of the concrete implementation.', 'hub': 'Decompose and split responsibilities; extract sub-modules.', 'cyclic_dependency': 'Break the cycle via dependency inversion or an abstraction layer that both sides depend on.'}
_SMELL_REF_SUFFIX: str = ' See Reference block for documentation.'

def _parse_smell_from_risk(risk: str) -> Optional[str]:
    """Extract smell type from risk string (e.g. 'god_module @ patch_engine.py' -> 'god_module')."""
    if not risk or not isinstance(risk, str):
        return None
    parts = risk.strip().split()
    if not parts:
        return None
    first = parts[0].lower()
    return first if first in _SMELL_HOW_MAP else None

def _build_recommendation_how_block(risks: List[str], knowledge_snippet: str) -> str:
    """Build concrete 'how to fix' block for top risks (ROADMAP 2.9.1)."""
    seen: set[str] = set()
    lines: List[str] = []
    for r in (risks or [])[:5]:
        smell = _parse_smell_from_risk(r)
        if not smell or smell in seen:
            continue
        seen.add(smell)
        how = _SMELL_HOW_MAP.get(smell)
        if how:
            lines.append(f'- {smell}: {how}')
    if not lines:
        return ''
    ref_note = _SMELL_REF_SUFFIX if knowledge_snippet else ''
    return '\n\nRecommendation (how to fix):\n' + '\n'.join(lines) + ref_note

def _template_risks_sentence(risks: List[str], central_modules: List[Dict[str, Any]]) -> str:
    """Sentence about top risks; fallback to central modules when risks absent."""
    if risks:
        top = risks[:3]
        risk_str = '; '.join(top) if len(top) <= 2 else top[0] + ' and ' + str(len(risks) - 1) + ' more'
        return f'Main risks: {risk_str}.'
    if central_modules:
        names = [c.get('name', '') for c in central_modules[:3] if isinstance(c, dict)]
        return f"Central modules: {', '.join(names)}."
    return ''

def _template_trends_sentences(trend_complexity: str, trend_smells: str, regressions: List[str]) -> List[str]:
    """Optional trend and regression sentences."""
    out: List[str] = []
    if trend_complexity != 'unknown' or trend_smells != 'unknown':
        out.append(f'Trends: complexity {trend_complexity}, smells {trend_smells}.')
    if regressions:
        out.append(f"Potential regressions: {'; '.join(regressions[:2])}.")
    return out

def _template_context_sentences(patch_plan: Optional[Dict[str, Any]], knowledge_snippet: str, recent_events_snippet: str) -> List[str]:
    """Optional sentences for patch-plan and recent events. Reference shown in dedicated block (2.9.1)."""
    out: List[str] = []
    patch_sentence = _format_template_patch_plan_sentence(patch_plan)
    if patch_sentence:
        out.append(patch_sentence)
    if recent_events_snippet:
        out.append(f'Recent actions: {recent_events_snippet}.')
    return out

def _format_reference_block(knowledge_snippet: str, max_chars: int=800) -> str:
    """Format Knowledge snippets as a dedicated Reference block (ROADMAP 2.9.1)."""
    if not knowledge_snippet or not knowledge_snippet.strip():
        return ''
    snip = knowledge_snippet.strip()
    if len(snip) > max_chars:
        snip = snip[:max_chars] + '...'
    return '\n\nReference (from documentation):\n' + snip

def _template_interpret(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]=None, knowledge_snippet: str='', recent_events_snippet: str='') -> str:
    """Deterministic 2–4 sentence take from summary and history (ROADMAP 2.9.1: + Recommendation + Reference)."""
    sys = summary.get('system') or {}
    modules = sys.get('modules', 0)
    deps = sys.get('dependencies', 0)
    cycles = sys.get('cycles', 0)
    maturity = summary.get('maturity', 'unknown')
    risks = summary.get('risks') or []
    central = summary.get('central_modules') or []
    trend_complexity = (history.get('trends') or {}).get('complexity', 'unknown')
    trend_smells = (history.get('trends') or {}).get('smells', 'unknown')
    regressions = history.get('regressions') or []
    parts: list[str] = []
    parts.append(_template_structure_sentence(modules, deps, cycles))
    parts.append(f'Syntactic maturity is {maturity}.')
    risks_sentence = _template_risks_sentence(risks, central)
    if risks_sentence:
        parts.append(risks_sentence)
    parts.extend(_template_trends_sentences(trend_complexity, trend_smells, regressions))
    parts.extend(_template_context_sentences(patch_plan, knowledge_snippet, recent_events_snippet))
    out = ' '.join(parts)
    rec_block = _build_recommendation_how_block(risks, knowledge_snippet)
    if rec_block:
        out += rec_block
    ref_block = _format_reference_block(knowledge_snippet)
    if ref_block:
        out += ref_block
    return out

def _build_openai_client(api_key: str, base_url: str | None) -> tuple[Any | None, str | None]:
    """Build OpenAI client instance. Returns (client, reason)."""
    from urllib.parse import urlparse
    try:
        from openai import OpenAI
    except ImportError:
        return (None, 'openai package not installed (pip install openai)')
    kwargs: dict[str, Any] = {'api_key': api_key, 'base_url': base_url}
    if base_url:
        try:
            host = (urlparse(base_url).hostname or '').lower()
            if host in {'127.0.0.1', 'localhost', '::1'}:
                import httpx
                kwargs['http_client'] = httpx.Client(trust_env=False)
        except Exception:
            pass
    return (OpenAI(**kwargs), None)

def _init_primary_openai_client() -> tuple[Any | None, str | None, str | None]:
    """Initialize primary LLM client from OPENAI_* env (typically OpenRouter)."""
    import os
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return (None, None, 'OPENAI_API_KEY not set (add to .env or export; pip install python-dotenv to load .env)')
    base_url = os.environ.get('OPENAI_BASE_URL') or None
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
    client, reason = _build_openai_client(api_key, base_url)
    return (client, model, reason)

def _init_ollama_fallback_client() -> tuple[Any | None, str | None, str | None]:
    """Initialize local Ollama fallback client from OLLAMA_OPENAI_* env (or defaults)."""
    import os
    api_key = os.environ.get('OLLAMA_OPENAI_API_KEY', 'ollama')
    base_url = os.environ.get('OLLAMA_OPENAI_BASE_URL', 'http://127.0.0.1:11434/v1')
    model = os.environ.get('OLLAMA_OPENAI_MODEL', 'qwen2.5-coder:7b')
    client, reason = _build_openai_client(api_key, base_url)
    return (client, model, reason)

def _build_llm_prompt(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]], knowledge_snippet: str, recent_events_snippet: str) -> str:
    """Assemble a concise architect prompt for LLM."""
    patch_desc = _build_llm_patch_desc(patch_plan)
    ref_block = ''
    if knowledge_snippet:
        ref_block = '\n\nReference knowledge (use if relevant):\n' + knowledge_snippet
    events_block = ''
    if recent_events_snippet:
        events_block = '\n\nRecent refactoring events (for context): ' + recent_events_snippet
    return f"You are a software architect. In 2-4 short sentences, summarize the state of this codebase and the main recommendation. Be concrete and concise. If patch operations are planned, mention the most impactful refactorings.\n\nSummary: {summary}\n\nHistory (trends/regressions): {history.get('trends')}, regressions: {history.get('regressions', [])[:3]}{patch_desc}{events_block}{ref_block}"

def _build_ollama_cli_prompt(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]) -> str:
    """Compact prompt for local CLI fallback to avoid long generation stalls."""
    sys_info = summary.get('system') or {}
    modules = sys_info.get('modules', 0)
    deps = sys_info.get('dependencies', 0)
    cycles = sys_info.get('cycles', 0)
    maturity = summary.get('maturity', 'unknown')
    top_risk = (summary.get('risks') or ['none'])[0]
    trends = history.get('trends') or {}
    patch_desc = _build_llm_patch_desc(patch_plan)
    return f"You are a software architect. Reply in exactly 2 short sentences.\nSentence 1: architecture risk level. Sentence 2: one highest-impact refactoring.\n\nMetrics: modules={modules}, dependencies={deps}, cycles={cycles}, maturity={maturity}\nTop risk: {top_risk}\nTrends: complexity={trends.get('complexity', 'unknown')}, smells={trends.get('smells', 'unknown')}, centralization={trends.get('centralization', 'unknown')}{patch_desc}"

def _call_llm_architect(client: Any, model: str, prompt: str, max_tokens: int=350) -> tuple[str | None, str | None]:
    """Call OpenAI chat completions and normalize response shape."""
    import os
    timeout_sec = float(os.environ.get('EURIKA_LLM_TIMEOUT_SEC', '20'))
    try:
        r = client.chat.completions.create(model=model, messages=[{'role': 'user', 'content': prompt}], max_tokens=max_tokens, timeout=timeout_sec)
        if r.choices and r.choices[0].message.content:
            return (r.choices[0].message.content.strip(), None)
        return (None, 'empty LLM response')
    except Exception as e:
        return (None, str(e))

def _call_ollama_cli(model: str, prompt: str) -> tuple[str | None, str | None]:
    """Fallback path via local `ollama run` CLI when HTTP endpoints are unavailable."""
    import os
    import subprocess
    cli_timeout_sec = int(os.environ.get('EURIKA_OLLAMA_CLI_TIMEOUT_SEC', '45'))

    def _run_once(timeout_sec: int | None=None) -> tuple[str | None, str | None]:
        if timeout_sec is None:
            timeout_sec = cli_timeout_sec
        try:
            r = subprocess.run(['ollama', 'run', model, prompt], capture_output=True, text=True, timeout=timeout_sec, check=False)
        except FileNotFoundError:
            return (None, 'ollama CLI not found in PATH')
        except Exception as e:
            return (None, str(e))
        if r.returncode != 0:
            reason = (r.stderr or r.stdout or '').strip() or f'ollama exited with code {r.returncode}'
            return (None, reason)
        text = (r.stdout or '').strip()
        if not text:
            return (None, 'empty ollama CLI response')
        return (text, None)

    def _model_ready_reason() -> str | None:
        try:
            r = subprocess.run(['ollama', 'show', model], capture_output=True, text=True, timeout=20, check=False)
        except Exception as e:
            return str(e)
        if r.returncode == 0:
            return None
        reason = (r.stderr or r.stdout or '').strip() or 'unknown model check failure'
        lowered = reason.lower()
        if 'not found' in lowered or 'no such model' in lowered:
            return f"ollama model '{model}' is not available; run `ollama pull {model}`"
        return f'ollama model check failed: {reason}'
    try:
        text, reason = _run_once()
        if text:
            return (text, None)
        if reason and 'could not connect to ollama server' in reason.lower():
            return (None, 'could not connect to ollama server; start it manually with `ollama serve`')
        if reason and 'timed out' in reason.lower():
            readiness_issue = _model_ready_reason()
            if readiness_issue:
                return (None, readiness_issue)
            return (None, f'{reason} (cli timeout={cli_timeout_sec}s)')
        return (None, reason)
    except Exception as e:
        return (None, str(e))

def _llm_interpret(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]=None, knowledge_snippet: str='', recent_events_snippet: str='') -> tuple[str | None, str | None]:
    """Call LLM for a short architect take. Returns (text, None) on success, (None, reason) on failure.

    Env: OPENAI_API_KEY (required), OPENAI_BASE_URL (e.g. OpenRouter), OPENAI_MODEL (e.g. mistralai/...).
    knowledge_snippet: optional pre-formatted reference knowledge to append to the prompt.
    """
    primary_client, primary_model, init_reason = _init_primary_openai_client()
    prompt = _build_llm_prompt(summary=summary, history=history, patch_plan=patch_plan, knowledge_snippet=knowledge_snippet, recent_events_snippet=recent_events_snippet)
    primary_reason = init_reason
    if primary_client and primary_model:
        llm_text, primary_call_reason = _call_llm_architect(primary_client, primary_model, prompt)
        if llm_text:
            return (llm_text, None)
        primary_reason = primary_call_reason
    fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
    fallback_reason = fallback_init_reason
    if fallback_client and fallback_model:
        fallback_text, fallback_call_reason = _call_llm_architect(fallback_client, fallback_model, prompt)
        if fallback_text:
            return (fallback_text, None)
        fallback_reason = fallback_call_reason
    cli_model = fallback_model or 'qwen2.5-coder:7b'
    cli_prompt = _build_ollama_cli_prompt(summary, history, patch_plan)
    cli_text, cli_reason = _call_ollama_cli(cli_model, cli_prompt)
    if cli_text:
        return (cli_text, None)
    return (None, f"primary LLM failed ({primary_reason or 'unknown'}); ollama HTTP fallback failed ({fallback_reason or 'unknown'}); ollama CLI fallback failed ({cli_reason or 'unknown'})")

def call_llm_with_prompt(prompt: str, max_tokens: int=1024) -> tuple[str | None, str | None]:
    """Call LLM with custom prompt. Same chain: primary -> ollama HTTP -> ollama CLI.
    ROADMAP 3.5.11: chat_send uses this."""
    primary_client, primary_model, init_reason = _init_primary_openai_client()
    primary_reason = init_reason
    if primary_client and primary_model:
        text, err = _call_llm_architect(primary_client, primary_model, prompt, max_tokens=max_tokens)
        if text:
            return (text, None)
        primary_reason = err
    fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
    fallback_reason = fallback_init_reason
    if fallback_client and fallback_model:
        text, err = _call_llm_architect(fallback_client, fallback_model, prompt, max_tokens=max_tokens)
        if text:
            return (text, None)
        fallback_reason = err
    cli_model = fallback_model or 'qwen2.5-coder:7b'
    cli_text, cli_reason = _call_ollama_cli(cli_model, prompt)
    if cli_text:
        return (cli_text, None)
    return (None, f"primary LLM failed ({primary_reason or 'unknown'}); ollama HTTP fallback failed ({fallback_reason or 'unknown'}); ollama CLI fallback failed ({cli_reason or 'unknown'})")

def interpret_architecture(summary: Dict[str, Any], history: Dict[str, Any], use_llm: bool=True, verbose: bool=True, patch_plan: Optional[Dict[str, Any]]=None, knowledge_provider: Optional['KnowledgeProvider']=None, knowledge_topic: Optional[Union[str, List[str]]]=None, recent_events: Optional[List['Event']]=None) -> str:
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
    text, meta = interpret_architecture_with_meta(summary=summary, history=history, use_llm=use_llm, verbose=verbose, patch_plan=patch_plan, knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic, recent_events=recent_events)
    _ = meta
    return text

def interpret_architecture_with_meta(summary: Dict[str, Any], history: Dict[str, Any], use_llm: bool=True, verbose: bool=True, patch_plan: Optional[Dict[str, Any]]=None, knowledge_provider: Optional['KnowledgeProvider']=None, knowledge_topic: Optional[Union[str, List[str]]]=None, recent_events: Optional[List['Event']]=None) -> tuple[str, Dict[str, Any]]:
    """Return architect text with runtime metadata about degraded mode/fallbacks."""
    import sys
    meta: Dict[str, Any] = {'use_llm': bool(use_llm), 'llm_used': False, 'degraded_mode': False, 'degraded_reasons': []}
    knowledge_snippet = _resolve_knowledge_snippet(knowledge_provider, knowledge_topic)
    recent_snippet = _format_recent_events(recent_events) if recent_events else ''
    if use_llm:
        llm_text, reason = _llm_interpret(summary, history, patch_plan, knowledge_snippet, recent_snippet)
        if llm_text:
            meta['llm_used'] = True
            risks = summary.get('risks') or []
            rec_block = _build_recommendation_how_block(risks, knowledge_snippet)
            ref_block = _format_reference_block(knowledge_snippet)
            if rec_block or ref_block:
                llm_text = llm_text.rstrip()
                if rec_block:
                    llm_text += rec_block
                if ref_block:
                    llm_text += ref_block
            return (llm_text, meta)
        meta['degraded_mode'] = True
        if reason:
            if verbose:
                print(f'eurika: architect: using template — {reason}', file=sys.stderr)
            meta['degraded_reasons'].append(f'llm_unavailable:{reason}')
        else:
            meta['degraded_reasons'].append('llm_unavailable:unknown')
    else:
        meta['degraded_mode'] = True
        meta['degraded_reasons'].append('llm_disabled')
    return (_template_interpret(summary, history, patch_plan, knowledge_snippet, recent_snippet), meta)