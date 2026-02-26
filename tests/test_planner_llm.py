"""Tests for planner_llm (ROADMAP 2.9.2)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from eurika.reasoning.planner_llm import (
    _build_planner_prompt,
    _parse_llm_hints,
    ask_llm_extract_method_hints,
    ask_ollama_split_hints,
    llm_hint_runtime_stats,
)


@pytest.fixture(autouse=True)
def _reset_llm_hint_runtime_state() -> None:
    """Isolate module-level LLM hint state between tests."""
    from eurika.reasoning import planner_llm

    planner_llm._reset_hint_runtime_state()
    yield
    planner_llm._reset_hint_runtime_state()


def test_parse_llm_hints_extracts_bullets() -> None:
    """_parse_llm_hints extracts hint-like lines from bullet/numbered list."""
    text = (
        "- Extract validation logic into utils_validators.py\n"
        "* Create api.py re-exporting public symbols\n"
        "3. Group reporting in module_reporting.py\n"
    )
    hints = _parse_llm_hints(text)
    assert len(hints) == 3
    assert "validation" in hints[0]
    assert "api.py" in hints[1]
    assert "reporting" in hints[2]


def test_parse_llm_hints_filters_boilerplate() -> None:
    """Drops common LLM preamble and very short lines."""
    text = "Sure! Here are my suggestions:\n- Do something useful here.\n"
    hints = _parse_llm_hints(text)
    assert len(hints) == 1
    assert "useful" in hints[0]


def test_parse_llm_hints_empty_input() -> None:
    assert _parse_llm_hints("") == []
    assert _parse_llm_hints(None) == []  # type: ignore


def test_build_planner_prompt_god_module() -> None:
    """Prompt for god_module includes imports_from and imported_by."""
    p = _build_planner_prompt(
        "god_module",
        "patch_engine.py",
        {"imports_from": ["a", "b"], "imported_by": ["c", "d"]},
    )
    assert "patch_engine" in p
    assert "god module" in p
    assert "a" in p and "b" in p
    assert "c" in p and "d" in p


def test_build_planner_prompt_bottleneck() -> None:
    """Prompt for bottleneck includes callers."""
    p = _build_planner_prompt(
        "bottleneck",
        "api.py",
        {"callers": ["cli.py", "server.py"]},
    )
    assert "api" in p
    assert "bottleneck" in p
    assert "cli" in p and "server" in p


def test_ask_ollama_disabled_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When EURIKA_USE_LLM_HINTS=0, ask_ollama_split_hints returns [] without calling Ollama."""
    monkeypatch.setenv("EURIKA_USE_LLM_HINTS", "0")
    result = ask_ollama_split_hints(
        "god_module",
        "x.py",
        {"imports_from": ["a"], "imported_by": []},
    )
    assert result == []


def test_ask_ollama_unknown_smell_returns_empty() -> None:
    """Unknown smell type returns [] without calling Ollama."""
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        result = ask_ollama_split_hints("cyclic_dependency", "x.py", {})
    assert result == []


def test_ask_ollama_success_returns_hints() -> None:
    """When Ollama returns text, parsed hints are returned."""
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = (
                "- Extract core logic into core.py\n- Move helpers to utils.py",
                None,
            )
            result = ask_ollama_split_hints(
                "god_module",
                "patch_engine.py",
                {"imports_from": ["a"], "imported_by": ["b"]},
            )
    assert len(result) >= 1
    assert "core" in result[0] or "logic" in result[0]


def test_ask_ollama_failure_returns_empty() -> None:
    """When Ollama fails, returns [] (fallback to heuristics)."""
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = (None, "connection refused")
            result = ask_ollama_split_hints(
                "god_module",
                "x.py",
                {"imports_from": [], "imported_by": []},
            )
    assert result == []


def test_ask_ollama_respects_max_calls_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second module is skipped when max call budget is exhausted."""
    monkeypatch.setenv("EURIKA_LLM_HINTS_MAX_CALLS", "1")
    monkeypatch.setenv("EURIKA_LLM_HINTS_BUDGET_SEC", "999")
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = ("- Extract one helper module", None)
            r1 = ask_ollama_split_hints("god_module", "a.py", {"imports_from": [], "imported_by": []})
            r2 = ask_ollama_split_hints("god_module", "b.py", {"imports_from": [], "imported_by": []})
    assert len(r1) >= 1
    assert r2 == []
    assert mock_cli.call_count == 1


def test_ask_ollama_caches_result_per_module() -> None:
    """Repeated request for same smell/module should not re-call Ollama."""
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = ("- Extract parser helpers", None)
            r1 = ask_ollama_split_hints("god_module", "same.py", {"imports_from": [], "imported_by": []})
            r2 = ask_ollama_split_hints("god_module", "same.py", {"imports_from": [], "imported_by": []})
    assert r1 == r2
    assert mock_cli.call_count == 1


def test_ask_ollama_timeout_triggers_circuit_breaker() -> None:
    """Timeout/connect failure disables further hint calls for the run."""
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = (None, "timed out (cli timeout=45s)")
            r1 = ask_ollama_split_hints("god_module", "first.py", {"imports_from": [], "imported_by": []})
            r2 = ask_ollama_split_hints("god_module", "second.py", {"imports_from": [], "imported_by": []})
    assert r1 == []
    assert r2 == []
    assert mock_cli.call_count == 1


def test_ask_llm_extract_method_hints_disabled_by_default() -> None:
    """When EURIKA_USE_LLM_EXTRACT_HINTS=0 (default), returns [] without calling."""
    from eurika.reasoning.planner_llm import ask_llm_extract_method_hints

    result = ask_llm_extract_method_hints(__file__, "test_ask_llm_extract_method_hints_disabled")
    assert result == []


def test_ask_llm_extract_method_hints_success(tmp_path: Path) -> None:
    """When enabled and Ollama returns text, parsed hints are returned."""
    py_file = tmp_path / "code.py"
    py_file.write_text(
        "def long_function(x):\n    a = 1\n    b = 2\n    for i in range(10):\n        yield i * a + b\n",
        encoding="utf-8",
    )
    with patch("eurika.reasoning.planner_llm._use_llm_extract_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = (
                "- Extract the loop body to _process_chunk(data)\n- Move validation to helper",
                None,
            )
            result = ask_llm_extract_method_hints(py_file, "long_function")
    assert len(result) >= 1
    assert "loop" in result[0].lower() or "validation" in result[0].lower() or "chunk" in result[0].lower()


def test_llm_hint_runtime_stats_exposes_budget_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime stats should expose usage counters and breaker flags."""
    monkeypatch.setenv("EURIKA_LLM_HINTS_MAX_CALLS", "2")
    monkeypatch.setenv("EURIKA_LLM_HINTS_BUDGET_SEC", "999")
    with patch("eurika.reasoning.planner_llm._use_llm_hints", return_value=True):
        with patch("eurika.reasoning.architect._call_ollama_cli") as mock_cli:
            mock_cli.return_value = ("- Extract parser helpers", None)
            _ = ask_ollama_split_hints("god_module", "stats.py", {"imports_from": [], "imported_by": []})
    stats = llm_hint_runtime_stats()
    assert stats["calls_used"] == 1
    assert stats["max_calls"] == 2
    assert stats["budget_exhausted"] is False
    assert stats["circuit_breaker_triggered"] is False
