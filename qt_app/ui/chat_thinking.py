"""CR-H5: expandable Thinking row — live steps while Chat is working."""
from __future__ import annotations

import html
from typing import Any


def thinking_title(steps: list[str], *, busy: bool) -> str:
    """Cursor-style header: just Thinking, steps live in the list below."""
    return "Thinking…" if busy else "Thinking"


def format_thinking_step(raw: str) -> str:
    """Make a tool line look like Cursor (Read / Grepped / Running)."""
    text = _strip_thinking_prefix(raw).strip()
    if not text:
        return ""
    lower = text.lower()
    if lower == "модель" or lower.startswith("модель "):
        return "Model" + text[len("модель") :]
    mapping = (
        ("read ", "Read "),
        ("search ", "Grepped "),
        ("edit ", "Edited "),
        ("skill ", "Running "),
        ("tests ", "Tests "),
        ("terminal ", "Terminal "),
    )
    for prefix, label in mapping:
        if lower.startswith(prefix):
            return label + text[len(prefix) :]
    return text


def format_thinking_html(steps: list[str]) -> str:
    """Muted in-thread block that stays under the user bubble (Cursor-like)."""
    rows = "".join(
        f'<div style="margin:1px 0 1px 2px;">{html.escape(step)}</div>'
        for step in steps
        if step
    )
    return (
        '<div style="color:#94a3b8; font-size:13px; margin:8px 20px 16px 8px;">'
        '<div style="font-style:italic; margin-bottom:8px;">Thinking</div>'
        f"{rows}</div>"
    )


def thinking_step_from_terminal_line(line: str) -> str | None:
    """Progress line for Thinking (release_check / pytest), not every test name."""
    text = (line or "").strip()
    if not text:
        return None
    if text.startswith("==>") or text.startswith("pytest [") or text.startswith("FAILED "):
        return text[:160]
    if text.startswith("FAIL:") or text.startswith("WARN:"):
        return text[:160]
    return None


def thinking_step_from_event(event: dict[str, Any]) -> str | None:
    """User-visible step from live_activity. Skip idle_self_dev noise."""
    method = str(event.get("method") or "")
    client = str(event.get("client") or "")
    if method == "idle_self_dev" or client == "idle_self_dev":
        return None
    phase = str(event.get("phase") or "")
    title = str(event.get("title") or "").strip()
    kind = str(event.get("kind") or "")
    if phase == "progress":
        return _strip_thinking_prefix(title) or "working"
    if phase == "start" and (
        "chat" in method or kind == "chat" or title.startswith("Thinking")
    ):
        return _strip_thinking_prefix(title) or "started"
    if title.startswith("Thinking"):
        return _strip_thinking_prefix(title)
    return None


def _strip_thinking_prefix(title: str) -> str:
    text = (title or "").strip()
    for prefix in ("Thinking · ", "Thinking…", "Thinking: ", "Thinking "):
        if text.startswith(prefix):
            return text[len(prefix) :].strip() or text
    if text == "Thinking":
        return ""
    return text


def begin_chat_thinking(main: Any) -> None:
    main._chat_thinking_steps = []
    main._chat_thinking_busy = True
    main._chat_thinking_committed = False
    btn = getattr(main, "chat_thinking_btn", None)
    if btn is not None:
        btn.setChecked(True)
    refresh_chat_thinking(main)


def append_chat_thinking(main: Any, step: str) -> None:
    text = format_thinking_step(step)
    if not text:
        return
    steps = getattr(main, "_chat_thinking_steps", None)
    if not isinstance(steps, list):
        steps = []
        main._chat_thinking_steps = steps
    if steps and steps[-1] == text:
        return
    steps.append(text)
    refresh_chat_thinking(main)


def take_chat_thinking_steps(main: Any) -> list[str]:
    steps = [str(item) for item in (getattr(main, "_chat_thinking_steps", None) or []) if item]
    main._chat_thinking_steps = []
    return steps


def finish_chat_thinking(main: Any) -> None:
    main._chat_thinking_busy = False
    refresh_chat_thinking(main)


def refresh_chat_thinking(main: Any) -> None:
    btn = getattr(main, "chat_thinking_btn", None)
    detail = getattr(main, "chat_thinking_detail", None)
    label = getattr(main, "chat_typing_label", None)
    steps = list(getattr(main, "_chat_thinking_steps", []) or [])
    busy = bool(getattr(main, "_chat_thinking_busy", False))
    title = thinking_title(steps, busy=busy)
    if btn is None or detail is None:
        if label is not None:
            if busy or steps:
                label.setText(title)
                label.setVisible(True)
            else:
                label.clear()
                label.setVisible(False)
        return
    panel = getattr(main, "chat_thinking_panel", None)
    if not busy and not steps:
        btn.setVisible(False)
        detail.setVisible(False)
        if panel is not None:
            panel.setVisible(False)
        if label is not None:
            label.clear()
            label.setVisible(False)
        return
    btn.setText(title)
    btn.setVisible(True)
    if panel is not None:
        panel.setVisible(True)
    detail.setPlainText("\n".join(steps) if steps else "")
    if busy and not btn.isChecked():
        btn.setChecked(True)
    detail.setVisible(bool(btn.isChecked()))
    if label is not None:
        label.clear()
        label.setVisible(False)
