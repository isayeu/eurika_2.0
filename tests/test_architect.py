"""Tests for eurika.reasoning.architect (ROADMAP §7 — мини-AI)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.reasoning.architect import _format_recent_events, interpret_architecture, _template_interpret
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
