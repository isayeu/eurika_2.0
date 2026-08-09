"""Chat shell commands must mirror to Terminal payload (Cursor-like visibility)."""

from __future__ import annotations

from pathlib import Path


def test_chat_specific_pytest_returns_terminal_mirror(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod
    from eurika.api.task_executor_types import ExecutionReport

    monkeypatch.setattr(
        chat_mod,
        "execute_spec",
        lambda _root, _spec: ExecutionReport(
            ok=True,
            summary="tests passed",
            applied_steps=["run pytest"],
            verification={
                "ok": True,
                "runner": "pytest",
                "command": ["python", "-m", "pytest", "-q", "tests/test_plugin_hook_orchestration.py"],
                "exit_code": 0,
                "output": ".... [100%]",
            },
        ),
    )

    out = chat_mod.chat_send(
        tmp_path, "запусти тест tests/test_plugin_hook_orchestration.py"
    )

    assert "tests/test_plugin_hook_orchestration.py" in (out.get("terminal_cmd") or "")
    assert out.get("terminal_output") == ".... [100%]"
    assert out.get("terminal_exit_code") == 0


def test_chat_scan_returns_terminal_mirror(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod

    calls: list[str] = []

    def _run(cmd: str) -> tuple[str, int]:
        calls.append(cmd)
        return ("scan ok\nmodules=1", 0)

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no llm")),
    )
    out = chat_mod.chat_send(tmp_path, "просканируй проект", run_command_with_result=_run)
    assert out.get("error") is None
    assert out.get("terminal_cmd", "").startswith("$ ")
    assert "eurika scan" in (out.get("terminal_cmd") or "")
    assert "scan ok" in (out.get("terminal_output") or "")
    assert out.get("terminal_exit_code") == 0
    assert calls and "scan" in calls[0]


def test_chat_self_check_returns_full_terminal_output(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod

    def _run(cmd: str) -> tuple[str, int]:
        assert "self-check" in cmd
        return ("SELF-CHECK OK\nbinance: skip", 0)

    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no llm")),
    )
    out = chat_mod.chat_send(
        tmp_path,
        "проведи self-check",
        run_command_with_result=_run,
    )
    text = out.get("text") or ""
    assert "Self-check" in text or "self-check" in text.lower()
    assert "SELF-CHECK OK" in (out.get("terminal_output") or "")
    assert out.get("terminal_cmd", "").startswith("$ ")
    assert out.get("terminal_exit_code") == 0


def test_chat_host_health_operacionka(tmp_path: Path, monkeypatch) -> None:
    import eurika.api.chat as chat_mod
    from eurika.api.host_health import HostHealthResult

    monkeypatch.setattr(
        "eurika.api.host_health.run_host_health_probe",
        lambda: HostHealthResult(
            ok=True,
            level="ok",
            output="=== HOST HEALTH ===\nuptime ok\n=== done ===",
            facts=("kernel: test", "uptime: up 1 day"),
        ),
    )
    monkeypatch.setattr(
        "eurika.api.host_health.enrich_host_health_with_llm",
        lambda facts, use_llm=True: facts + "\n\n**Заключение (LLM):**\nХост в порядке.",
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("llm via enrich mock")),
    )
    out = chat_mod.chat_send(tmp_path, "проверь операционку")
    assert out.get("error") is None
    assert "Здоровье ОС" in (out.get("text") or "")
    assert "Советы:" in (out.get("text") or "")
    assert "не проекта" in (out.get("text") or "").lower() or "не проекта Eurika" in (out.get("text") or "")
    assert "host-health" in (out.get("terminal_cmd") or "")
    assert "uptime ok" in (out.get("terminal_output") or "")


def test_chat_host_health_attention_never_raw_error(tmp_path: Path, monkeypatch) -> None:
    """Even when level is bad/attention, chat must not get raw probe as error."""
    import eurika.api.chat as chat_mod
    from eurika.api.host_health import HostHealthResult

    raw = "=== HOST HEALTH ===\nStack trace of thread 1:\n#0 abort\n=== done ==="
    monkeypatch.setattr(
        "eurika.api.host_health.run_host_health_probe",
        lambda: HostHealthResult(
            ok=False,
            level="bad",
            output=raw,
            facts=("disk / 96% full",),
        ),
    )
    monkeypatch.setattr(
        "eurika.api.host_health.enrich_host_health_with_llm",
        lambda facts, use_llm=True: facts,
    )
    out = chat_mod.chat_send(tmp_path, "проверь операционку")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "Здоровье ОС" in text
    assert "Советы:" in text
    assert "Stack trace" not in text
    assert "Stack trace" in (out.get("terminal_output") or "")


def test_format_self_check_os_focus_skips_architecture_noise() -> None:
    from eurika.api.chat_utils import format_self_check_for_chat

    raw = (
        "ity=18.00)\n- god_module @ patch_engine.py\n"
        "PYTORCH (optional ML runtime)\n\navailable: yes\ndevice: cpu\ncuda: no\nsmoke: ok\n\n"
        "BINANCE (read-only)\n\nready: yes\nping: yes\n\n"
        "LBOT (remote read-only)\n\nok: yes\nrunning: yes\n\n"
        "LAYER DISCIPLINE: OK (0 forbidden, 0 layer violations)\n\n"
        "FILE SIZE LIMITS\nx\n\n"
        "SELF-GUARD (R5):\nViolations: 39 file-size (>400 LOC)\n"
    )
    text = format_self_check_for_chat(raw, ok=True, os_focus=True)
    assert "ity=18" not in text
    assert "god_module" not in text
    assert "PYTORCH" in text and "BINANCE" in text
    assert "Terminal" in text


def test_chat_ls_mirrors_terminal(tmp_path: Path, monkeypatch) -> None:
    """Bare ``ls`` → host_shell; output mirrored to Terminal fields."""
    import eurika.api.chat as chat_mod
    from eurika.api.chat_host_ops import HostCommandResult

    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")

    def _fake_run(cmd, **_kw):
        assert "ls" in cmd
        return HostCommandResult(0, "-rw-r--r-- a.py\n")

    monkeypatch.setattr(
        "eurika.api.chat_host_ops.run_host_command_with_privilege",
        _fake_run,
    )
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no llm")),
    )
    out = chat_mod.chat_send(tmp_path, "ls")
    assert "a.py" in (out.get("text") or "") or "a.py" in (out.get("terminal_output") or "")
    assert "ls" in (out.get("terminal_cmd") or "")
    assert out.get("terminal_exit_code") == 0


def test_chat_ls_phrase_uses_tool_loop(tmp_path: Path, monkeypatch) -> None:
    """Russian ls phrase → LLM tool-loop, not project_ls template."""
    import eurika.api.chat as chat_mod
    from eurika.api.chat_host_ops import HostCommandResult

    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    calls = {"n": 0}

    def _llm(prompt, max_tokens=1024):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("```eurika-cmds\nls -la\n```", None)
        return ("В корне есть a.py.", None)

    def _fake_run(cmd, **_kw):
        assert "ls" in cmd
        return HostCommandResult(0, "-rw-r--r-- a.py\n")

    monkeypatch.setattr("eurika.reasoning.architect.call_llm_with_prompt", _llm)
    monkeypatch.setattr(
        "eurika.api.chat_host_ops.run_host_command_with_privilege",
        _fake_run,
    )
    out = chat_mod.chat_send(tmp_path, "выполни ls")
    assert out.get("error") is None
    assert "a.py" in (out.get("text") or "")
    assert calls["n"] >= 2
    turns = tmp_path / ".eurika" / "chat_tool_turns.jsonl"
    assert turns.is_file()
    line = turns.read_text(encoding="utf-8").strip().splitlines()[-1]
    import json

    row = json.loads(line)
    assert row.get("event") == "tool_turn"
    assert any("ls" in str(c) for c in row.get("commands") or [])
