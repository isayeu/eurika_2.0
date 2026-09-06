"""Qt Chat must not echo live-activity session/chat as an assistant reply."""

from types import SimpleNamespace
from typing import cast

from qt_app.ui.handlers.chat_handlers import (
    _apply_live_activity_event,
    _live_event_echoes_in_chat,
)
from qt_app.ui.main_window import MainWindow


def test_session_chat_start_is_not_transcript_echo() -> None:
    event = {
        "kind": "chat",
        "phase": "start",
        "client": "agent",
        "method": "session/chat",
        "title": "session/chat — «сделай вкладку Models/LLM эргономичнее»",
    }
    assert _live_event_echoes_in_chat(event) is False
    assert _live_event_echoes_in_chat(
        {"kind": "chat", "method": "POST /api/chat", "title": "POST /api/chat — «hi»"}
    ) is False
    assert _live_event_echoes_in_chat(
        {"kind": "rpc", "method": "tool/call", "title": "tool/call read models_tab.py"}
    ) is True


def test_apply_session_chat_updates_status_not_transcript(monkeypatch) -> None:
    appended: list[str] = []
    terminal: list[str] = []
    status = SimpleNamespace(text="")
    status.setText = lambda t: setattr(status, "text", t)
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers._append_transcript",
        lambda _main, html: appended.append(html),
    )
    main = SimpleNamespace(
        status_label=status,
        terminal_emulator_output=SimpleNamespace(append=terminal.append),
    )
    _apply_live_activity_event(
        cast(MainWindow, main),
        {
            "kind": "chat",
            "phase": "start",
            "client": "agent",
            "method": "session/chat",
            "title": "session/chat — «сделай вкладку эргономичнее»",
        },
    )
    assert appended == []
    assert terminal == []
    assert "session/chat" in status.text


def test_apply_idle_self_dev_echoes_concrete_steps(monkeypatch) -> None:
    appended: list[str] = []
    terminal: list[str] = []
    status = SimpleNamespace(text="")
    status.setText = lambda t: setattr(status, "text", t)
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers._append_transcript",
        lambda _main, html: appended.append(html),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers._format_chat_line",
        lambda _main, _role, text, is_error=False: text,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers._scroll_transcript_to_bottom",
        lambda _main: None,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.focus_approvals_mode",
        lambda _main: None,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.QTimer.singleShot",
        lambda _ms, cb: None,
    )
    main = SimpleNamespace(
        status_label=status,
        terminal_emulator_output=SimpleNamespace(append=terminal.append),
        _chat_worker=None,
    )
    _apply_live_activity_event(
        cast(MainWindow, main),
        {
            "kind": "rpc",
            "phase": "start",
            "client": "idle_self_dev",
            "method": "idle_self_dev",
            "title": "саморазвитие: убрать unused import `os` в eurika/polygon/imports_ok.py",
        },
    )
    assert any("саморазвитие" in line and "imports_ok.py" in line for line in appended)
    appended.clear()
    _apply_live_activity_event(
        cast(MainWindow, main),
        {
            "kind": "progress",
            "phase": "progress",
            "client": "idle_self_dev",
            "method": "idle_self_dev",
            "title": "саморазвитие: sandbox apply+verify для drill `imports`…",
        },
    )
    assert any("sandbox apply+verify" in line for line in appended)
    appended.clear()
    _apply_live_activity_event(
        cast(MainWindow, main),
        {
            "kind": "rpc",
            "phase": "done",
            "client": "idle_self_dev",
            "method": "idle_self_dev",
            "title": "саморазвитие: убрать unused import",
            "ok": True,
            "text": (
                "саморазвитие: drill `imports` — убрать unused import `os` "
                "в eurika/polygon/imports_ok.py → Approvals"
            ),
            "approvalsQueued": 1,
        },
    )
    assert any("Approvals" in line for line in appended)


def test_apply_done_with_approvals_focuses(monkeypatch) -> None:
    focused: list[bool] = []
    terminal: list[str] = []
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.focus_approvals_mode",
        lambda _main: focused.append(True),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.QTimer.singleShot",
        lambda _ms, cb: cb(),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.terminal_tab._append_stream",
        lambda _main, text: terminal.append(text),
    )
    main = SimpleNamespace(
        status_label=SimpleNamespace(setText=lambda *_: None),
        terminal_emulator_output=SimpleNamespace(append=terminal.append),
        chat_input=None,
        tabs=SimpleNamespace(setCurrentIndex=lambda *_: None),
        terminal_tab_index=2,
        _chat_worker=None,
    )
    _apply_live_activity_event(
        cast(MainWindow, main),
        {
            "kind": "rpc",
            "phase": "done",
            "client": "qt-chat",
            "method": "prove-cycle --propose --drill extractable_block",
            "title": "prove-cycle --propose --drill extractable_block",
            "ok": True,
            "terminal_cmd": "$ eurika prove-cycle . --propose --drill extractable_block",
            "terminal_output": "pending",
            "terminal_exit_code": 0,
            "approvalsQueued": 1,
        },
    )
    assert focused == [True]
    assert any("prove-cycle" in line for line in terminal)
