"""Tests for Qt chat light-markdown renderer (fenced frames, Copy/Run links)."""

from __future__ import annotations

from qt_app.ui.chat_markdown import (
    format_chat_line_html,
    looks_like_shell,
    parse_chat_action_url,
    render_chat_markdown,
    shell_command_from_block,
)


def test_plain_text_is_escaped() -> None:
    html_out = render_chat_markdown('say <script>alert(1)</script> & ok')
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&amp;" in html_out


def test_fenced_python_has_copy_not_run() -> None:
    payloads: dict[str, str] = {}
    html_out = render_chat_markdown(
        "before\n```python\nprint(1)\n```\nafter",
        payloads=payloads,
    )
    assert "eurika-chat://copy/" in html_out
    assert "eurika-chat://run/" not in html_out
    assert "print(1)" in html_out
    assert len(payloads) == 1
    assert list(payloads.values())[0] == "print(1)"


def test_fenced_bash_has_copy_and_run() -> None:
    payloads: dict[str, str] = {}
    html_out = render_chat_markdown(
        "```bash\nls -la\n```",
        payloads=payloads,
    )
    assert "eurika-chat://copy/" in html_out
    assert "eurika-chat://run/" in html_out
    assert "ls -la" in html_out
    assert "bash" in html_out


def test_empty_lang_shell_heuristic() -> None:
    assert looks_like_shell("eurika scan .", "") is True
    assert looks_like_shell("$ git status", "") is True
    assert looks_like_shell("def foo():\n    return 1", "") is False
    assert looks_like_shell("print(1)", "python") is False
    assert looks_like_shell("ls", "eurika-cmds") is False


def test_inline_code_and_bold() -> None:
    html_out = render_chat_markdown("use **bold** and `x=1` here")
    assert "<b>bold</b>" in html_out
    assert "<code" in html_out
    assert "x=1" in html_out


def test_parse_action_url() -> None:
    assert parse_chat_action_url("eurika-chat://copy/abc123") == ("copy", "abc123")
    assert parse_chat_action_url("eurika-chat://run/zz") == ("run", "zz")
    assert parse_chat_action_url("https://example.com") is None


def test_shell_command_strips_prompt() -> None:
    assert shell_command_from_block("$ ls -la\n$ pwd") == "ls -la\npwd"


def test_format_chat_line_roles() -> None:
    payloads: dict[str, str] = {}
    user = format_chat_line_html("user", "hi", payloads=payloads)
    bot = format_chat_line_html("assistant", "```sh\npwd\n```", payloads=payloads)
    err = format_chat_line_html("assistant", "boom", is_error=True, payloads=payloads)
    assert "You" in user
    assert "Eurika" in bot
    assert "eurika-chat://run/" in bot
    assert "#b91c1c" in err
