"""Cursor SDK model selection helpers (no live API)."""

from __future__ import annotations

from eurika.agent.cursor_judge import (
    DEFAULT_CURSOR_MODEL,
    _unavailable_model_id,
    build_agent_model,
    is_router_model,
    selected_cursor_model,
    selected_optimize_for,
    stub_model_catalog,
)


def test_unavailable_model_id_strips_trailing_dot() -> None:
    err = "invalid_argument: Cannot use this model: auto-smart. Available models: default, composer-2.5"
    assert _unavailable_model_id(err) == "auto-smart"


def test_stub_catalog_includes_composer_and_auto() -> None:
    ids = {item["id"] for item in stub_model_catalog()}
    assert "composer-2.5" in ids
    assert "default" in ids
    assert "auto-smart" not in ids


def test_build_agent_model_plain_id() -> None:
    assert build_agent_model("composer-2.5", "") == "composer-2.5"
    assert is_router_model("composer-2.5") is False


def test_build_agent_model_default_ignores_router_mode() -> None:
    assert build_agent_model("default", "cost") == "default"
    assert is_router_model("default") is False


def test_build_agent_model_router_selection() -> None:
    model = build_agent_model("auto-smart", "balanced")
    assert getattr(model, "id", None) == "auto-smart"
    params = list(getattr(model, "params", ()) or ())
    assert params
    assert getattr(params[0], "id", None) == "optimize_for"
    assert getattr(params[0], "value", None) == "balanced"


def test_selected_cursor_model_from_env(monkeypatch) -> None:
    monkeypatch.setenv("CURSOR_MODEL", "composer-2")
    monkeypatch.setenv("CURSOR_OPTIMIZE_FOR", "intelligence")
    assert selected_cursor_model() == "composer-2"
    assert selected_optimize_for() == "intelligence"
    monkeypatch.delenv("CURSOR_MODEL", raising=False)
    assert selected_cursor_model() == DEFAULT_CURSOR_MODEL


def test_call_llm_with_prompt_routes_cursor(monkeypatch) -> None:
    from eurika.reasoning import architect

    monkeypatch.setenv("EURIKA_CHAT_PROVIDER", "cursor")

    def _fake_complete(prompt, **kwargs):
        return (f"cursor:{prompt[:8]}", None)

    monkeypatch.setattr("eurika.agent.cursor_judge.complete_chat", _fake_complete)
    text, err = architect.call_llm_with_prompt("hello from test", max_tokens=16)
    assert err is None
    assert text and text.startswith("cursor:")


def test_prompt_local_retries_unavailable_auto_smart(monkeypatch) -> None:
    from cursor_sdk import CursorAgentError

    from eurika.agent import cursor_judge as cj

    calls: list[object] = []

    class _Ok:
        status = "finished"
        result = "ok after fallback"
        id = "run-1"
        agent_id = "ag-1"

    def _prompt(message, options):
        calls.append(getattr(options, "model", None))
        if len(calls) == 1:
            raise CursorAgentError("invalid_argument: Cannot use this model: auto-smart. Available models: default")
        return _Ok()

    monkeypatch.setattr(cj, "load_cursor_key", lambda _ws: "crsr_test")
    monkeypatch.setattr("cursor_sdk.Agent.prompt", _prompt)
    out = cj.prompt_local("hi", model="auto-smart", optimize_for="cost", tools=())
    assert out["ok"] is True
    assert out["text"] == "ok after fallback"
    assert len(calls) == 2
    assert calls[1] == "default"
