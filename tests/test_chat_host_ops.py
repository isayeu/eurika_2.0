"""Tests: agent tool-loop (LLM decides → host tools run → LLM answers)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat_direct import resolve_direct_handler
from eurika.api.chat_host_ops import (
    extract_eurika_cmds,
    has_tool_call,
    is_safe_host_command,
    run_host_command,
    run_llm_tool_loop,
    strip_tool_calls,
    tool_protocol_instructions,
)


class _ScriptedLlm:
    """LLM stub returning the given replies in order; records every prompt."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, prompt: str, max_tokens: int) -> tuple[str | None, str | None]:
        self.prompts.append(prompt)
        return (self._replies.pop(0) if self._replies else "готово"), None


def _scripted(*replies: str) -> _ScriptedLlm:
    return _ScriptedLlm(*replies)


def test_loop_runs_tool_and_answers_from_output() -> None:
    call = _scripted(
        "Сейчас посмотрю.\n```eurika-cmds\necho hello-device\n```",
        "Последним подключено hello-device.",
    )
    result, err = run_llm_tool_loop("вопрос", call=call)
    assert err is None
    assert result.commands == ["echo hello-device"]
    assert "hello-device" in result.terminal_log
    assert result.text == "Последним подключено hello-device."
    assert "hello-device" in call.prompts[1]


def test_loop_answers_without_tools_when_not_needed() -> None:
    call = _scripted("Python — язык программирования.")
    result, err = run_llm_tool_loop("что такое python?", call=call)
    assert err is None
    assert result.commands == []
    assert result.ran_tools is False
    assert result.terminal_log == ""


def test_loop_never_leaves_protocol_block_in_answer() -> None:
    call = _scripted(
        "```eurika-cmds\necho one\n```",
        "Ответ без блоков.",
    )
    result, _ = run_llm_tool_loop("q", call=call)
    assert "eurika-cmds" not in result.text


def test_unwrap_bash_fence_path_to_prose() -> None:
    from eurika.api.chat_host_ops import unwrap_fact_code_fence

    assert unwrap_fact_code_fence("```bash\n/home/andrei\n```") == "Текущий каталог: /home/andrei"
    # Command examples must keep the fence (Copy/Run in chat).
    assert unwrap_fact_code_fence("```bash\npwd\n```") == "```bash\npwd\n```"
    assert unwrap_fact_code_fence("```bash\nls -la\n```") == "```bash\nls -la\n```"
    with_footer = (
        "```code\n/mnt/storage/project/eurika_2.0.Qt\n```\n\n—\n"
        "Лимит Groq достигнут. Пока отвечаю через локальный Ollama."
    )
    out = unwrap_fact_code_fence(with_footer)
    assert out.startswith("Текущий каталог: /mnt/storage/project/eurika_2.0.Qt")
    assert "Лимит Groq" in out
    assert "```" not in out.split("—")[0]


def test_pwd_uses_project_cwd(tmp_path) -> None:
    from eurika.api.chat_host_ops import run_host_command

    r = run_host_command("pwd", cwd=str(tmp_path))
    assert r.exit_code == 0
    assert str(tmp_path.resolve()) in r.output


def test_ordinary_bash_fence_is_not_a_tool_call() -> None:
    """UI Copy/Run examples must not be auto-executed or stripped."""
    text = "Пример:\n```bash\npwd\n```\n"
    assert extract_eurika_cmds(text) == []
    assert "```bash" in strip_tool_calls(text)


def test_malformed_code_fence_with_eurika_header_is_tool_call() -> None:
    """Ollama often emits ```code / eurika-cmds: / pwd instead of ```eurika-cmds."""
    text = "```code\neurika-cmds:\npwd\n```"
    assert extract_eurika_cmds(text) == ["pwd"]
    assert strip_tool_calls(text) == ""


def test_malformed_bare_header_is_tool_call() -> None:
    text = "eurika-cmds:\npwd\n"
    assert extract_eurika_cmds(text) == ["pwd"]
    assert "pwd" not in strip_tool_calls(text)


def test_bare_sed_polygon_read_is_tool_call() -> None:
    """Weak models dump `sed -n` instead of a ```eurika-cmds``` fence."""
    cmd = "sed -n '1,200p' eurika/polygon/refactor_code_smell_if_chain.py"
    assert extract_eurika_cmds(cmd) == [cmd]
    assert extract_eurika_cmds("cat /etc/passwd") == []
    assert extract_eurika_cmds("rm eurika/polygon/deep_nesting.py") == []


def test_host_command_mutates_workspace_blocks_writes() -> None:
    from eurika.api.chat_host_ops import host_command_mutates_workspace

    assert host_command_mutates_workspace("sed -n '1,80p' eurika/polygon/deep_nesting.py") is False
    assert host_command_mutates_workspace("python -c \"print(1)\"") is False
    assert host_command_mutates_workspace("ls -la 2>/dev/null") is False
    assert host_command_mutates_workspace("echo hi > eurika/polygon/deep_nesting.py") is True
    assert host_command_mutates_workspace("rm -f eurika/polygon/imports_ok.py") is True
    assert host_command_mutates_workspace("tee eurika/polygon/imports_ok.py") is True
    assert host_command_mutates_workspace(
        "python -c \"from pathlib import Path; Path('x.py').write_text('nope')\""
    ) is True


def test_pwd_and_pipes_are_allowed() -> None:
    assert is_safe_host_command("pwd") is True
    assert extract_eurika_cmds("```eurika-cmds\npwd\nls -la | head\n```") == [
        "pwd",
        "ls -la | head",
    ]
    result = run_host_command("pwd")
    assert result.exit_code == 0
    assert result.output.strip()


def test_loop_runs_pwd_without_allowlist_rejection() -> None:
    call = _scripted(
        "```eurika-cmds\npwd\n```",
        "Текущий каталог получен.",
    )
    result, err = run_llm_tool_loop("pwd", call=call)
    assert err is None
    assert result.commands == ["pwd"]
    assert "allowlist" not in (call.prompts[1] if len(call.prompts) > 1 else "")


def test_fake_allowlist_answer_triggers_recovery() -> None:
    """History-poisoned models that invent the old allowlist get one recovery pass."""
    call = _scripted(
        "Команды вне allowlist. Разрешены только следующие команды:\namixer\nbluetoothctl\n",
        "```eurika-cmds\npwd\n```",
        "Каталог получен.",
    )
    result, err = run_llm_tool_loop("какой сейчас pwd?", call=call)
    assert err is None
    assert result.commands == ["pwd"]
    assert "allowlist" not in result.text.lower()
    assert "Каталог" in result.text


def test_ungrounded_macos_network_advice_triggers_cmds() -> None:
    """Lecture about netstat/Activity Monitor must not replace a live host check."""
    from eurika.api.chat_host_ops import looks_like_ungrounded_host_advice

    lecture = (
        "Для проверки подключений используйте netstat -tuln. "
        "Откройте Activity Monitor на macOS."
    )
    assert looks_like_ungrounded_host_advice(lecture) is True
    assert looks_like_ungrounded_host_advice("Python — язык программирования.") is False
    call = _scripted(
        lecture,
        "```eurika-cmds\necho wlan0 Hotel_Kolyma\n```",
        "Сейчас Wi‑Fi Hotel_Kolyma на wlan0.",
    )
    result, err = run_llm_tool_loop(
        "посмотри какие соединения к сети у меня сейчас на компе",
        call=call,
    )
    assert err is None
    assert result.commands == ["echo wlan0 Hotel_Kolyma"]
    assert "Hotel_Kolyma" in result.text
    assert "Activity Monitor" not in result.text


def test_socket_inventory_on_uplink_question_nudges_nmcli(monkeypatch) -> None:
    from eurika.api import chat_host_ops as hop
    from eurika.api.chat_host_ops import (
        commands_are_socket_inventory,
        message_asks_host_uplinks,
    )

    q = "посмотри какие соединения к сети у меня сейчас на компе"
    assert message_asks_host_uplinks(q) is True
    assert message_asks_host_uplinks("какие порты слушаются?") is False
    assert commands_are_socket_inventory(["ss -tuln", "lsof -i TCP"]) is True
    assert commands_are_socket_inventory(["nmcli device status"]) is False

    def _fake_run(cmd, *, privilege_prompt=None, timeout=60.0, cwd=None):
        out = "LISTEN 127.0.0.1:11434" if "ss" in cmd or "lsof" in cmd else "wlan0 Hotel_Kolyma\nwg0 ProDG.kz"
        return hop.HostCommandResult(0, out)

    monkeypatch.setattr(hop, "run_host_command_with_privilege", _fake_run)
    call = _scripted(
        "```eurika-cmds\nss -tuln\nlsof -i TCP\n```",
        "```eurika-cmds\nnmcli connection show --active\nip -br addr\n```",
        "Wi‑Fi Hotel_Kolyma и VPN ProDG.kz на wg0.",
    )
    result, err = run_llm_tool_loop(q, call=call, user_message=q, max_iters=4)
    assert err is None
    assert "ss -tuln" in result.commands
    assert any("nmcli" in c or "ip -br" in c for c in result.commands)
    assert "Hotel_Kolyma" in result.text
    assert any("nmcli" in p for p in call.prompts[1:])


def test_host_identity_injected_into_chat_prompt() -> None:
    from eurika.api.chat_prompt import build_chat_prompt

    prompt = build_chat_prompt(
        "посмотри какие соединения к сети у меня сейчас на компе",
        context="",
        history=None,
    )
    assert "[Host identity]" in prompt
    assert "Linux" in prompt
    assert "Activity Monitor" in prompt  # as a forbidden example
    assert "nmcli" in prompt


def test_empty_tool_block_asks_for_real_commands() -> None:
    call = _scripted(
        "```eurika-cmds\n\n```",
        "```eurika-cmds\necho ok\n```",
        "Готово.",
    )
    result, _ = run_llm_tool_loop("q", call=call)
    assert "пуст" in call.prompts[1].lower() or "не содержит" in call.prompts[1].lower()
    assert "echo ok" in result.commands


def test_privilege_prompt_password_path(monkeypatch) -> None:
    from eurika.api import chat_host_ops as hop

    calls: list[tuple[str, bool]] = []

    def _fake_run(cmd, *, password=None, use_sudo=False, timeout=60.0, cwd=None):
        calls.append((cmd, use_sudo))
        if use_sudo:
            return hop.HostCommandResult(0, "secret-ok", used_sudo=True)
        return hop.HostCommandResult(1, "Permission denied", used_sudo=False)

    monkeypatch.setattr(hop, "run_host_command", _fake_run)

    def _ask(_cmd: str, _hint: str):
        return "password", "secret"

    result = hop.run_host_command_with_privilege(
        "cat /etc/shadow",
        privilege_prompt=_ask,
    )
    assert result.exit_code == 0
    assert result.used_sudo is True
    assert calls[-1][1] is True


def test_privilege_prompt_continue_without_sudo(monkeypatch) -> None:
    from eurika.api import chat_host_ops as hop

    def _fake_run(cmd, *, password=None, use_sudo=False, timeout=60.0, cwd=None):
        return hop.HostCommandResult(1, "Permission denied", used_sudo=False)

    monkeypatch.setattr(hop, "run_host_command", _fake_run)

    def _ask(_cmd: str, _hint: str):
        return "continue", ""

    result = hop.run_host_command_with_privilege(
        "cat /root/x",
        privilege_prompt=_ask,
    )
    assert "без sudo" in result.output.lower() or "continued" in result.privilege_note


def test_loop_stops_asking_for_tools_on_last_iteration() -> None:
    call = _scripted(
        "```eurika-cmds\necho a\n```",
        "```eurika-cmds\necho b\n```",
        "```eurika-cmds\necho c\n```",
    )
    result, _ = run_llm_tool_loop("q", max_iters=3, call=call)
    assert result.commands == ["echo a", "echo b"]
    assert "Больше команд не запускай" in call.prompts[2]
    assert "ТОЛЬКО по фактам" in call.prompts[2]


def test_pack_observations_keeps_command_heads() -> None:
    from eurika.api.chat_host_ops import _pack_observations

    early = "$ hostnamectl\n(exit 0)\nStatic hostname: pavilion\n" + ("x" * 4000)
    late = "$ df -h\n(exit 0)\n/dev/sdb1 916G"
    packed = _pack_observations([early, late], budget=2500)
    assert "pavilion" in packed
    assert "/dev/sdb1" in packed or "df -h" in packed


def test_loop_reports_llm_error() -> None:
    def _call(prompt: str, max_tokens: int):
        return None, "boom"

    result, err = run_llm_tool_loop("q", call=_call)
    assert err == "boom"
    assert result.text == ""


def test_tool_protocol_has_no_allowlist_dump() -> None:
    text = tool_protocol_instructions()
    assert "eurika-cmds" in text
    assert "Разрешённые бинарники" not in text
    assert "бинарного allowlist НЕТ" in text
    assert "корень текущего проекта" in text or "cwd" in text.lower()
    assert "ls" in text
    assert "format_market_learning_block" in text
    assert "resolve_market_root" in text
    assert "eurika scan" in text
    assert "запахи кода" in text or "не через" in text.lower() or "НЕ через" in text
    assert "accuracy" in text.lower()
    # Mentions retired names only as forbidden-to-invent examples, not as a grant list.
    assert "Разрешены только" not in text


def test_message_asks_market_learning() -> None:
    from eurika.api.chat_host_ops import message_asks_market_learning

    assert message_asks_market_learning(
        "как успехи проекта, проведи разбор, особенно в части касающейся маркета"
    )
    assert message_asks_market_learning(
        "проведи аудит как проходит обучение ML, как вообще маркет справляется, стоит ли менять стратегию"
    )
    assert message_asks_market_learning("успехи обучения ML в проекте?")
    assert not message_asks_market_learning("покажи содержимое каталога")


def test_soft_scan_not_invented_for_ml_training_question() -> None:
    from eurika.api.chat_direct import _accept_soft_handler, resolve_direct_handler
    from pathlib import Path

    msg = "как успехи обучения ML в проекте?"
    assert _accept_soft_handler("scan", msg) is False
    assert _accept_soft_handler("list_docs", msg) is False
    assert _accept_soft_handler("scan", "scsn") is True
    assert resolve_direct_handler(Path("."), msg)[0] is None


def test_record_and_load_tool_turn_experience(tmp_path: Path) -> None:
    from eurika.api.chat_host_ops import (
        infer_tool_turn_hint,
        load_tool_turn_experience,
        record_tool_turn,
    )

    record_tool_turn(
        tmp_path,
        message="покажи содержимое каталога",
        commands=["ls -la"],
        exit_code=0,
        ok=True,
    )
    record_tool_turn(
        tmp_path,
        message="fail case",
        commands=["false"],
        exit_code=1,
        ok=False,
    )
    ml_cmd = (
        'python -c "from eurika.ml.root import resolve_market_root; '
        "from eurika.ml.learning_status import format_market_learning_block; "
        'print(format_market_learning_block(resolve_market_root()))"'
    )
    record_tool_turn(
        tmp_path,
        message="как успехи обучения ML?",
        commands=[ml_cmd],
        exit_code=0,
        ok=True,
        answer="Entry acc 0.57, equity 987",
    )
    # Noise: recent unrelated turn should not beat ML when query is about training.
    record_tool_turn(
        tmp_path,
        message="покажи git status",
        commands=["git status"],
        exit_code=0,
        ok=True,
    )
    path = tmp_path / ".eurika" / "chat_tool_turns.jsonl"
    assert path.is_file()
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ml_row = next(r for r in rows if "format_market_learning_block" in str(r.get("commands")))
    assert "market ML" in (ml_row.get("outcome_hint") or "")
    assert "не eurika scan" in (ml_row.get("outcome_hint") or "")

    snippet = load_tool_turn_experience(tmp_path, message="успехи обучения ML в проекте")
    assert "format_market_learning_block" in snippet
    assert "содержимое" in load_tool_turn_experience(tmp_path, message="содержимое каталога")
    assert "false" not in snippet
    assert infer_tool_turn_hint("x", [ml_cmd]).startswith("успехи")
    proto = tool_protocol_instructions(snippet)
    assert "Опыт tool-loop" in proto or "опыт tool-loop" in proto.lower()


def test_bare_shell_sudo_whoami_not_list_docs() -> None:
    from pathlib import Path

    from eurika.api.chat_direct import is_bare_shell_request, resolve_direct_handler

    assert is_bare_shell_request("sudo whoami") is True
    assert is_bare_shell_request("pwd") is True
    assert is_bare_shell_request("delete") is False
    assert is_bare_shell_request("remember my name") is False
    assert is_bare_shell_request("какой сейчас pwd?") is False
    assert is_bare_shell_request("покажи пример в блоке bash: pwd") is False
    handler, _ = resolve_direct_handler(Path("."), "sudo whoami")
    assert handler == "host_shell"


def test_host_facts_still_go_to_llm_not_direct(tmp_path: Path) -> None:
    """Regression: host questions must not be captured by hardcoded handlers."""
    handler, _cmd = resolve_direct_handler(tmp_path, "какое устройство подключалось последним?")
    assert handler is None
    handler, _cmd = resolve_direct_handler(tmp_path, "что за блютуз колонка у меня?")
    assert handler is None


def test_harden_host_command_adds_venv_excludes() -> None:
    from eurika.api.chat_host_ops import harden_host_command

    plain = harden_host_command('grep -n handshake eurika/agent/stdio.py')
    assert plain == 'grep -n handshake eurika/agent/stdio.py'
    recursive = harden_host_command('grep -Rin "handshake" .')
    assert "--exclude-dir=.venv" in recursive
    assert "--exclude-dir=.mypy_cache" in recursive
    already = harden_host_command('grep -Rin handshake . --exclude-dir=.venv')
    assert already.count("--exclude-dir=.venv") == 1
    assert "--exclude-dir=.mypy_cache" in already


def test_recursive_grep_skips_venv_tree(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "noise.py").write_text("handshake = 1\n", encoding="utf-8")
    src = tmp_path / "eurika"
    src.mkdir()
    (src / "stdio.py").write_text("def initialize():\n    handshake = True\n", encoding="utf-8")
    result = run_host_command('grep -Rin "handshake" .', cwd=str(tmp_path), timeout=10)
    assert result.exit_code == 0
    assert "stdio.py" in result.output
    assert ".venv" not in result.output

