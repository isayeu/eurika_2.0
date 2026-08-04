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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from .architect_helpers import build_llm_patch_desc, build_recommendation_how_block, format_recent_events, format_reference_block, resolve_knowledge_snippet
from .context_sources import build_context_sources
if TYPE_CHECKING:
    from eurika.knowledge import KnowledgeProvider
    from eurika.storage.events import Event
__all__ = ['build_context_sources', 'call_llm_with_prompt', 'get_architect_data', 'interpret_architecture', 'interpret_architecture_with_meta']

def get_architect_data(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]=None, knowledge_snippet: str='', recent_events_snippet: str='') -> Dict[str, Any]:
    """R1 Domain: return structured architect data. Presentation in report/architect_format."""
    sys = summary.get('system') or {}
    return {'structure': {'modules': sys.get('modules', 0), 'dependencies': sys.get('dependencies', 0), 'cycles': sys.get('cycles', 0)}, 'maturity': summary.get('maturity', 'unknown'), 'risks': summary.get('risks') or [], 'central_modules': summary.get('central_modules') or [], 'trends': history.get('trends') or {}, 'regressions': history.get('regressions') or [], 'patch_plan': patch_plan, 'knowledge_snippet': knowledge_snippet, 'recent_events_snippet': recent_events_snippet}

def _minimal_template_format(data: Dict[str, Any]) -> str:
    """Minimal format when no formatter injected (no L5 dependency)."""
    s = data.get('structure') or {}
    m, d, c = (s.get('modules', 0), s.get('dependencies', 0), s.get('cycles', 0))
    mat = data.get('maturity', 'unknown')
    risks = data.get('risks') or []
    top = '; '.join((str(r) for r in risks[:3])) if risks else 'none'
    return f'The codebase has {m} modules, {d} dependencies and {c} cycles. Maturity: {mat}. Main risks: {top}.'

def _template_interpret(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]=None, knowledge_snippet: str='', recent_events_snippet: str='', *, formatter: Optional[Callable[[Dict[str, Any]], str]]=None) -> str:
    """Format architect data. formatter from report/architect_format (injected by caller)."""
    data = get_architect_data(summary, history, patch_plan, knowledge_snippet, recent_events_snippet)
    if formatter:
        return formatter(data)
    return _minimal_template_format(data)

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
    patch_desc = build_llm_patch_desc(patch_plan)
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
    patch_desc = build_llm_patch_desc(patch_plan)
    return f"You are a software architect. Reply in exactly 2 short sentences.\nSentence 1: architecture risk level. Sentence 2: one highest-impact refactoring.\n\nMetrics: modules={modules}, dependencies={deps}, cycles={cycles}, maturity={maturity}\nTop risk: {top_risk}\nTrends: complexity={trends.get('complexity', 'unknown')}, smells={trends.get('smells', 'unknown')}, centralization={trends.get('centralization', 'unknown')}{patch_desc}"

def _call_litellm(prompt: str, max_tokens: int=350) -> tuple[str | None, str | None]:
    """Try litellm first (unified OpenAI/Ollama/OpenRouter). Returns (text, None) or (None, reason)."""
    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError:
        return (None, 'litellm not installed')
    import os
    api_key = os.environ.get('OPENAI_API_KEY')
    base = os.environ.get('OPENAI_BASE_URL') or ''
    model = os.environ.get('OPENAI_MODEL') or os.environ.get('OLLAMA_OPENAI_MODEL', 'qwen2.5-coder:7b')
    if 'openrouter' in base.lower():
        model = f'openrouter/{model}' if not model.startswith('openrouter/') else model
    elif api_key and (not base):
        model = model if '/' in model else f'openai/{model}'
    elif not model.startswith('ollama/'):
        model = f"ollama/{model.split('/')[-1]}"
    timeout = float(os.environ.get('EURIKA_LLM_TIMEOUT_SEC', '60'))
    try:
        r = litellm.completion(model=model, messages=[{'role': 'user', 'content': prompt}], max_tokens=max_tokens, timeout=timeout)
        if r and r.choices and r.choices[0].message.content:
            return (r.choices[0].message.content.strip(), None)
        return (None, 'empty litellm response')
    except Exception as e:
        return (None, str(e))

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

def _ollama_preflight_check(model: str) -> str | None:
    """Быстрая проверка: Ollama запущен и модель доступна. None если ок. При timeout пропускаем (daemon может быть занят)."""
    import subprocess
    try:
        r = subprocess.run(['ollama', 'show', model], capture_output=True, text=True, timeout=5, check=False, stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            return None
        err = (r.stderr or r.stdout or '').strip().lower()
        if 'not found' in err or 'no such model' in err:
            return f"модель '{model}' не найдена — выполните `ollama pull {model}`"
        if 'could not connect' in err or 'connection refused' in err:
            return 'Ollama не отвечает — запустите `ollama serve`'
        if 'timed out' in err:
            return None
        return f'ollama show: {err[:200]}'
    except FileNotFoundError:
        return 'ollama не найден в PATH'
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        return str(e)

def _call_ollama_cli(model: str, prompt: str, timeout_override: int | None=None) -> tuple[str | None, str | None]:
    """Fallback path via local `ollama run` CLI when HTTP endpoints are unavailable.
    EURIKA_OLLAMA_CLI_TIMEOUT_SEC: 0=unlimited, else seconds (default 120).
    timeout_override: use instead of env (e.g. EURIKA_LLM_EXTRACT_TIMEOUT_SEC for extract)."""
    import os
    import subprocess
    import threading
    import time
    if timeout_override is not None:
        cli_timeout_sec = timeout_override if timeout_override > 0 else None
    else:
        raw = os.environ.get('EURIKA_OLLAMA_CLI_TIMEOUT_SEC', '120')
        try:
            val = int(raw) if raw else 120
            cli_timeout_sec = None if val <= 0 else val
        except (ValueError, TypeError):
            cli_timeout_sec = 120
    preflight = _ollama_preflight_check(model)
    if preflight:
        _trace_architect(f'ollama preflight: {preflight}')
        return (None, preflight)
    progress_interval = 15
    from eurika.utils.env import env_bool
    show_progress = env_bool("EURIKA_OLLAMA_PROGRESS", default=True)
    if cli_timeout_sec:
        _trace_architect(f'ollama CLI: ожидание до {cli_timeout_sec}s...')
    _result: list = []

    def _run_subprocess(timeout_sec: int | None) -> None:
        t = timeout_sec if timeout_sec is not None else cli_timeout_sec
        try:
            r = subprocess.run(['ollama', 'run', model, prompt], capture_output=True, text=True, timeout=t, check=False, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            _result.append((None, 'ollama CLI not found in PATH'))
            return
        except subprocess.TimeoutExpired:
            _result.append((None, f'timed out after {t}s'))
            return
        except OSError as e:
            _result.append((None, str(e)))
            return
        except Exception as e:
            _result.append((None, str(e)))
            return
        if r.returncode != 0:
            reason = (r.stderr or r.stdout or '').strip() or f'ollama exited with code {r.returncode}'
            _result.append((None, reason))
            return
        text = (r.stdout or '').strip()
        if not text:
            _result.append((None, 'empty ollama CLI response'))
            return
        _result.append((text, None))

    def _run_once(timeout_sec: int | None=None) -> tuple[str | None, str | None]:
        _result.clear()
        t = timeout_sec if timeout_sec is not None else cli_timeout_sec
        if show_progress and t and (t >= progress_interval):
            th = threading.Thread(target=_run_subprocess, args=(t,), daemon=True)
            th.start()
            start = time.monotonic()
            last_printed = 0
            while th.is_alive():
                time.sleep(5)
                elapsed = int(time.monotonic() - start)
                if elapsed - last_printed >= progress_interval:
                    _trace_architect(f'  ... {elapsed}s (ollama обрабатывает)')
                    last_printed = elapsed
            th.join(timeout=2)
            if _result:
                return _result[0]
            return (None, 'internal: no result from subprocess')
        _run_subprocess(t)
        return _result[0] if _result else (None, 'internal: no result')

    def _model_ready_reason() -> str | None:
        try:
            r = subprocess.run(['ollama', 'show', model], capture_output=True, text=True, timeout=20, check=False, stdin=subprocess.DEVNULL)
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
            from eurika.utils.text import strip_ansi
            return (strip_ansi(text).strip(), None)
        if reason and 'could not connect to ollama server' in reason.lower():
            return (None, 'could not connect to ollama server; start it manually with `ollama serve`')
        if reason and 'timed out' in reason.lower():
            readiness_issue = _model_ready_reason()
            if readiness_issue:
                return (None, readiness_issue)
            return (None, f'{reason}' + (f' (cli timeout={cli_timeout_sec}s)' if cli_timeout_sec else ''))
        return (None, reason)
    except Exception as e:
        return (None, str(e))

def _chat_llm_provider() -> str:
    """Chat routing: auto | openai | codex | ollama (set by Qt adapter or tests)."""
    import os
    raw = (os.environ.get("EURIKA_CHAT_PROVIDER") or "auto").strip().lower()
    if raw in {"openai", "codex", "ollama", "auto"}:
        return raw
    return "auto"


def _call_remote_openai_chat(prompt: str, max_tokens: int) -> tuple[str | None, str | None]:
    """OpenAI / Codex path: primary HTTP client, then litellm fallback."""
    primary_client, primary_model, init_reason = _init_primary_openai_client()
    if not primary_client or not primary_model:
        return (None, init_reason or "OPENAI_API_KEY not set")
    text, err = _call_llm_architect(primary_client, primary_model, prompt, max_tokens=max_tokens)
    if text:
        return (text, None)
    litellm_text, litellm_reason = _call_litellm(prompt, max_tokens=max_tokens)
    if litellm_text:
        return (litellm_text, None)
    return (None, f"OpenAI failed ({err or 'unknown'}; litellm: {litellm_reason or 'n/a'})")


def _should_use_litellm_first() -> bool:
    """Use litellm only when remote API (OpenAI/OpenRouter); skip for local Ollama (litellm has ~20s extra latency)."""
    import os
    api_key = os.environ.get('OPENAI_API_KEY')
    base = (os.environ.get('OPENAI_BASE_URL') or '').lower()
    if not api_key:
        return False
    if 'openrouter' in base or ('127.0.0.1' not in base and 'localhost' not in base):
        return True
    return False

def _trace_architect(msg: str) -> None:
    import logging
    logging.getLogger('eurika.reasoning.architect').info(f'eurika: architect — {msg}')

def _llm_interpret(summary: Dict[str, Any], history: Dict[str, Any], patch_plan: Optional[Dict[str, Any]]=None, knowledge_snippet: str='', recent_events_snippet: str='') -> tuple[str | None, str | None]:
    """Call LLM for a short architect take. Returns (text, None) on success, (None, reason) on failure.

    Local Ollama: ollama CLI first (fast), then ollama HTTP. openai's /v1/chat/completions is ~40x slower than native ollama run.
    Remote API (OpenAI/OpenRouter): litellm -> primary -> ollama fallbacks.
    """
    prompt = _build_llm_prompt(summary=summary, history=history, patch_plan=patch_plan, knowledge_snippet=knowledge_snippet, recent_events_snippet=recent_events_snippet)
    if _should_use_litellm_first():
        _trace_architect('trying litellm (remote API)...')
        litellm_text, litellm_reason = _call_litellm(prompt, max_tokens=350)
        if litellm_text:
            _trace_architect('litellm ok')
            return (litellm_text, None)
        _trace_architect(f'litellm failed: {litellm_reason}; trying primary OpenAI...')
        primary_client, primary_model, init_reason = _init_primary_openai_client()
        primary_reason = init_reason or litellm_reason
        if primary_client and primary_model:
            llm_text, primary_call_reason = _call_llm_architect(primary_client, primary_model, prompt)
            if llm_text:
                _trace_architect('primary OpenAI ok')
                return (llm_text, None)
            _trace_architect(f'primary failed: {primary_call_reason}; trying ollama HTTP...')
            primary_reason = primary_call_reason
        fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
        fallback_reason = fallback_init_reason
        if fallback_client and fallback_model:
            fallback_text, fallback_call_reason = _call_llm_architect(fallback_client, fallback_model, prompt)
            if fallback_text:
                _trace_architect('ollama HTTP ok')
                return (fallback_text, None)
            _trace_architect(f'ollama HTTP failed: {fallback_call_reason}; trying ollama CLI...')
            fallback_reason = fallback_call_reason
        cli_model = fallback_model or 'qwen2.5-coder:7b'
        _trace_architect(f'architect: ollama CLI fallback (model={cli_model}), до 120s...')
        cli_prompt = _build_ollama_cli_prompt(summary, history, patch_plan)
        cli_text, cli_reason = _call_ollama_cli(cli_model, cli_prompt)
        if cli_text:
            _trace_architect('ollama CLI ok')
            return (cli_text, None)
        return (None, f"primary failed ({primary_reason or 'unknown'}); ollama HTTP failed ({fallback_reason or 'unknown'}); ollama CLI failed ({cli_reason or 'unknown'})")
    import os
    cli_model = os.environ.get('OLLAMA_OPENAI_MODEL', 'qwen2.5-coder:7b')
    _trace_architect(f'architect: ollama CLI (model={cli_model}), до 120s...')
    cli_prompt = _build_ollama_cli_prompt(summary, history, patch_plan)
    cli_text, cli_reason = _call_ollama_cli(cli_model, cli_prompt)
    if cli_text:
        _trace_architect('ollama CLI ok')
        return (cli_text, None)
    _trace_architect(f'ollama CLI failed: {cli_reason}; trying ollama HTTP...')
    fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
    if fallback_client and fallback_model:
        fallback_text, _ = _call_llm_architect(fallback_client, fallback_model, prompt)
        if fallback_text:
            _trace_architect('ollama HTTP ok')
            return (fallback_text, None)
    return (None, f"ollama CLI failed ({cli_reason or 'unknown'}); ollama HTTP failed ({fallback_init_reason or 'unknown'})")

def call_llm_with_prompt(prompt: str, max_tokens: int=1024) -> tuple[str | None, str | None]:
    """Call LLM with custom prompt. Local Ollama: CLI first (fast), then HTTP. Remote: litellm -> primary -> ollama.
    ROADMAP 3.5.11: chat_send uses this."""
    provider = _chat_llm_provider()
    if provider in {"openai", "codex"}:
        return _call_remote_openai_chat(prompt, max_tokens)
    if provider == "ollama":
        import os
        cli_model = os.environ.get('OLLAMA_OPENAI_MODEL', 'qwen2.5-coder:7b')
        cli_text, cli_reason = _call_ollama_cli(cli_model, prompt)
        if cli_text:
            return (cli_text, None)
        fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
        http_reason = fallback_init_reason
        if fallback_client and fallback_model:
            text, http_reason = _call_llm_architect(fallback_client, fallback_model, prompt, max_tokens=max_tokens)
            if text:
                return (text, None)
        return (None, f"ollama CLI and HTTP failed (CLI: {cli_reason or 'unknown'}; HTTP: {http_reason or 'unknown'})")
    if not _should_use_litellm_first():
        import os
        cli_model = os.environ.get('OLLAMA_OPENAI_MODEL', 'qwen2.5-coder:7b')
        cli_text, cli_reason = _call_ollama_cli(cli_model, prompt)
        if cli_text:
            return (cli_text, None)
        fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
        http_reason = fallback_init_reason
        if fallback_client and fallback_model:
            text, http_reason = _call_llm_architect(fallback_client, fallback_model, prompt, max_tokens=max_tokens)
            if text:
                return (text, None)
        return (None, f"ollama CLI and HTTP failed (CLI: {cli_reason or 'unknown'}; HTTP: {http_reason or 'unknown'})")
    text, _ = _call_litellm(prompt, max_tokens=max_tokens)
    if text:
        return (text, None)
    primary_client, primary_model, init_reason = _init_primary_openai_client()
    if primary_client and primary_model:
        text, err = _call_llm_architect(primary_client, primary_model, prompt, max_tokens=max_tokens)
        if text:
            return (text, None)
        init_reason = err
    fallback_client, fallback_model, fallback_init_reason = _init_ollama_fallback_client()
    if fallback_client and fallback_model:
        text, err = _call_llm_architect(fallback_client, fallback_model, prompt, max_tokens=max_tokens)
        if text:
            return (text, None)
        fallback_init_reason = err
    cli_model = fallback_model or 'qwen2.5-coder:7b'
    cli_text, cli_reason = _call_ollama_cli(cli_model, prompt)
    if cli_text:
        return (cli_text, None)
    return (None, f"primary failed ({init_reason or 'unknown'}); ollama HTTP failed ({fallback_init_reason or 'unknown'}); ollama CLI failed ({cli_reason or 'unknown'})")

def interpret_architecture(summary: Dict[str, Any], history: Dict[str, Any], use_llm: bool=True, verbose: bool=True, patch_plan: Optional[Dict[str, Any]]=None, knowledge_provider: Optional['KnowledgeProvider']=None, knowledge_topic: Optional[Union[str, List[str]]]=None, recent_events: Optional[List['Event']]=None, *, template_formatter: Optional[Callable[[Dict[str, Any]], str]]=None) -> str:
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
    text, meta = interpret_architecture_with_meta(summary=summary, history=history, use_llm=use_llm, verbose=verbose, patch_plan=patch_plan, knowledge_provider=knowledge_provider, knowledge_topic=knowledge_topic, recent_events=recent_events, template_formatter=template_formatter)
    _ = meta
    return text

def _extracted_block_505(llm_text: str, rec_block: str, ref_block: str) -> str:
    llm_text = llm_text.rstrip()
    if rec_block:
        llm_text += rec_block
    if ref_block:
        llm_text += ref_block
    return llm_text

def interpret_architecture_with_meta(summary: Dict[str, Any], history: Dict[str, Any], use_llm: bool=True, verbose: bool=True, patch_plan: Optional[Dict[str, Any]]=None, knowledge_provider: Optional['KnowledgeProvider']=None, knowledge_topic: Optional[Union[str, List[str]]]=None, recent_events: Optional[List['Event']]=None, *, template_formatter: Optional[Callable[[Dict[str, Any]], str]]=None) -> tuple[str, Dict[str, Any]]:
    """Return architect text with runtime metadata about degraded mode/fallbacks.
    R2 Fallback: knowledge resolution failures yield empty snippet; cycle completes deterministically."""
    meta: Dict[str, Any] = {'use_llm': bool(use_llm), 'llm_used': False, 'degraded_mode': False, 'degraded_reasons': []}
    try:
        knowledge_snippet = resolve_knowledge_snippet(knowledge_provider, knowledge_topic)
    except Exception:
        knowledge_snippet = ''
    recent_snippet = format_recent_events(recent_events) if recent_events else ''
    if use_llm:
        llm_text, reason = _llm_interpret(summary, history, patch_plan, knowledge_snippet, recent_snippet)
        if llm_text:
            meta['llm_used'] = True
            risks = summary.get('risks') or []
            rec_block = build_recommendation_how_block(risks, knowledge_snippet)
            ref_block = format_reference_block(knowledge_snippet)
            if rec_block or ref_block:
                llm_text = _extracted_block_505(llm_text, rec_block, ref_block)
            return (llm_text, meta)
        meta['degraded_mode'] = True
        _trace_architect(f"LLM failed, using template — {reason or 'unknown'}")
        meta['degraded_reasons'].append(f"llm_unavailable:{reason or 'unknown'}")
    else:
        _trace_architect('LLM disabled (--no-llm), using template')
        meta['degraded_mode'] = True
        meta['degraded_reasons'].append('llm_disabled')
    return (_template_interpret(summary, history, patch_plan, knowledge_snippet, recent_snippet, formatter=template_formatter), meta)