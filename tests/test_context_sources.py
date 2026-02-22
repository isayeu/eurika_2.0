"""Tests for planner semantic context sources (ROADMAP 3.6.3)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.reasoning.context_sources import build_context_sources


def test_build_context_sources_collects_campaign_and_tests(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "session_memory.json").write_text(
        json.dumps(
            {
                "campaign": {
                    "rejected_keys": ["a.py|split_module|"],
                    "verify_fail_keys": ["b.py|remove_unused_import|", "b.py|remove_unused_import|"],
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "self_map.json").write_text(
        json.dumps(
            {
                "modules": [{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}],
                "dependencies": {"a.py": ["c.py"], "b.py": []},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

    ops = [{"target_file": "a.py", "kind": "split_module"}, {"target_file": "b.py", "kind": "clean"}]
    ctx = build_context_sources(tmp_path, ops)
    assert "a.py" in (ctx.get("campaign_rejected_targets") or [])
    assert "b.py" in (ctx.get("recent_verify_fail_targets") or [])
    by_target = ctx.get("by_target") or {}
    assert "tests/test_a.py" in (by_target.get("a.py") or {}).get("related_tests", [])
    assert "c.py" in (by_target.get("a.py") or {}).get("neighbor_modules", [])

