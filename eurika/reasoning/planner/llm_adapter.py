"""
LLM hints for patch planning (ROADMAP 2.9.2).

For god_module, hub, bottleneck: optional Ollama call to suggest split points.
Result merged into patch_plan hints; fallback to graph heuristics when unavailable.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_HINT_CALLS = 0
_HINT_BUDGET_START = 0.0
_HINT_CACHE: Dict[tuple[str, ...], List[str]] = {}
_HINT_CIRCUIT_BROKEN = False


def _use_llm_hints() -> bool:
    """Check env to enable/disable LLM hints. Default: enabled."""
    v = os.environ.get("EURIKA_USE_LLM_HINTS", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_OPENAI_MODEL", "qwen2.5-coder:7b")


def _max_hint_calls() -> int:
    """Per-run cap for planner LLM calls. 0 or -1 = unlimited."""
    raw = os.environ.get("EURIKA_LLM_HINTS_MAX_CALLS", "15")
    try:
        v = int(raw)
        return -1 if v <= 0 else v
    except ValueError:
        return 15


def _hints_budget_sec() -> float:
    """Per-run wall-clock budget for planner LLM calls (seconds). 0 or -1 = unlimited."""
    raw = os.environ.get("EURIKA_LLM_HINTS_BUDGET_SEC", "300")
    try:
        v = float(raw)
        return -1.0 if v <= 0 else v
    except ValueError:
        return 300.0


def _reset_hint_runtime_state() -> None:
    """Reset in-process counters/cache (used by tests)."""
    global _HINT_CALLS, _HINT_BUDGET_START, _HINT_CACHE, _HINT_CIRCUIT_BROKEN, _EXTRACT_PATCH_CALLS
    _HINT_CALLS = 0
    _HINT_BUDGET_START = 0.0
    _HINT_CACHE = {}
    _HINT_CIRCUIT_BROKEN = False
    _EXTRACT_PATCH_CALLS = 0


def _llm_hint_allowed() -> bool:
    """Runtime guard against long diagnose due to many/slow LLM hints."""
    global _HINT_BUDGET_START
    if _HINT_CIRCUIT_BROKEN:
        return False
    max_calls = _max_hint_calls()
    if max_calls >= 0 and _HINT_CALLS >= max_calls:
        return False
    budget = _hints_budget_sec()
    if budget > 0:
        now = time.monotonic()
        if _HINT_BUDGET_START <= 0.0:
            _HINT_BUDGET_START = now
        if (now - _HINT_BUDGET_START) > budget:
            return False
    return True


def _register_llm_hint_call() -> None:
    global _HINT_CALLS
    _HINT_CALLS += 1


def _disable_llm_hints_for_run() -> None:
    """Circuit-breaker after hard timeout/connectivity failures."""
    global _HINT_CALLS, _HINT_CIRCUIT_BROKEN
    _HINT_CIRCUIT_BROKEN = True
    max_calls = _max_hint_calls()
    if max_calls >= 0:
        _HINT_CALLS = max_calls


def llm_hint_runtime_stats() -> Dict[str, Any]:
    """Runtime counters for diagnose observability."""
    max_calls = _max_hint_calls()
    budget_sec = _hints_budget_sec()
    elapsed_sec = 0.0
    if _HINT_BUDGET_START > 0.0:
        elapsed_sec = max(0.0, time.monotonic() - _HINT_BUDGET_START)
    calls_exhausted = max_calls >= 0 and _HINT_CALLS >= max_calls
    time_exhausted = budget_sec > 0 and _HINT_BUDGET_START > 0.0 and elapsed_sec > budget_sec
    budget_exhausted = bool(calls_exhausted or time_exhausted)
    return {
        "calls_used": int(_HINT_CALLS),
        "max_calls": int(max_calls),
        "budget_sec": float(budget_sec),
        "elapsed_sec": round(float(elapsed_sec), 3),
        "budget_exhausted": budget_exhausted,
        "circuit_breaker_triggered": bool(_HINT_CIRCUIT_BROKEN),
    }


def _build_planner_prompt(
    smell_type: str,
    module_name: str,
    graph_context: Dict[str, Any],
) -> str:
    """Build a compact prompt for split/facade suggestions."""
    if smell_type == "god_module":
        imp_from = graph_context.get("imports_from", [])[:5]
        imp_by = graph_context.get("imported_by", [])[:5]
        return (
            f"Module {module_name} is a god module (too many responsibilities). "
            f"It imports from: {imp_from}. Imported by: {imp_by}. "
            "In 1-3 short bullet points, suggest concrete split points or extraction targets. "
            "Example: 'Extract validation logic into module_x'; 'Group reporting in module_y'. "
            "Reply with bullet points only, no preamble."
        )
    if smell_type == "hub":
        imp_from = graph_context.get("imports_from", [])[:5]
        imp_by = graph_context.get("imported_by", [])[:5]
        return (
            f"Module {module_name} is a hub (high fan-out). It imports from: {imp_from}. Imported by: {imp_by}. "
            "In 1-3 short bullet points, suggest how to reduce fan-out or introduce abstractions. "
            "Reply with bullet points only, no preamble."
        )
    if smell_type == "bottleneck":
        callers = graph_context.get("callers", [])[:5]
        return (
            f"Module {module_name} is a bottleneck (high fan-in). Callers: {callers}. "
            "In 1-3 short bullet points, suggest facade or API boundary. "
            "Example: 'Create api.py re-exporting public symbols'. Reply with bullet points only, no preamble."
        )
    return ""


def _use_llm_extract_hints() -> bool:
    """Check env for long_function extract-method LLM hints. Default: off to avoid latency."""
    v = os.environ.get("EURIKA_USE_LLM_EXTRACT_HINTS", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _extract_function_source(content: str, function_name: str) -> str | None:
    """Get function source by name (first 80 lines). Returns None if not found."""
    try:
        import ast
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                start = (node.lineno or 1) - 1
                end = min((node.end_lineno or node.lineno or 0), start + 80)
                lines = content.splitlines()
                return "\n".join(lines[start:end])
    except (SyntaxError, ValueError):
        pass
    return None


def _build_extract_method_prompt(
    function_name: str,
    function_source: str,
    oss_snippets: list[str] | None = None,
) -> str:
    """Prompt for LLM to suggest extract-method steps. Learning from GitHub: oss_snippets as few-shot examples."""
    preview = function_source[:1500] + ("..." if len(function_source) > 1500 else "")
    base = (
        f"Python function '{function_name}' is too long. Here is its source:\n\n```python\n{preview}\n```\n\n"
        "In 1-3 short bullet points, suggest how to extract a coherent helper (which block to move, what to name it). "
        "Example: 'Extract the validation block (lines 15-25) to _validate_input(data)'. "
    )
    if oss_snippets:
        ref_block = "\n\nReference (OSS examples):\n" + "\n\n".join(oss_snippets[:2])
        base += ref_block + "\n\n"
    base += "Reply with bullet points only, no preamble."
    return base


def ask_llm_extract_method_hints(
    file_path: "os.PathLike[str] | str",
    function_name: str,
    project_root: "os.PathLike[str] | str | None" = None,
) -> List[str]:
    """
    Ask LLM for extract-method hints (ROADMAP operability: internet/LLM).
    Learning from GitHub Phase 3: when project_root given, prompt enriched with OSS snippets.

    Returns list of hint strings; empty when disabled, on failure, or budget exhausted.
    Uses same budget/circuit breaker as ask_ollama_split_hints.
    """
    if not _use_llm_extract_hints():
        return []
    if not function_name or not function_name.strip():
        return []
    cache_key = ("long_function_extract", f"{file_path}:{function_name}")
    cached = _HINT_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)
    if not _llm_hint_allowed():
        _HINT_CACHE[cache_key] = []
        return []
    try:
        content = open(file_path, encoding="utf-8").read()
    except OSError:
        _HINT_CACHE[cache_key] = []
        return []
    src = _extract_function_source(content, function_name)
    if not src or len(src) < 30:
        _HINT_CACHE[cache_key] = []
        return []
    oss_snippets: list[str] = []
    if project_root:
        try:
            from eurika.api.ops import _load_oss_snippets_for_smell

            root = Path(project_root).resolve()
            oss_snippets = _load_oss_snippets_for_smell(root, "long_function", max_count=2)
        except Exception:
            pass
    prompt = _build_extract_method_prompt(function_name, src, oss_snippets=oss_snippets or None)
    _register_llm_hint_call()
    try:
        from eurika.reasoning.architect import _call_ollama_cli

        text, reason = _call_ollama_cli(_ollama_model(), prompt)
        if text:
            hints = _parse_llm_hints(text)
            _HINT_CACHE[cache_key] = hints
            return list(hints)
        if reason and (
            "timed out" in reason.lower() or "could not connect to ollama server" in reason.lower()
        ):
            _disable_llm_hints_for_run()
    except Exception:
        pass
    _HINT_CACHE[cache_key] = []
    return []


def _use_llm_extract() -> bool:
    """Check EURIKA_USE_LLM_EXTRACT (REFACTOR_CODE_SMELL_PLAN Phase 3). Default: off."""
    return os.environ.get("EURIKA_USE_LLM_EXTRACT", "0").strip().lower() in ("1", "true", "yes")


_EXTRACT_PATCH_CALLS = 0


def _max_extract_patch_calls() -> int:
    """Separate budget for ask_llm_extract_patch. 0 or -1 = unlimited."""
    raw = os.environ.get("EURIKA_LLM_EXTRACT_MAX_CALLS", "15")
    try:
        v = int(raw)
        return -1 if v <= 0 else v
    except ValueError:
        return 15


def _llm_extract_allowed() -> bool:
    """Budget check for LLM extract — independent of architect _HINT_CALLS."""
    max_calls = _max_extract_patch_calls()
    return max_calls < 0 or _EXTRACT_PATCH_CALLS < max_calls


def _build_extract_patch_prompt(function_name: str, full_source: str, oss_snippets: list[str] | None) -> str:
    """Prompt for LLM to generate refactored file (extract helper from long function)."""
    preview = full_source[:2500] + ("..." if len(full_source) > 2500 else "")
    base = (
        f"Refactor the Python file below. Function '{function_name}' is too long. "
        "Extract a coherent block of logic into a helper function (e.g. _compute_xyz). "
        "Output ONLY the complete refactored file content, no explanation. "
        "Preserve ALL functions and classes in the file; do not remove any. Preserve semantics and imports.\n\n"
        f"```python\n{preview}\n```\n\n"
    )
    if oss_snippets:
        ref_label = "OSS before/after (Phase 5):" if any("Before:" in s for s in oss_snippets) else "OSS Reference (extract-style examples):"
        base += f"\n{ref_label}\n" + "\n".join(oss_snippets[:3]) + "\n\n"
    base += "Reply with the full refactored Python code only (inside ```python ... ``` or raw)."
    return base


def _top_level_names(source: str) -> set[str]:
    """Extract top-level def/class names (excluding private _names) from Python source."""
    try:
        import ast
        tree = ast.parse(source)
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    names.add(node.name)
        return names
    except SyntaxError:
        return set()


def _validate_llm_extract_preserves_names(original: str, refactored: str) -> bool:
    """Reject LLM output that drops top-level public names from the original file."""
    orig_names = _top_level_names(original)
    if not orig_names:
        return True
    new_names = _top_level_names(refactored)
    missing = orig_names - new_names
    return len(missing) == 0


def ask_llm_extract_patch(
    file_path: "os.PathLike[str] | str",
    function_name: str,
    project_root: "os.PathLike[str] | str | None" = None,
) -> Optional[str]:
    """
    Ask LLM to generate refactored file content (extract helper from long function).
    REFACTOR_CODE_SMELL_PLAN Phase 3. Returns new file content or None.

    Uses separate budget (EURIKA_LLM_EXTRACT_MAX_CALLS, default 15) so architect
    hints during diagnose do not exhaust it.
    """
    global _EXTRACT_PATCH_CALLS
    if not _use_llm_extract():
        return None

    if not function_name or not str(function_name).strip():
        return None
    cache_key = ("llm_extract_patch", f"{file_path}:{function_name}")
    cached = _HINT_CACHE.get(cache_key)
    if cached is not None:
        return cached[0] if isinstance(cached, (list, tuple)) and cached else None
    if not _llm_extract_allowed():
        return None
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None
    if len(content) < 50:
        _HINT_CACHE[cache_key] = []
        return None
    oss: list[str] = []
    if project_root:
        try:
            from eurika.api.ops import _load_oss_before_after_for_smell, _load_oss_snippets_for_smell
            root = Path(project_root).resolve()
            before_after = _load_oss_before_after_for_smell(root, "long_function", max_count=1)
            oss = before_after or _load_oss_snippets_for_smell(root, "long_function", max_count=4)
        except Exception:
            pass
    prompt = _build_extract_patch_prompt(function_name, content, oss or None)
    _EXTRACT_PATCH_CALLS += 1
    try:
        from eurika.reasoning.architect import _call_ollama_cli
        text, _reason = _call_ollama_cli(_ollama_model(), prompt, timeout_override=0)
        if not text or not text.strip():
            _HINT_CACHE[cache_key] = []
            return None
        # Extract code block or use raw
        code_match = re.search(r"```(?:python)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
        raw = (code_match.group(1).strip() if code_match else text.strip())
        try:
            import ast
            ast.parse(raw)
        except SyntaxError:
            _HINT_CACHE[cache_key] = []
            return None
        if not _validate_llm_extract_preserves_names(content, raw):
            _HINT_CACHE[cache_key] = []
            return None
        _HINT_CACHE[cache_key] = [raw]
        return raw
    except Exception:
        pass
    _HINT_CACHE[cache_key] = []
    return None


def _parse_llm_hints(text: str) -> List[str]:
    """Extract hint-like lines from LLM response. Filters noise."""
    if not text or not isinstance(text, str):
        return []
    hints: List[str] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        # Drop empty, too short, or meta lines
        if not line or len(line) < 10:
            continue
        # Drop common LLM boilerplate
        if re.match(r"^(here are|sure[,.!]|certainly[,.!]|i (would|suggest|recommend))", line, re.I):
            continue
        # Unwrap bullet/number prefixes
        m = re.match(r"^[\-\*\d\.\)]+\s*", line)
        if m:
            line = line[m.end() :].strip()
        if line and len(line) >= 10 and line not in hints:
            hints.append(line[:200])  # Cap length
    return hints[:5]  # At most 5 hints


def _fetch_knowledge_for_planner_hints(project_root: str | Path, smell_type: str, max_chars: int = 500) -> str:
    """Fetch knowledge snippet for planner LLM prompt (ROADMAP 3.6.6). Cache-only (rate_limit=0)."""
    try:
        from eurika.knowledge import (
            CompositeKnowledgeProvider,
            LocalKnowledgeProvider,
            OfficialDocsProvider,
            OSSPatternProvider,
            PEPProvider,
            ReleaseNotesProvider,
            SMELL_TO_KNOWLEDGE_TOPICS,
            StructuredKnowledge,
        )
        root = Path(project_root)
        topics = list(SMELL_TO_KNOWLEDGE_TOPICS.get(smell_type, ["architecture_refactor"]))
        cache_dir = root / ".eurika" / "knowledge_cache"
        ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
        oss_path = root / ".eurika" / "pattern_library.json"
        provider = CompositeKnowledgeProvider([
            LocalKnowledgeProvider(root / "eurika_knowledge.json"),
            OSSPatternProvider(oss_path),
            PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
            OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
            ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
        ])
        all_fragments: List[Dict[str, Any]] = []
        for t in topics[:3]:
            kn = provider.query(t.strip())
            if isinstance(kn, StructuredKnowledge) and (not kn.is_empty()):
                for f in kn.fragments:
                    if isinstance(f, dict):
                        all_fragments.append(f)
        if not all_fragments:
            return ""
        lines: List[str] = []
        for f in all_fragments[:5]:
            title = f.get("title") or f.get("name", "")
            content = f.get("content") or f.get("text") or str(f)
            lines.append(f"- {title}: {content[:250]}".rstrip() + ("..." if len(str(content)) > 250 else ""))
        snip = "\n".join(lines)
        return snip[:max_chars] + ("..." if len(snip) > max_chars else "")
    except Exception:
        return ""


def ask_ollama_split_hints(
    smell_type: str,
    module_name: str,
    graph_context: Dict[str, Any],
    *,
    project_root: Optional[str | Path] = None,
) -> List[str]:
    """
    Ask Ollama for split/facade suggestions (ROADMAP 2.9.2, 3.6.6).

    Returns list of hint strings; empty on failure or when disabled.
    When project_root is provided, prompt is enriched with Knowledge Layer (ROADMAP 3.6.6).
    """
    if not _use_llm_hints():
        return []
    if smell_type not in ("god_module", "hub", "bottleneck"):
        return []
    prompt = _build_planner_prompt(smell_type, module_name, graph_context)
    if not prompt:
        return []
    if project_root:
        knowledge_snippet = _fetch_knowledge_for_planner_hints(project_root, smell_type)
        if knowledge_snippet:
            prompt = f"{prompt}\n\nReference (from documentation):\n{knowledge_snippet}"
    cache_key = (smell_type, module_name, str(project_root or ""))
    cached = _HINT_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)
    if not _llm_hint_allowed():
        _HINT_CACHE[cache_key] = []
        return []
    _register_llm_hint_call()
    try:
        from eurika.reasoning.architect import _call_ollama_cli

        text, reason = _call_ollama_cli(_ollama_model(), prompt)
        if text:
            hints = _parse_llm_hints(text)
            _HINT_CACHE[cache_key] = hints
            return list(hints)
        if reason and (
            "timed out" in reason.lower() or "could not connect to ollama server" in reason.lower()
        ):
            _disable_llm_hints_for_run()
    except Exception:
        pass
    _HINT_CACHE[cache_key] = []
    return []
