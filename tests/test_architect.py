"""Tests for eurika.reasoning.architect (ROADMAP §7 — мини-AI)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.reasoning.architect import interpret_architecture, _template_interpret


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
