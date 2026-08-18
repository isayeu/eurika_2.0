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
    assert "<table" in user
    assert "Eurika" in bot
    assert "eurika-chat://run/" in bot
    assert "#ef4444" in err or "#b91c1c" in err


def test_numbered_list_uses_explicit_markers_not_ol() -> None:
    html_out = render_chat_markdown("1. alpha\n\n1. beta\n\n1. gamma")
    assert "<ol" not in html_out
    assert "<ul" not in html_out
    assert "1." in html_out
    assert "2." in html_out
    assert "3." in html_out


def test_heading_quote_and_image_markdown(tmp_path) -> None:
    png = tmp_path / "shot.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    html_out = render_chat_markdown(
        "## Title\n> quote\n\n![screenshot](shot.png)",
        image_root=tmp_path,
    )
    assert "Title" in html_out
    assert "quote" in html_out
    assert "<img " in html_out
    assert "file://" in html_out


def test_appended_cards_do_not_continue_list_numbering() -> None:
    """Qt QTextBrowser.append used to nest 'You' as '2. You' after an <ol>."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QTextBlockFormat, QTextCursor
    from PySide6.QtWidgets import QApplication, QTextBrowser

    app = QApplication.instance() or QApplication([])
    view = QTextBrowser()
    first = format_chat_line_html(
        "assistant",
        "1. keep history\n2. store on disk\n3. restore in Qt",
        dark=True,
    )
    second = format_chat_line_html("user", "next question", dark=True)
    for chunk in (first, second):
        cursor = view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(chunk)
        cursor.insertBlock(QTextBlockFormat())
        view.setTextCursor(cursor)
    plain = view.toPlainText()
    assert "2. You" not in plain
    assert "3. You" not in plain
    assert "You" in plain
    assert "next question" in plain
