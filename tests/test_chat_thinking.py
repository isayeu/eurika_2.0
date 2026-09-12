"""CR-H5: Thinking row helpers (no Qt widgets)."""

from qt_app.ui.chat_thinking import (
    format_thinking_html,
    format_thinking_step,
    thinking_step_from_event,
    thinking_step_from_terminal_line,
    thinking_title,
)


def test_thinking_title_is_cursor_header() -> None:
    assert thinking_title([], busy=True) == "Thinking…"
    assert thinking_title(["release_check"], busy=True) == "Thinking…"
    assert thinking_title(["a", "b"], busy=False) == "Thinking"


def test_format_thinking_step_cursor_verbs() -> None:
    assert format_thinking_step("read qt_app/ui/chat_tab.py") == "Read qt_app/ui/chat_tab.py"
    assert format_thinking_step("search wants_local_agent") == "Grepped wants_local_agent"
    assert format_thinking_step("skill release_check") == "Running release_check"
    assert format_thinking_step("модель") == "Model"


def test_format_thinking_html_is_in_thread_block() -> None:
    html = format_thinking_html(["Read foo.py", "Running release_check"])
    assert "Thinking" in html
    assert "Read foo.py" in html
    assert "Running release_check" in html


def test_thinking_step_from_release_check_progress() -> None:
    assert thinking_step_from_terminal_line("==> 1. Tests") == "==> 1. Tests"
    assert thinking_step_from_terminal_line("pytest [1005/1766]") == "pytest [1005/1766]"
    assert thinking_step_from_terminal_line("    passed something") is None


def test_thinking_step_from_progress_and_skips_self_dev() -> None:
    assert thinking_step_from_event(
        {"phase": "progress", "title": "Thinking · skill release_check"}
    ) == "skill release_check"
    assert thinking_step_from_event(
        {"phase": "start", "method": "session/chat", "title": "session/chat — «hello»"}
    )
    assert (
        thinking_step_from_event(
            {"phase": "progress", "method": "idle_self_dev", "title": "саморазвитие"}
        )
        is None
    )
    assert thinking_step_from_event(
        {"phase": "progress", "title": "Thinking · модель", "client": "agent"}
    ) == "модель"
