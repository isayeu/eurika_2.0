"""Tests for eurika.reasoning.architect (ROADMAP §7 — мини-AI)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from report.architect_format import format_architect_template

from eurika.reasoning.architect_helpers import (
    build_recommendation_how_block,
    format_recent_events,
    parse_smell_from_risk,
)
from eurika.reasoning.architect import (
    _call_ollama_cli,
    _init_ollama_fallback_client,
    _llm_interpret,
    _template_interpret,
    interpret_architecture,
    interpret_architecture_with_meta,
)
from eurika.storage.events import Event


def test_recommendation_how_block_and_parse_smell():
    """ROADMAP 2.9.1: Recommendation block for god_module, bottleneck, hub; parse_smell_from_risk."""
    assert parse_smell_from_risk("god_module @ main.py") == "god_module"
    assert parse_smell_from_risk("bottleneck @ api.py (severity=7)") == "bottleneck"
    assert parse_smell_from_risk("hub @ core.py") == "hub"
    assert parse_smell_from_risk("unknown @ x.py") is None

    block = build_recommendation_how_block(
        ["god_module @ main.py", "bottleneck @ api.py"],
        knowledge_snippet="",
    )
    assert "Recommendation (how to fix)" in block
    assert "god_module" in block and "Split into focused modules" in block
    assert "bottleneck" in block and "facade" in block
    assert "Reference block" not in block

    block_with_ref = build_recommendation_how_block(
        ["god_module @ main.py"],
        knowledge_snippet="architecture_refactor: Split god module...",
    )
    assert "Reference block" in block_with_ref


def test_template_interpret_minimal():
    """Template produces text from minimal summary and history (ROADMAP 2.9.1: + Recommendation)."""
    summary = {
        "system": {"modules": 10, "dependencies": 12, "cycles": 0},
        "maturity": "medium",
        "risks": ["god_module @ main.py (severity=5.00)"],
        "central_modules": [{"name": "main.py", "fan_in": 3, "fan_out": 2}],
    }
    history = {
        "trends": {"complexity": "stable", "smells": "increasing"},
        "regressions": ["Total smells increased: 1 → 2"],
    }
    text = _template_interpret(summary, history, formatter=format_architect_template)
    assert "10 modules" in text
    assert "12 dependencies" in text
    assert "no cycles" in text
    assert "medium" in text
    assert "god_module" in text or "Main risks" in text
    assert "complexity" in text or "smells" in text
    assert "Recommendation (how to fix)" in text
    assert "Split into focused modules" in text


def test_interpret_architecture_no_llm():
    """interpret_architecture with use_llm=False returns template text."""
    summary = {"system": {"modules": 5, "dependencies": 4, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    text = interpret_architecture(summary, history, use_llm=False)
    assert "5 modules" in text
    assert "4 dependencies" in text
    assert "low" in text


def test_template_interpret_with_patch_plan():
    """Template includes patch-plan summary when provided (ROADMAP §7)."""
    summary = {"system": {"modules": 3, "dependencies": 2, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    patch_plan = {
        "operations": [
            {"target_file": "a.py", "kind": "split_module", "description": "Split a"},
            {"target_file": "b.py", "kind": "extract_class", "description": "Extract b"},
        ],
    }
    text = _template_interpret(summary, history, patch_plan=patch_plan, formatter=format_architect_template)
    assert "Planned refactorings" in text
    assert "2 ops" in text
    assert "a.py" in text or "b.py" in text


def test_interpret_architecture_with_knowledge(tmp_path):
    """When knowledge_provider + topic return fragments, template output includes Reference (Knowledge Layer)."""
    import json
    from eurika.knowledge import LocalKnowledgeProvider
    cache = tmp_path / "eurika_knowledge.json"
    cache.write_text(
        json.dumps({
            "topics": {
                "python": [{"title": "PEP 701", "content": "f-strings can contain quotes."}],
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    provider = LocalKnowledgeProvider(cache)
    summary = {"system": {"modules": 2, "dependencies": 1, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    text = interpret_architecture(
        summary, history, use_llm=False,
        knowledge_provider=provider, knowledge_topic="python",
        template_formatter=format_architect_template,
    )
    assert "Reference" in text
    assert "PEP 701" in text or "f-strings" in text


def test_architect_includes_recent_events():
    """interpret_architecture with recent_events includes Recent actions block (ROADMAP 3.2.3)."""
    summary = {"system": {"modules": 4, "dependencies": 3, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    recent = [
        Event(type="patch", input={}, output={"modified": ["foo.py"]}, result=True, timestamp=1.0),
        Event(type="learn", input={"modules": ["foo.py"]}, output={}, result=True, timestamp=2.0),
    ]
    text = interpret_architecture(
        summary, history, use_llm=False, recent_events=recent,
        template_formatter=format_architect_template,
    )
    assert "Recent actions" in text
    assert "patch" in text and "modified" in text
    assert "learn" in text


def test_format_recent_events():
    """_format_recent_events produces compact string for patch and learn."""
    events = [
        Event(type="patch", input={}, output={"modified": ["a.py", "b.py"]}, result=True),
        Event(type="learn", input={"modules": ["a.py"]}, output={}, result=False),
    ]
    s = format_recent_events(events)
    assert "patch" in s
    assert "2 file" in s or "modified" in s
    assert "learn" in s
    assert "a.py" in s


def test_format_recent_events_includes_failure_reason():
    """When verify=False and failure_reason present, it appears in output (Review III самокоррекция)."""
    events = [
        Event(
            type="patch",
            input={},
            output={"modified": ["x.py"], "failure_reason": "metrics_worsened"},
            result=False,
        ),
    ]
    s = format_recent_events(events)
    assert "failure=metrics_worsened" in s


def test_llm_interpret_falls_back_to_ollama_on_primary_error() -> None:
    """When ollama CLI fails, _llm_interpret falls back to ollama HTTP (new flow: CLI first)."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=(None, "cli down"),
        ),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "ollama-model", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            return_value=("fallback ok", None),
        ) as call_llm,
    ):
        text, reason = _llm_interpret(summary, history)
    assert text == "fallback ok"
    assert reason is None
    assert call_llm.call_count == 1


def test_llm_interpret_reports_both_primary_and_fallback_errors() -> None:
    """When both ollama CLI and ollama HTTP fail, reason contains both (new flow: CLI first)."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=(None, "cli down"),
        ),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "ollama-model", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            return_value=(None, "ollama down"),
        ),
    ):
        text, reason = _llm_interpret(summary, history)
    assert text is None
    assert reason is not None
    assert "ollama CLI failed" in reason
    assert "cli down" in reason
    assert "ollama HTTP failed" in reason


def test_llm_interpret_falls_back_to_ollama_cli_on_http_errors() -> None:
    """Ollama CLI first: when CLI succeeds, returns immediately (no HTTP fallback needed)."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=("cli fallback ok", None),
        ) as call_cli,
    ):
        text, reason = _llm_interpret(
            summary,
            history,
            knowledge_snippet="Reference knowledge blob",
            recent_events_snippet="event1; event2",
        )
    assert text == "cli fallback ok"
    assert reason is None
    call_cli.assert_called_once()
    cli_prompt = call_cli.call_args[0][1]
    assert "Reference knowledge" not in cli_prompt
    assert "Recent refactoring events" not in cli_prompt


def test_call_ollama_cli_connection_error_requires_manual_start() -> None:
    """On connection error, _call_ollama_cli should not auto-start daemon."""
    first = type("R", (), {"returncode": 1, "stderr": "Error: could not connect to ollama server", "stdout": ""})()
    with patch("subprocess.run", side_effect=[first]) as run_mock:
        text, reason = _call_ollama_cli("qwen2.5-coder:7b", "hello")
    assert text is None
    assert reason is not None
    assert "ollama serve" in reason
    assert run_mock.call_count == 1


def test_init_ollama_fallback_client_uses_coding_model_default() -> None:
    """Fallback client default model should target code-oriented Ollama model."""
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("eurika.reasoning.architect._build_openai_client", return_value=(object(), None)),
    ):
        _, model, reason = _init_ollama_fallback_client()
    assert reason is None
    assert model == "qwen2.5-coder:7b"


def test_call_ollama_cli_timeout_reports_missing_model_hint() -> None:
    """On run timeout, model check should surface actionable pull hint."""
    preflight_ok = type("R", (), {"returncode": 0, "stderr": "", "stdout": "ok"})()
    first = type("R", (), {"returncode": 1, "stderr": "command timed out after 45 seconds", "stdout": ""})()
    second = type("R", (), {"returncode": 1, "stderr": "Error: model 'qwen2.5-coder:7b' not found", "stdout": ""})()
    with patch("subprocess.run", side_effect=[preflight_ok, first, second]) as run_mock:
        text, reason = _call_ollama_cli("qwen2.5-coder:7b", "hello")
    assert text is None
    assert reason is not None
    assert "ollama pull qwen2.5-coder:7b" in reason
    assert run_mock.call_count >= 2  # preflight + run + (show in _model_ready_reason)


def test_interpret_architecture_with_meta_llm_disabled_sets_degraded() -> None:
    summary = {"system": {"modules": 2, "dependencies": 1, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    text, meta = interpret_architecture_with_meta(summary, history, use_llm=False)
    assert isinstance(text, str) and text
    assert meta.get("degraded_mode") is True
    assert "llm_disabled" in (meta.get("degraded_reasons") or [])
    assert meta.get("llm_used") is False
    assert meta.get("use_llm") is False


def test_interpret_architecture_with_meta_llm_error_sets_reason() -> None:
    summary = {"system": {"modules": 2, "dependencies": 1, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with patch(
        "eurika.reasoning.architect._llm_interpret",
        return_value=(None, "primary down; fallback down"),
    ):
        text, meta = interpret_architecture_with_meta(summary, history, use_llm=True, verbose=False)
    assert isinstance(text, str) and text
    assert meta.get("degraded_mode") is True
    reasons = meta.get("degraded_reasons") or []
    assert any("llm_unavailable:primary down; fallback down" in r for r in reasons)
    assert meta.get("llm_used") is False
    assert meta.get("use_llm") is True


def test_interpret_architecture_with_meta_knowledge_throws_uses_empty_snippet() -> None:
    """R2 Fallback: when knowledge resolution throws, architect uses empty snippet and completes."""
    from eurika.knowledge import LocalKnowledgeProvider

    summary = {"system": {"modules": 2, "dependencies": 1, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with patch("eurika.reasoning.architect.resolve_knowledge_snippet", side_effect=OSError("fetch failed")):
        text, meta = interpret_architecture_with_meta(
            summary,
            history,
            use_llm=False,
            knowledge_provider=LocalKnowledgeProvider(),
            knowledge_topic="python",
        )
    assert isinstance(text, str) and len(text) > 0
    assert "degraded_mode" in meta


def test_interpret_architecture_with_meta_llm_success_not_degraded() -> None:
    summary = {"system": {"modules": 2, "dependencies": 1, "cycles": 0}, "maturity": "low", "risks": []}
    history = {"trends": {}, "regressions": []}
    with patch("eurika.reasoning.architect._llm_interpret", return_value=("ok from llm", None)):
        text, meta = interpret_architecture_with_meta(summary, history, use_llm=True, verbose=False)
    assert text.startswith("ok from llm")
    assert meta.get("degraded_mode") is False
    assert meta.get("degraded_reasons") == []
    assert meta.get("llm_used") is True
    assert meta.get("use_llm") is True


def test_groq_base_url_skips_litellm_first(monkeypatch) -> None:
    """Custom Groq OPENAI_BASE_URL must not route litellm as ollama/model."""
    from eurika.reasoning.architect import (
        _has_remote_openai_compatible,
        _should_use_litellm_first,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    assert _has_remote_openai_compatible() is True
    assert _should_use_litellm_first() is False

    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    assert _should_use_litellm_first() is True

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert _should_use_litellm_first() is True

    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    assert _has_remote_openai_compatible() is False
    assert _should_use_litellm_first() is False


def test_call_llm_with_prompt_falls_back_to_ollama_on_groq_rate_limit(monkeypatch) -> None:
    """Groq TPD 429 must not stop at litellm — chat falls through to local Ollama."""
    from eurika.reasoning.architect import call_llm_with_prompt

    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.delenv("EURIKA_CHAT_PROVIDER", raising=False)

    rate_err = (
        "Error code: 429 - Rate limit reached for model "
        "`llama-3.3-70b-versatile` on tokens per day (TPD). "
        "Please try again in 27m41.472s."
    )
    with (
        patch(
            "eurika.reasoning.architect._init_primary_openai_client",
            return_value=(object(), "llama-3.3-70b-versatile", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            side_effect=[(None, rate_err), ("local ok", None)],
        ) as call_llm,
        patch(
            "eurika.reasoning.architect._call_litellm",
            return_value=(None, "should not be called"),
        ) as call_lite,
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "qwen2.5-coder:7b", None),
        ),
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=(None, "cli unused"),
        ),
    ):
        text, err = call_llm_with_prompt("что мы делаем сегодня?", max_tokens=64)

    assert err is None
    assert text is not None
    assert text.startswith("local ok")
    assert "Лимит Groq достигнут" in text
    assert "27" in text or "мин" in text
    assert call_lite.call_count == 0
    assert call_llm.call_count == 2


def test_is_rate_limit_error_detects_groq_tpd() -> None:
    from eurika.reasoning.architect import _is_rate_limit_error

    assert _is_rate_limit_error("Error code: 429 - tokens per day (TPD)")
    assert _is_rate_limit_error("RateLimitError: rate_limit_exceeded")
    assert not _is_rate_limit_error("connection refused")


def test_format_rate_limit_user_message_includes_when_again() -> None:
    from eurika.reasoning.architect import (
        format_rate_limit_user_message,
        humanize_llm_error,
        parse_rate_limit_retry_seconds,
    )

    raw = "Please try again in 27m41.472s. Rate limit reached (TPD)."
    assert parse_rate_limit_retry_seconds(raw) == pytest.approx(27 * 60 + 41.472, rel=1e-3)
    msg = format_rate_limit_user_message(raw, used_local_fallback=True)
    assert "Лимит" in msg
    assert "мин" in msg
    assert "Ollama" in msg
    assert "Лимит" in humanize_llm_error(f"Error code: 429 — {raw}")


def test_rate_limit_without_ollama_returns_friendly_error(monkeypatch) -> None:
    from eurika.reasoning.architect import call_llm_with_prompt

    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.delenv("EURIKA_CHAT_PROVIDER", raising=False)
    rate_err = "Error code: 429 — Please try again in 5m0s. tokens per day"
    with (
        patch(
            "eurika.reasoning.architect._init_primary_openai_client",
            return_value=(object(), "llama-3.3-70b-versatile", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            return_value=(None, rate_err),
        ),
        patch("eurika.reasoning.architect._call_litellm", return_value=(None, "n/a")),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(None, None, "ollama down"),
        ),
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=(None, "cli down"),
        ),
    ):
        text, err = call_llm_with_prompt("ping", max_tokens=16)
    assert text is None
    assert err is not None
    assert "Лимит Groq достигнут" in err
    assert "5 мин" in err or "~5 мин" in err
    assert "Ollama" in err
