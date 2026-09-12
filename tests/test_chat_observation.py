"""CR-H1: one observation bundle for Chat and session/chat."""

from __future__ import annotations

from pathlib import Path

from eurika.api.chat_observation import (
    attach_workspace_observation,
    build_workspace_observation,
    last_check_is_stale,
    last_user_cmd,
    maybe_refresh_last_check_from_terminal,
    observation_prompt_block,
)
from eurika.api.last_check import LAST_CHECK_LOG, persist_last_check


def _mypy_ok(root: Path) -> None:
    persist_last_check(
        root,
        {
            "ok": True,
            "runner": "mypy",
            "command": ["python", "-m", "mypy", "eurika", "cli"],
            "exit_code": 0,
            "output": "Success: no issues found in 10 source files\n",
        },
    )


def _release_pane() -> str:
    return (
        "$ ./scripts/release_check.sh\n"
        "==> Release check\n"
        "FAILED tests/test_entry_cost.py::test_calibration_keeps_flow\n"
        "[done] exit_code=1\n"
    )


def test_last_user_cmd_takes_last_prompt_line() -> None:
    assert last_user_cmd("$ ls\n$ ./scripts/release_check.sh\nFAILED\n") == (
        "./scripts/release_check.sh"
    )


def test_mypy_disk_vs_release_pane_is_stale(tmp_path: Path) -> None:
    _mypy_ok(tmp_path)
    pane = _release_pane()
    obs = build_workspace_observation(tmp_path, terminal_text=pane, git=False)
    assert obs["lastCheckStale"] is True
    assert "mypy" in obs["lastCheckStaleReason"]
    check = obs["lastCheck"]
    assert check is not None
    assert check["source"] == "terminal"
    assert check["ok"] is False
    assert check["runner"] == "release_check"
    assert "test_entry_cost" in (check.get("outputPreview") or "")
    block = observation_prompt_block(obs)
    assert "prefer [Terminal output]" in block
    assert "stale=yes" in block
    assert "lastUserCmd: ./scripts/release_check.sh" in block


def test_failed_mypy_without_pane_is_not_stale(tmp_path: Path) -> None:
    persist_last_check(
        tmp_path,
        {
            "ok": False,
            "runner": "mypy",
            "command": ["mypy"],
            "exit_code": 1,
            "output": "foo.py:1: error: x\nFound 1 error in 1 file\n",
        },
    )
    obs = build_workspace_observation(tmp_path, terminal_text="$ ", git=False)
    assert obs["lastCheckStale"] is False
    assert obs["lastCheck"]["runner"] == "mypy"
    assert obs["lastCheck"]["ok"] is False
    stale, _reason = last_check_is_stale("$ ", {"ok": False, "runner": "mypy"}, "foo.py")
    assert stale is False


def test_refresh_seals_pane_over_stale_mypy(tmp_path: Path) -> None:
    _mypy_ok(tmp_path)
    obs = build_workspace_observation(tmp_path, terminal_text=_release_pane(), git=False)
    maybe_refresh_last_check_from_terminal(tmp_path, obs)
    log = (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")
    assert "test_entry_cost" in log
    again = build_workspace_observation(tmp_path, terminal_text=_release_pane(), git=False)
    assert again["lastCheckStale"] is False
    assert again["lastCheck"]["runner"] == "release_check"
    assert again["lastCheck"]["ok"] is False


def test_attach_workspace_observation_sets_editor_context(tmp_path: Path) -> None:
    _mypy_ok(tmp_path)
    ctx = attach_workspace_observation(
        tmp_path,
        {"reviewInApprovals": True, "terminalText": _release_pane()},
    )
    assert ctx["lastCheckStale"] is True
    assert ctx["lastCheck"]["source"] == "terminal"
    assert ctx["lastUserCmd"] == "./scripts/release_check.sh"
    assert "FAILED tests/" in ctx["terminalText"]
    assert ctx["observation"]["source"] == "terminal"


def test_git_hint_when_repo_present(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    obs = build_workspace_observation(tmp_path, terminal_text="", git=True)
    assert obs["gitHint"]
    assert "##" in obs["gitHint"] or "??" in obs["gitHint"]


def test_build_chat_prompt_keeps_observation_out_of_terminal_block() -> None:
    from eurika.api.chat_prompt import build_chat_prompt

    prompt = build_chat_prompt(
        "есть ошибки?",
        context="",
        terminal_snippet="FAILED tests/x.py::t\n",
        observation_snippet="[Workspace observation]\nlastCheck stale source=terminal",
    )
    assert "[Workspace observation]" in prompt
    assert "[Terminal output (Qt)]" in prompt
    assert prompt.index("[Workspace observation]") < prompt.index("[Terminal output")


def test_agent_prompt_prefers_terminal_when_last_check_stale(
    tmp_path: Path, monkeypatch
) -> None:
    from eurika.agent.local_runtime import LocalAgentRuntime
    from tests.test_local_agent_backend import _runtime_call

    _mypy_ok(tmp_path)
    runtime = LocalAgentRuntime(tmp_path)
    seen: list[str] = []

    def _call(prompt: str):
        seen.append(prompt)
        return ('{"type":"final","text":"pane first"}', None)

    monkeypatch.setattr(runtime, "_call_model", _call)
    monkeypatch.setattr(runtime, "_accept_grounded_final", lambda text, _obs: text)
    _runtime_call(
        runtime,
        "session/chat",
        {
            "message": "в терминале прогнал релиз чек, проверь есть ли ошибки",
            "context": {
                "reviewInApprovals": True,
                "terminalText": _release_pane(),
            },
        },
        [],
    )
    assert seen
    blob = seen[0]
    assert "lastCheckStale" in blob
    assert "test_entry_cost" in blob
    assert "source=terminal" in blob or "'source': 'terminal'" in blob or '"source": "terminal"' in blob
