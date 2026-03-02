"""Shim: re-export from planner.llm_adapter (ROADMAP v3.0 Stage 1)."""
from eurika.reasoning.planner.llm_adapter import (  # noqa: F401
    _build_planner_prompt,
    _parse_llm_hints,
    _reset_hint_runtime_state,
    ask_llm_extract_method_hints,
    ask_llm_extract_patch,
    ask_ollama_split_hints,
    llm_hint_runtime_stats,
)

__all__ = [
    "_build_planner_prompt",
    "_parse_llm_hints",
    "_reset_hint_runtime_state",
    "ask_llm_extract_method_hints",
    "ask_llm_extract_patch",
    "ask_ollama_split_hints",
    "llm_hint_runtime_stats",
]
