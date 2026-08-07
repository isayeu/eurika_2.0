"""docs_audit chat skill: VISION/ROADMAP status via LLM or fallback."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat_direct import resolve_direct_handler
from eurika.api.chat_intents_config import match_direct_intent
from eurika.api.docs_audit import _self_map_blurb, run_docs_audit


def test_self_map_blurb_counts_modules_not_dump(tmp_path: Path) -> None:
    modules = [{"path": f"m{i}.py", "lines": 1} for i in range(40)]
    (tmp_path / "self_map.json").write_text(
        json.dumps({"modules": modules, "dependencies": [], "summary": {"cycles": 0}}),
        encoding="utf-8",
    )
    blurb = _self_map_blurb(tmp_path)
    assert "modules=40" in blurb
    assert "m0.py" not in blurb
    assert len(blurb) < 200


def test_docs_audit_intent_beats_list_docs(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "VISION.md").write_text(
        "# V\n\n1. ~~Done~~ ✅\n6. HTF — Не трогать\n",
        encoding="utf-8",
    )
    msg = "прочти всю документацию по проекту, проверь что уже реализовано, а что нет"
    assert match_direct_intent(tmp_path, msg) == ("docs_audit", None)
    assert resolve_direct_handler(tmp_path, msg) == ("docs_audit", None)
    assert resolve_direct_handler(tmp_path, "покажи документацию") == ("list_docs", None)


def test_docs_audit_fallback_without_llm(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "VISION.md").write_text(
        "## Backlog\n\n"
        "1. ~~Chat-first~~ ✅ done\n"
        "6. **HTF bias** — Не трогать\n"
        "11. Plugin hooks\n",
        encoding="utf-8",
    )

    def _boom(*_a, **_k):
        return None, "no llm"

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        _boom,
    )
    text, meta = run_docs_audit(tmp_path, use_llm=True)
    assert meta.get("source") == "fallback"
    assert "VISION" in text or "Аудит" in text
    assert "Chat-first" in text or "✅" in text
    assert "MetricVector" not in text
    assert "chat UX" in text.lower() or "goals" in text.lower() or "plugin" in text.lower()


def test_docs_audit_prompt_deprioritizes_legacy_infra(tmp_path: Path) -> None:
    from eurika.api.docs_audit import build_docs_audit_prompt

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "VISION.md").write_text("# V\n1. Chat ✅\n", encoding="utf-8")
    prompt = build_docs_audit_prompt(tmp_path)
    assert "VISION.md" in prompt
    assert "ROADMAP.md" not in prompt
    assert "MetricVector" in prompt  # as forbidden example
    assert "уже в коде" in prompt
