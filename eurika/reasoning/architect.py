"""
Architect interpretation (ROADMAP §7 — мини-AI).

Produces a short "architect's take" on the codebase from summary + history.
- Template-based by default (no API key, deterministic).
- Optional LLM: set OPENAI_API_KEY; supports OpenAI and OpenRouter (OPENAI_BASE_URL, OPENAI_MODEL).
"""

from __future__ import annotations

from typing import Any, Dict


def _template_interpret(summary: Dict[str, Any], history: Dict[str, Any]) -> str:
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
    return " ".join(parts)


def _llm_interpret(summary: Dict[str, Any], history: Dict[str, Any]) -> tuple[str | None, str | None]:
    """Call LLM for a short architect take. Returns (text, None) on success, (None, reason) on failure.

    Env: OPENAI_API_KEY (required), OPENAI_BASE_URL (e.g. OpenRouter), OPENAI_MODEL (e.g. mistralai/...).
    """
    import sys
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
    prompt = (
        "You are a software architect. In 2-3 short sentences, summarize the state of this codebase "
        "and the main recommendation. Be concrete and concise.\n\n"
        f"Summary: {summary}\n\nHistory (trends/regressions): {history.get('trends')}, regressions: {history.get('regressions', [])[:3]}"
    )
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
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
) -> str:
    """
    Return a short architect's interpretation (2–4 sentences).

    If use_llm is True and OPENAI_API_KEY is set, attempts an LLM call;
    on failure or missing key, falls back to template-based text.
    If verbose is True, prints the fallback reason to stderr.
    """
    import sys
    if use_llm:
        llm_text, reason = _llm_interpret(summary, history)
        if llm_text:
            return llm_text
        if verbose and reason:
            print(f"eurika: architect: using template — {reason}", file=sys.stderr)
    return _template_interpret(summary, history)
