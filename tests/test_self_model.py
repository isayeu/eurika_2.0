"""Self + Capability + Goal Model v0."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.self_model import (
    build_self_model,
    format_self_model_brief,
    format_self_model_text,
    load_self_model,
    persist_self_model,
    snapshot_path,
)


def test_build_self_model_from_facts(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "idle_self_dev.json").write_text(
        json.dumps({"drill_ok": {"imports": 5, "extractable_block": 2}, "last_drill": "imports", "last_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / ".eurika" / "chat_history").mkdir()
    (tmp_path / ".eurika" / "chat_history" / "dialog_state.json").write_text(
        json.dumps(
            {
                "active_goal": {"intent": "scan", "target": ".", "source": "test"},
                "last_execution": {"ok": True, "summary": "scan done"},
            }
        ),
        encoding="utf-8",
    )

    snap = build_self_model(tmp_path)
    assert snap["version"] == 1
    assert "self" in snap and "capabilities" in snap and "goal" in snap
    assert snap["goal"]["status"] == "active"
    assert snap["goal"]["active"]["intent"] == "scan"
    idle = snap["capabilities"]["scores"]["c14_idle_drills"]
    assert idle["insufficient_data"] is False
    assert idle["level"] > 0
    text = format_self_model_text(snap, mode="full")
    assert "Self Model" in text
    assert "c14_idle_drills" in text
    assert "intent=scan" in text


def test_persist_and_load_self_model(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    snap = persist_self_model(tmp_path)
    path = snapshot_path(tmp_path)
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["version"] == snap["version"]
    again = load_self_model(tmp_path, refresh=False, persist=False)
    assert again["version"] == 1


def test_format_agent_context_panel_includes_self_model(tmp_path: Path) -> None:
    from eurika.api.chat_context import format_agent_context_panel

    (tmp_path / ".eurika").mkdir()
    panel = format_agent_context_panel({}, project_root=tmp_path)
    assert "Self / Capability / Goal" in panel
    brief = format_self_model_brief(tmp_path)
    assert any("goal.status" in ln for ln in brief)


def test_self_model_chat_intent(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod
    from eurika.api.chat_direct import resolve_direct_handler

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    (tmp_path / ".eurika").mkdir()
    assert resolve_direct_handler(tmp_path, "модель себя")[0] == "self_model"
    assert resolve_direct_handler(tmp_path, "какое состояние?")[0] == "self_model"
    out = chat_mod.chat_send(tmp_path, "модель себя")
    assert out.get("error") is None
    assert "Self Model" in (out.get("text") or "")
    assert snapshot_path(tmp_path).is_file()


def test_cli_self_model(tmp_path: Path) -> None:
    from argparse import Namespace

    from cli.core_handlers_self_model import handle_self_model

    (tmp_path / ".eurika").mkdir()
    code = handle_self_model(Namespace(path=tmp_path, json=True, quiet=False))
    assert code == 0
    assert snapshot_path(tmp_path).is_file()
