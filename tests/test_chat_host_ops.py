"""Tests: agent tool-loop (LLM decides → read-only tool runs → LLM answers)."""

from __future__ import annotations

from pathlib import Path

from eurika.api.chat_direct import resolve_direct_handler
from eurika.api.chat_host_ops import (
    extract_eurika_cmds,
    is_safe_host_command,
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
    # The second call must contain the real command output, not a template.
    assert "hello-device" in call.prompts[1]


def test_loop_answers_without_tools_when_not_needed() -> None:
    call = _scripted("Python — язык программирования.")
    result, err = run_llm_tool_loop("что такое python?", call=call)
    assert err is None
    assert result.commands == []
    assert result.ran_tools is False
    assert result.terminal_log == ""


def test_loop_never_leaves_command_block_in_answer() -> None:
    call = _scripted(
        "```eurika-cmds\necho one\n```",
        "Ответ без блоков.",
    )
    result, _ = run_llm_tool_loop("q", call=call)
    assert "eurika-cmds" not in result.text
    assert "```" not in result.text


def test_loop_feeds_back_rejected_commands_instead_of_giving_up() -> None:
    call = _scripted(
        "```eurika-cmds\nsudo rm -rf /\n```",
        "```eurika-cmds\necho safe\n```",
        "Готово.",
    )
    result, _ = run_llm_tool_loop("q", call=call)
    assert result.commands == ["echo safe"]
    assert "allowlist" in call.prompts[1]


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
        return None, "llm down"

    result, err = run_llm_tool_loop("q", call=_call)
    assert err == "llm down"
    assert result.text == ""


def test_python_code_block_is_not_a_tool_call() -> None:
    text = "Вот код:\n```python\nprint('test')\n```"
    assert extract_eurika_cmds(text) == []
    assert strip_tool_calls(text) == text


def test_extract_strips_pipes_and_unsafe() -> None:
    text = "```bash\nlspci | grep VGA\nnvidia-smi\nrm -rf /\n```"
    cmds = extract_eurika_cmds(text)
    assert "lspci" in cmds
    assert "nvidia-smi" in cmds
    assert all("|" not in c for c in cmds)
    assert "rm -rf /" not in cmds


def test_protocol_says_run_it_yourself() -> None:
    text = tool_protocol_instructions()
    assert "проверь" not in text.lower()
    assert "eurika-cmds" in text


def test_host_question_is_not_routed_to_a_domain_handler(tmp_path: Path) -> None:
    """No keyword routing: host questions reach the LLM tool-loop, not a canned handler."""
    for msg in (
        "какое последнее устройство было подключено к ноутбуку?",
        "как проверить какая видеокарта работает? (арчлинукс)",
        "я подключил блютус колонку, проверь она нормально подключилась?",
    ):
        assert resolve_direct_handler(tmp_path, msg) == (None, None)


def test_operacionka_stays_host_health(tmp_path: Path) -> None:
    assert resolve_direct_handler(tmp_path, "проверь операционку")[0] == "host_health"


def test_persona_keeps_ollama_in_rate_limit_footer() -> None:
    from eurika.api.chat_utils import enforce_eurika_persona

    text = "Ответ.\n\n—\nЛимит Groq достигнут. Пока отвечаю через локальный Ollama."
    out = enforce_eurika_persona(text)
    assert "Ollama" in out
    assert "локальный Eurika" not in out
    assert enforce_eurika_persona("I am Qwen") == "I am Eurika"


def test_safe_allowlist_is_sandbox_only() -> None:
    assert is_safe_host_command("lspci") is True
    assert is_safe_host_command("nvidia-smi") is True
    assert is_safe_host_command("rm -rf /") is False
    assert is_safe_host_command("cat /etc/shadow") is False
    assert is_safe_host_command("systemctl restart bluetooth") is False
