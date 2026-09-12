"""Last Chat quality-check is persisted and handed to the coding-agent follow-up."""

from __future__ import annotations

from pathlib import Path

from eurika.api.last_check import (
    LAST_CHECK_LOG,
    attach_last_check_context,
    count_diagnostics,
    last_check_files,
    last_check_observation,
    last_check_prompt_block,
    maybe_seal_terminal_quality_check,
    persist_last_check,
    seal_check_verification,
)
from eurika.api.task_executor import build_task_spec, execute_spec
from eurika.api.chat_context import store_last_execution
from eurika.api.chat_utils import format_execution_report


def test_count_diagnostics_uses_mypy_summary() -> None:
    text = "foo.py:1: error: x\nbar.py:2: error: y\nFound 118 errors in 18 files\n"
    assert count_diagnostics(text) == 118


def test_persist_and_attach_failed_check(tmp_path: Path) -> None:
    long_out = "\n".join(f"mod{i}.py:1: error: boom{i}" for i in range(80))
    long_out += "\nFound 80 errors in 80 files\n"
    extras = persist_last_check(
        tmp_path,
        {
            "ok": False,
            "runner": "mypy",
            "command": ["python", "-m", "mypy", "eurika", "cli"],
            "exit_code": 1,
            "output": long_out,
        },
    )
    assert extras["log_path"] == LAST_CHECK_LOG
    assert extras["error_count"] == 80
    log = (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")
    assert "mod79.py" in log
    assert "Found 80 errors" in log

    ctx = attach_last_check_context(tmp_path, {"reviewInApprovals": True})
    check = ctx["lastCheck"]
    assert check["ok"] is False
    assert check["errorCount"] == 80
    assert check["logPath"] == LAST_CHECK_LOG
    assert "mod0.py" in (check.get("outputPreview") or "")

    obs = last_check_observation(ctx)
    assert obs is not None
    assert obs["tool"] == "last_check"
    assert "surgical" in str(obs["result"]["note"])
    assert "remaining files" in str(obs["result"]["note"])
    assert "mod0.py" in (obs["result"].get("paths") or [])
    assert last_check_files("cli/wiring/entrypoints.py:17: error: x\n") == [
        "cli/wiring/entrypoints.py"
    ]

    block = last_check_prompt_block(tmp_path)
    assert "Last check FAILED" in block
    assert "mypy" in block


def test_last_check_observation_skips_successful_check(tmp_path: Path) -> None:
    persist_last_check(
        tmp_path,
        {"ok": True, "runner": "mypy", "command": ["mypy"], "output": "Success"},
    )
    ctx = attach_last_check_context(tmp_path, {})
    assert last_check_observation(ctx) is None
    assert last_check_prompt_block(tmp_path) == ""


def test_seal_truncates_chat_output_keeps_full_log(tmp_path: Path) -> None:
    raw = ("x.py:1: error: n\n" * 500) + "Found 500 errors in 1 file\n"
    sealed = seal_check_verification(
        tmp_path,
        {"ok": False, "runner": "mypy", "command": ["mypy"], "output": raw},
    )
    assert sealed["output_truncated"] is True
    assert len(sealed["output"]) <= 4000
    assert "Found 500 errors" in (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")


def test_maybe_seal_terminal_quality_check_from_release_script(tmp_path: Path) -> None:
    log = (
        "==> Release check\n"
        "FAILED tests/test_entry_cost.py::test_calibration_keeps_flow\n"
        "[done] exit_code=1\n"
    )
    sealed = maybe_seal_terminal_quality_check(
        tmp_path,
        command="./scripts/release_check.sh",
        output=log,
        exit_code=1,
    )
    assert sealed is not None
    assert sealed["ok"] is False
    assert "test_entry_cost" in (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")
    assert maybe_seal_terminal_quality_check(
        tmp_path, command="ls -la", output="README.md\n", exit_code=0
    ) is None


def test_format_execution_report_points_at_full_log() -> None:
    text = format_execution_report(
        {
            "ok": False,
            "summary": "type check failed",
            "applied_steps": ["run mypy"],
            "verification": {
                "ok": False,
                "output": "a.py:1: error: x",
                "log_path": LAST_CHECK_LOG,
                "error_count": 118,
                "output_truncated": True,
            },
            "error": "mypy returned non-zero",
        }
    )
    assert LAST_CHECK_LOG in text
    assert "118" in text


def test_store_last_execution_keeps_verify_pointer() -> None:
    state: dict = {}
    store_last_execution(
        state,
        {
            "ok": False,
            "summary": "type check failed",
            "verification": {
                "ok": False,
                "runner": "mypy",
                "exit_code": 1,
                "log_path": LAST_CHECK_LOG,
                "error_count": 3,
            },
        },
    )
    assert state["last_execution"]["verify"]["log_path"] == LAST_CHECK_LOG
    assert state["last_execution"]["verify"]["error_count"] == 3


def test_execute_run_mypy_writes_last_check_log(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    (tmp_path / "eurika").mkdir()
    (tmp_path / "cli").mkdir()
    body = "a.py:1: error: one\nb.py:2: error: two\nFound 2 errors in 2 files\n"

    def fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=body, stderr="")

    monkeypatch.setattr("eurika.api.task_executor_executors.subprocess.run", fake_run)
    report = execute_spec(tmp_path, build_task_spec(intent="run_mypy"))
    assert report.ok is False
    assert report.verification.get("log_path") == LAST_CHECK_LOG
    assert report.verification.get("error_count") == 2
    assert "Found 2 errors" in (tmp_path / LAST_CHECK_LOG).read_text(encoding="utf-8")


def test_agent_chat_prompt_includes_last_check(tmp_path: Path, monkeypatch) -> None:
    from eurika.agent.local_runtime import LocalAgentRuntime
    from tests.test_local_agent_backend import _runtime_call

    persist_last_check(
        tmp_path,
        {
            "ok": False,
            "runner": "mypy",
            "command": ["python", "-m", "mypy", "eurika", "cli"],
            "exit_code": 1,
            "output": "cli/wiring/entrypoints.py:17: error: import-not-found\nFound 1 error in 1 file\n",
        },
    )
    runtime = LocalAgentRuntime(tmp_path)
    seen: list[str] = []

    def _call(prompt: str):
        seen.append(prompt)
        return ('{"type":"final","text":"need last_check first"}', None)

    monkeypatch.setattr(runtime, "_call_model", _call)
    monkeypatch.setattr(runtime, "_accept_grounded_final", lambda text, _obs: text)
    _runtime_call(
        runtime,
        "session/chat",
        {"message": "исправь ошибки", "context": {"reviewInApprovals": True}},
        [],
    )
    assert seen
    blob = seen[0]
    assert "last_check" in blob
    assert "lastCheck" in blob or LAST_CHECK_LOG in blob
    assert "entrypoints.py" in blob
    assert "IMPLEMENT_REQUIRED" in blob


def test_agent_docs_question_does_not_seed_last_check(tmp_path: Path, monkeypatch) -> None:
    from eurika.agent.local_runtime import LocalAgentRuntime
    from tests.test_local_agent_backend import _runtime_call

    persist_last_check(
        tmp_path,
        {
            "ok": False,
            "runner": "mypy",
            "command": ["python", "-m", "mypy", "eurika", "cli"],
            "exit_code": 1,
            "output": "cli/wiring/entrypoints.py:17: error: import-not-found\nFound 1 error in 1 file\n",
        },
    )
    runtime = LocalAgentRuntime(tmp_path)
    seen: list[str] = []

    def _call(prompt: str):
        seen.append(prompt)
        return ('{"type":"final","text":"H3 is next"}', None)

    monkeypatch.setattr(runtime, "_call_model", _call)
    monkeypatch.setattr(runtime, "_accept_grounded_final", lambda text, _obs: text)
    out = _runtime_call(
        runtime,
        "session/chat",
        {"message": "проверь документы, что далее по плану?", "context": {}},
        [],
    )
    assert seen
    blob = seen[0]
    assert "Previous Chat quality-check failed" not in blob
    assert '"tool": "last_check"' not in blob
    assert '"lastCheck"' not in blob
    assert "DEVELOPMENT.md" in blob and "Текущий фокус" in blob
    assert "Do not mention last_check" in blob
    assert "Связь с last_check" in blob
    assert "Last check failed" not in str(out.get("text") or "")
    assert "I could not complete" not in str(out.get("text") or "")


def test_agent_docs_empty_final_falls_back_to_development_brief(tmp_path: Path, monkeypatch) -> None:
    from eurika.agent.local_runtime import LocalAgentRuntime
    from tests.test_continue_dev_docs import _write_dev
    from tests.test_local_agent_backend import _runtime_call

    _write_dev(tmp_path, "1. **CR-H H4 — один Chat.**")
    runtime = LocalAgentRuntime(tmp_path)
    monkeypatch.setattr(
        runtime, "_call_model", lambda _p: ('{"type":"final","text":"see docs/MISSING.md"}', None)
    )
    monkeypatch.setattr(runtime, "_accept_grounded_final", lambda _text, _obs: "")
    out = _runtime_call(
        runtime,
        "session/chat",
        {"message": "проверь документы, что далее по плану?", "context": {}},
        [],
    )
    text = str(out.get("text") or "")
    assert "CR-H H4" in text
    assert "From docs:" not in text
    assert "I could not complete" not in text


def test_agent_market_plan_empty_final_uses_freeze_brief(
    tmp_path: Path, monkeypatch
) -> None:
    from eurika.agent.local_runtime import LocalAgentRuntime
    from tests.test_continue_dev_docs import _write_dev
    from tests.test_local_agent_backend import _runtime_call

    _write_dev(tmp_path, "1. **CR-H H5 Thinking.**")
    (tmp_path / "docs" / "VISION.md").write_text(
        "# Vision\n\n### B. Market paper (по статистике journal)\n"
        "6. **HTF bias 4h** — не трогать, пока SL/horizon не стабилизируются.\n",
        encoding="utf-8",
    )
    runtime = LocalAgentRuntime(tmp_path)
    monkeypatch.setattr(
        runtime, "_call_model", lambda _p: ('{"type":"final","text":"From docs: x"}', None)
    )
    monkeypatch.setattr(runtime, "_accept_grounded_final", lambda _text, _obs: "")
    out = _runtime_call(
        runtime,
        "session/chat",
        {"message": "какие планы по развитию маркета?", "context": {}},
        [],
    )
    text = str(out.get("text") or "")
    assert "From docs:" not in text
    assert "I could not complete" not in text
    assert "freeze" in text.lower()
    assert "HTF" in text
    assert "live-ордера" in text


def test_try_park_last_check_import_fixes_writes_pending_plan(tmp_path: Path) -> None:
    from eurika.api.last_check import persist_last_check, try_park_last_check_import_fixes
    from eurika.orchestration.team_mode import load_pending_plan

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "old.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "new.py").write_text("def moved():\n    return 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_moved.py").write_text("from pkg.old import moved\n", encoding="utf-8")
    log = (
        "tests/test_moved.py:1: in <module>\n"
        "    from pkg.old import moved\n"
        "E   ImportError: cannot import name 'moved' from 'pkg.old'\n"
        "FAILED tests/test_moved.py::test_x\n"
    )
    persist_last_check(
        tmp_path,
        {
            "ok": False,
            "runner": "release_check",
            "command": ["./scripts/release_check.sh"],
            "exit_code": 1,
            "output": log,
        },
    )
    parked = try_park_last_check_import_fixes(tmp_path)
    assert parked is not None
    assert parked["approvalsQueued"] == 1
    plan = load_pending_plan(tmp_path)
    assert plan is not None
    assert plan["operations"][0]["target_file"] == "tests/test_moved.py"
    assert "from pkg.new import moved" in plan["operations"][0]["params"]["new_content"]


def test_last_check_is_the_task_only_on_fix() -> None:
    from eurika.api.last_check import last_check_is_the_task

    assert last_check_is_the_task("исправь ошибки")
    assert last_check_is_the_task("пофикси mypy")
    assert last_check_is_the_task("fix the errors")
    assert last_check_is_the_task("проверь документы, что далее по плану?") is False
    assert last_check_is_the_task("что дальше?") is False
    from eurika.api.last_check import docs_plan_is_the_task

    assert docs_plan_is_the_task("проверь документы, что далее по плану?")
    assert docs_plan_is_the_task("что дальше?")
    assert docs_plan_is_the_task("какие планы по развитию маркета?")
    assert docs_plan_is_the_task("исправь ошибки") is False
    assert docs_plan_is_the_task("поправь chat.py") is False


def test_docs_citations_are_not_rejected_as_non_implementation() -> None:
    from eurika.agent.local_runtime_ground import non_implementation_citations

    assert non_implementation_citations("Next is H3 — see docs/ROADMAP.md and docs/VISION.md.") == []
    assert non_implementation_citations("See tests/test_chat.py for the handler.") == [
        "tests/test_chat.py"
    ]


def test_grounded_fallback_after_last_check_asks_for_edits() -> None:
    from eurika.agent.local_runtime_ground import grounded_fallback

    seed = [
        {
            "tool": "last_check",
            "path": LAST_CHECK_LOG,
            "result": {"paths": ["eurika/api/self_model.py"]},
        }
    ]
    text = grounded_fallback(seed, "исправь ошибки")
    assert LAST_CHECK_LOG in text
    assert "From tool observations" not in text
    docs = grounded_fallback(seed, "проверь документы, что далее по плану?")
    assert "Last check failed" not in docs
    from_docs = grounded_fallback(
        [{"tool": "read", "path": "docs/DEVELOPMENT.md", "result": {"path": "docs/DEVELOPMENT.md"}}],
        "проверь документы, что далее по плану?",
    )
    assert from_docs == ""
    assert "From docs:" not in from_docs
    assert "Last check failed" not in from_docs
