"""Read-only host admin v0: classify, queue, HITL apply — no phrase-book."""
from __future__ import annotations

from pathlib import Path

from eurika.api.host_admin import (
    apply_pending_host_admin,
    classify_host_admin_command,
    clear_pending_host_admin,
    format_host_admin_brief,
    host_command_mutates_os,
    load_pending_host_admin,
    queue_host_admin,
)
from eurika.api.chat_host_ops import HostCommandResult, run_llm_tool_loop, tool_protocol_instructions


def test_observe_commands_are_not_os_mutations() -> None:
    for cmd in (
        "systemctl status cups",
        "systemctl --user status cups",
        "systemctl --failed",
        "journalctl -u cups -n 30 --no-pager",
        "pacman -Q cups",
        "pacman -Ss cups",
        "pacman -Si cups",
        "apt list --installed",
        "nmcli device status",
        "nmcli connection show --active",
        "lpstat -p -d",
        "bluetoothctl devices",
        "df -h",
        "free -h",
        "sudo systemctl status sshd",
    ):
        assert classify_host_admin_command(cmd) == "observe", cmd
        assert host_command_mutates_os(cmd) is False


def test_mutate_commands_are_os_mutations() -> None:
    for cmd in (
        "pacman -S cups",
        "sudo pacman -S cups",
        "pacman -Syu",
        "apt install -y cups",
        "systemctl restart cups",
        "systemctl enable cups",
        "reboot",
        "nmcli radio wifi off",
        "nmcli connection up home",
        "bluetoothctl pair AA:BB",
        "pip install requests",
        "modprobe dummy",
    ):
        assert classify_host_admin_command(cmd) == "mutate", cmd
        assert host_command_mutates_os(cmd) is True


def test_workspace_write_stays_distinct() -> None:
    assert classify_host_admin_command("rm -f eurika/api/ops.py") == "workspace_write"
    assert classify_host_admin_command("echo x > README.md") == "workspace_write"


def test_queue_and_apply_hitl(tmp_path: Path, monkeypatch) -> None:
    queued = queue_host_admin(tmp_path, ["pacman -S cups"], source="test")
    assert queued["commands"] == ["pacman -S cups"]
    assert load_pending_host_admin(tmp_path) is not None
    brief = format_host_admin_brief(tmp_path)
    assert any("pacman -S cups" in line for line in brief)

    ran: list[str] = []

    def _fake(cmd, *, privilege_prompt=None, timeout=60.0, cwd=None):
        ran.append(cmd)
        return HostCommandResult(0, "installed (fake)", used_sudo=True)

    monkeypatch.setattr(
        "eurika.api.chat_host_ops.run_host_command_with_privilege", _fake
    )
    out = apply_pending_host_admin(tmp_path)
    assert out["ok"] is True
    assert ran == ["pacman -S cups"]
    assert load_pending_host_admin(tmp_path) is None


def test_reject_clears_queue(tmp_path: Path) -> None:
    queue_host_admin(tmp_path, ["reboot"])
    assert clear_pending_host_admin(tmp_path) is True
    assert load_pending_host_admin(tmp_path) is None


def test_tool_loop_queues_mutate_without_running(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise AssertionError("mutating OS command must not run before HITL")

    monkeypatch.setattr("eurika.api.chat_host_ops.run_host_command_with_privilege", _boom)

    class _Llm:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, prompt: str, max_tokens: int):
            self.n += 1
            if self.n == 1:
                return ("```eurika-cmds\npacman -S cups\n```", None)
            return ("Пакет в очереди HITL, не установлен.", None)

    result, err = run_llm_tool_loop(
        "поставь cups",
        call=_Llm(),
        cwd=str(tmp_path),
        project_root=tmp_path,
    )
    assert err is None
    assert result.commands == ["pacman -S cups"]
    assert "read-only" in result.terminal_log
    pending = load_pending_host_admin(tmp_path)
    assert pending is not None
    assert pending["commands"] == ["pacman -S cups"]


def test_tool_loop_still_runs_observe(tmp_path: Path, monkeypatch) -> None:
    def _ok(cmd, *, privilege_prompt=None, timeout=60.0, cwd=None):
        return HostCommandResult(0, "active")

    monkeypatch.setattr("eurika.api.chat_host_ops.run_host_command_with_privilege", _ok)

    class _Llm:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, prompt: str, max_tokens: int):
            self.n += 1
            if self.n == 1:
                return ("```eurika-cmds\nsystemctl status cups\n```", None)
            return ("cups active.", None)

    result, err = run_llm_tool_loop(
        "статус cups",
        call=_Llm(),
        cwd=str(tmp_path),
        project_root=tmp_path,
    )
    assert err is None
    assert result.text == "cups active."
    assert load_pending_host_admin(tmp_path) is None


def test_chat_apply_runs_queued_host_admin(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.chat import chat_send

    queue_host_admin(tmp_path, ["systemctl restart cups"], source="test")
    ran: list[str] = []

    def _fake(cmd, *, privilege_prompt=None, timeout=60.0, cwd=None):
        ran.append(cmd)
        return HostCommandResult(0, "restarted (fake)")

    monkeypatch.setattr(
        "eurika.api.chat_host_ops.run_host_command_with_privilege", _fake
    )
    out = chat_send(tmp_path, "одобрить", persist_history=True)
    assert out.get("error") is None
    assert ran == ["systemctl restart cups"]
    assert "Host admin HITL" in (out.get("text") or "")
    assert load_pending_host_admin(tmp_path) is None


def test_bare_shell_mutate_queues_without_running(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.chat import chat_send

    def _boom(*_a, **_k):
        raise AssertionError("bare mutating shell must not run before HITL")

    monkeypatch.setattr(
        "eurika.api.chat_host_ops.run_host_command_with_privilege", _boom
    )
    out = chat_send(tmp_path, "systemctl restart cups", persist_history=True)
    assert out.get("error") is None
    assert "read-only" in (out.get("text") or "")
    assert "host admin" in (out.get("text") or "").lower()
    assert load_pending_host_admin(tmp_path)["commands"] == ["systemctl restart cups"]


def test_chat_context_shows_host_admin_queue(tmp_path: Path) -> None:
    from eurika.api.chat import chat_send
    from eurika.api.chat_context import format_dialog_goal_block, load_dialog_state

    queue_host_admin(tmp_path, ["systemctl enable cups"], source="test")
    block = format_dialog_goal_block(load_dialog_state(tmp_path), project_root=tmp_path)
    assert "Host admin HITL" in block
    assert "systemctl enable cups" in block
    out = chat_send(tmp_path, "что в контексте?", persist_history=True)
    assert "Host admin HITL" in (out.get("text") or "")
    assert "systemctl enable cups" in (out.get("text") or "")


def test_chat_reject_host_admin_wording(tmp_path: Path) -> None:
    from eurika.api.chat import chat_send

    queue_host_admin(tmp_path, ["reboot"], source="test")
    out = chat_send(tmp_path, "отклонить", persist_history=True)
    assert "host admin" in (out.get("text") or "").lower()
    assert load_pending_host_admin(tmp_path) is None


def test_protocol_teaches_read_only_not_autostart() -> None:
    proto = tool_protocol_instructions()
    assert "read-only" in proto
    assert "одобрить" in proto
    assert "HITL" in proto
    assert 'if "принтер"' not in proto
