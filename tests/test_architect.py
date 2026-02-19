"""Tests for eurika.reasoning.architect (ROADMAP §7 — мини-AI)."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.reasoning.architect import (
    _call_ollama_cli,
    _format_recent_events,
    _llm_interpret,
    _template_interpret,
    interpret_architecture,
)
from eurika.storage.events import Event


def test_template_interpret_minimal():
    """Template produces text from minimal summary and history."""
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
    text = _template_interpret(summary, history)
    assert "10 modules" in text
    assert "12 dependencies" in text
    assert "no cycles" in text
    assert "medium" in text
    assert "god_module" in text or "Main risks" in text
    assert "complexity" in text or "smells" in text


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
    text = _template_interpret(summary, history, patch_plan=patch_plan)
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
    text = interpret_architecture(summary, history, use_llm=False, recent_events=recent)
    assert "Recent actions" in text
    assert "patch" in text and "modified" in text
    assert "learn" in text


def test_format_recent_events():
    """_format_recent_events produces compact string for patch and learn."""
    events = [
        Event(type="patch", input={}, output={"modified": ["a.py", "b.py"]}, result=True),
        Event(type="learn", input={"modules": ["a.py"]}, output={}, result=False),
    ]
    s = _format_recent_events(events)
    assert "patch" in s
    assert "2 file" in s or "modified" in s
    assert "learn" in s
    assert "a.py" in s


def test_llm_interpret_falls_back_to_ollama_on_primary_error() -> None:
    """If primary provider fails, _llm_interpret should return Ollama fallback response."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._init_primary_openai_client",
            return_value=(object(), "primary-model", None),
        ),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "ollama-model", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            side_effect=[(None, "primary down"), ("fallback ok", None)],
        ) as call_llm,
    ):
        text, reason = _llm_interpret(summary, history)
    assert text == "fallback ok"
    assert reason is None
    assert call_llm.call_count == 2


def test_llm_interpret_reports_both_primary_and_fallback_errors() -> None:
    """When both providers fail, reason should contain both error sources."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._init_primary_openai_client",
            return_value=(object(), "primary-model", None),
        ),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "ollama-model", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            side_effect=[(None, "primary down"), (None, "ollama down")],
        ),
        patch(
            "eurika.reasoning.architect._call_ollama_cli",
            return_value=(None, "cli down"),
        ),
    ):
        text, reason = _llm_interpret(summary, history)
    assert text is None
    assert reason is not None
    assert "primary LLM failed" in reason
    assert "ollama HTTP fallback failed" in reason
    assert "ollama CLI fallback failed" in reason


def test_llm_interpret_falls_back_to_ollama_cli_on_http_errors() -> None:
    """If both HTTP providers fail, local ollama CLI result should be used."""
    summary = {"system": {"modules": 1, "dependencies": 0, "cycles": 0}, "maturity": "low"}
    history = {"trends": {}, "regressions": []}
    with (
        patch(
            "eurika.reasoning.architect._init_primary_openai_client",
            return_value=(object(), "primary-model", None),
        ),
        patch(
            "eurika.reasoning.architect._init_ollama_fallback_client",
            return_value=(object(), "ollama-model", None),
        ),
        patch(
            "eurika.reasoning.architect._call_llm_architect",
            side_effect=[(None, "primary down"), (None, "ollama http down")],
        ),
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


def test_call_ollama_cli_starts_server_and_retries_once() -> None:
    """On connection error, _call_ollama_cli starts daemon and retries once."""
    first = type("R", (), {"returncode": 1, "stderr": "Error: could not connect to ollama server", "stdout": ""})()
    second = type("R", (), {"returncode": 0, "stderr": "", "stdout": "model details"})()
    third = type("R", (), {"returncode": 0, "stderr": "", "stdout": "ok from cli\n"})()
    with (
        patch("subprocess.run", side_effect=[first, second, third]) as run_mock,
        patch("subprocess.Popen") as popen_mock,
        patch("time.sleep"),
    ):
        text, reason = _call_ollama_cli("qwen2.5:1.5b", "hello")
    assert text == "ok from cli"
    assert reason is None
    assert run_mock.call_count == 3
    popen_mock.assert_called_once()


def test_call_ollama_cli_reports_missing_model_after_server_start() -> None:
    """If daemon starts but model is absent, returns actionable pull instruction."""
    first = type("R", (), {"returncode": 1, "stderr": "Error: could not connect to ollama server", "stdout": ""})()
    second = type("R", (), {"returncode": 1, "stderr": "Error: model 'qwen2.5:1.5b' not found", "stdout": ""})()
    with (
        patch("subprocess.run", side_effect=[first, second]) as run_mock,
        patch("subprocess.Popen") as popen_mock,
        patch("time.sleep"),
    ):
        text, reason = _call_ollama_cli("qwen2.5:1.5b", "hello")
    assert text is None
    assert reason is not None
    assert "ollama pull qwen2.5:1.5b" in reason
    assert run_mock.call_count == 2
    popen_mock.assert_called_once()


def test_call_ollama_cli_timeout_reports_missing_model_hint() -> None:
    """On run timeout, model check should surface actionable pull hint."""
    first = type("R", (), {"returncode": 1, "stderr": "command timed out after 45 seconds", "stdout": ""})()
    second = type("R", (), {"returncode": 1, "stderr": "Error: model 'qwen2.5:1.5b' not found", "stdout": ""})()
    with patch("subprocess.run", side_effect=[first, second]) as run_mock:
        text, reason = _call_ollama_cli("qwen2.5:1.5b", "hello")
    assert text is None
    assert reason is not None
    assert "ollama pull qwen2.5:1.5b" in reason
    assert run_mock.call_count == 2
