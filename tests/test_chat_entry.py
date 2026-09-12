"""CR-H2: one entry — HITL/already-ran stay on core; else one agent runtime."""

from __future__ import annotations

from pathlib import Path

from eurika.api.chat_entry import dispatch_chat_turn, is_pre_llm_turn


def test_pre_llm_is_hitl_already_ran_and_run_now() -> None:
    assert is_pre_llm_turn("применяй") is True
    assert is_pre_llm_turn("отклонить") is True
    assert is_pre_llm_turn("в терминале прогнал релиз чек, проверь есть ли ошибки") is True
    assert is_pre_llm_turn("прогони release check") is True
    assert is_pre_llm_turn("запусти scan") is True
    assert is_pre_llm_turn("собери полный коммит и запуш") is True
    assert is_pre_llm_turn("привет") is False
    assert is_pre_llm_turn("IMPLEMENT: split handlers") is False
    assert is_pre_llm_turn("модель себя") is False


def test_dispatch_greeting_uses_agent(tmp_path: Path) -> None:
    agent_calls: list[str] = []
    core_calls: list[str] = []

    def _agent(message: str, client_terminal_text=None):
        agent_calls.append(message)
        return {"ok": True, "text": "hi-agent"}

    def _core(**kwargs):
        core_calls.append(str(kwargs.get("message")))
        return {"text": "hi-core", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "привет",
        agent_chat=_agent,
        core_chat=_core,
    )
    assert agent_calls == ["привет"]
    assert core_calls == []
    assert out["text"] == "hi-agent"


def test_dispatch_run_now_release_check_uses_core(tmp_path: Path) -> None:
    agent_calls: list[str] = []

    def _agent(message: str, client_terminal_text=None):
        agent_calls.append(message)
        return {"ok": True, "text": "lecture"}

    def _core(**kwargs):
        return {"text": "ran-release-check", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "прогони release check",
        agent_chat=_agent,
        core_chat=_core,
    )
    assert agent_calls == []
    assert out["text"] == "ran-release-check"


def test_dispatch_already_ran_uses_core(tmp_path: Path) -> None:
    agent_calls: list[str] = []

    def _agent(message: str, client_terminal_text=None):
        agent_calls.append(message)
        return {"ok": True, "text": "nope"}

    def _core(**kwargs):
        return {"text": "from-pane", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "в терминале прогнал релиз чек, проверь есть ли ошибки",
        client_terminal_text="FAILED tests/x.py::t\n",
        agent_chat=_agent,
        core_chat=_core,
    )
    assert agent_calls == []
    assert out["text"] == "from-pane"


def test_dispatch_missing_agent_fails_loud(tmp_path: Path) -> None:
    def _boom(message: str, client_terminal_text=None):
        raise FileNotFoundError(".eurika/agent_http.json")

    def _core(**kwargs):
        return {"text": "should not run", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "привет",
        agent_chat=_boom,
        core_chat=_core,
    )
    assert out.get("ok") is False
    assert "agent HTTP" in str(out.get("error") or "")


def test_dispatch_short_backlog_uses_core_even_with_agent(tmp_path: Path) -> None:
    agent_calls: list[str] = []
    core_calls: list[str] = []

    def _agent(message: str, client_terminal_text=None):
        agent_calls.append(message)
        return {"ok": True, "text": "agent-should-not-run"}

    def _core(**kwargs):
        core_calls.append(str(kwargs.get("message")))
        return {"text": "from-development-focus", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "что дальше?",
        agent_chat=_agent,
        core_chat=_core,
    )
    assert agent_calls == []
    assert core_calls == ["что дальше?"]
    assert out["text"] == "from-development-focus"


def test_dispatch_git_commit_uses_core_even_with_agent(tmp_path: Path) -> None:
    agent_calls: list[str] = []

    def _agent(message: str, client_terminal_text=None):
        agent_calls.append(message)
        return {"ok": True, "text": "agent-should-not-run"}

    def _core(**kwargs):
        return {"text": "pending-git-preview", "error": None}

    out = dispatch_chat_turn(
        tmp_path,
        "собери полный коммит и запуш",
        agent_chat=_agent,
        core_chat=_core,
    )
    assert agent_calls == []
    assert out["text"] == "pending-git-preview"


def test_http_chat_without_runtime_uses_core(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.chat_entry import handle_http_chat

    seen: list[str] = []

    def _fake_send(_root, message, **_kwargs):
        seen.append(message)
        return {"text": "core-hi", "error": None}

    monkeypatch.setattr("eurika.api.chat.chat_send", _fake_send)
    out = handle_http_chat(tmp_path, "привет", agent_runtime=None)
    assert seen == ["привет"]
    assert out["text"] == "core-hi"


def test_http_chat_with_runtime_uses_agent_for_docs_plan(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.chat_entry import handle_http_chat

    seen: list[str] = []

    class _Runtime:
        def dispatch(self, method, params, cancel=None, emit=None):
            seen.append(method)
            ctx = params.get("context") or {}
            assert ctx.get("reviewInApprovals") is not True
            return {"ok": True, "text": "H4 from DEVELOPMENT", "pendingToolCalls": []}

    monkeypatch.setattr(
        "eurika.api.chat.chat_send",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("core must not run")),
    )
    out = handle_http_chat(
        tmp_path,
        "проверь документы, что далее по плану?",
        agent_runtime=_Runtime(),
    )
    assert seen == ["session/chat"]
    assert out["text"] == "H4 from DEVELOPMENT"


def test_greeting_prompt_does_not_dump_last_check() -> None:
    from eurika.agent.local_runtime_prompt import chat_prompt

    prompt = chat_prompt(
        [{"role": "user", "content": "hello"}],
        {"lastCheck": {"runner": "mypy", "ok": True}},
        [{"tool": "last_check", "runner": "mypy"}],
    )
    assert "short greeting" in prompt
    assert "Do not mention last_check" in prompt
    assert "EDITOR_CONTEXT=" not in prompt
    assert "TOOLS=" not in prompt


def test_skill_release_check_seals_last_check(tmp_path: Path, monkeypatch) -> None:
    from eurika.agent.workspace import WorkspaceTools
    from eurika.api.last_check import LAST_CHECK_LOG

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "release_check.sh").write_text("#!/bin/bash\nexit 0\n")
    monkeypatch.setattr(
        "eurika.api.chat_tools.run_release_check",
        lambda _root, timeout=None: (False, "FAILED tests/skill.py::t\n"),
    )
    tools = WorkspaceTools(tmp_path)
    import threading

    result = tools.skill(
        {"name": "release_check"},
        cancel=threading.Event(),
        emit=lambda *_a, **_k: None,
    )
    assert result["ok"] is False
    assert "skill.py" in result["output"]
    assert "skill.py" in (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")
