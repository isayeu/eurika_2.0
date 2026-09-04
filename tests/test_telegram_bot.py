"""Tests for Telegram → chat_send bridge (VISION C.12 v1)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.integrations.telegram_bot import (
    extract_text_update,
    format_last_fix_status,
    format_telegram_reply,
    handle_text_message,
    is_apply_result_question,
    parse_allowed_chat_ids,
    process_updates,
    run_telegram_bot,
    telegram_slash_command,
)


def test_parse_allowed_chat_ids() -> None:
    assert parse_allowed_chat_ids("1, 2;3", allow_any=False) == {1, 2, 3}
    assert parse_allowed_chat_ids("", allow_any=False) == set()
    assert parse_allowed_chat_ids("9", allow_any=True) is None


def test_extract_text_update() -> None:
    assert extract_text_update({"update_id": 7, "message": {"chat": {"id": 42}, "text": "hi"}}) == (
        42,
        7,
        "hi",
    )
    assert extract_text_update({"update_id": 1, "message": {"chat": {"id": 1}, "photo": []}}) is None


def test_telegram_slash_start_does_not_hit_shell() -> None:
    reply = telegram_slash_command("/start")
    assert reply is not None
    assert "Eurika" in reply
    assert "Approvals" in reply
    assert telegram_slash_command("/start@MyBot") is not None
    assert telegram_slash_command("/foo") is not None
    assert telegram_slash_command("hi") is None


def test_handle_text_message_slash_skips_chat_send(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_chat(_root: Path, message: str, **_kwargs):
        calls.append(message)
        return {"text": "should not run", "error": None}

    out = handle_text_message(
        tmp_path, 1, "/start", allowed_chat_ids={1}, chat_send=fake_chat
    )
    assert calls == []
    assert "Eurika" in out
    assert "bash" not in out.lower()


def test_apply_result_question_uses_fix_report(tmp_path: Path) -> None:
    assert is_apply_result_question("Нажал run apply approved, получилось?")
    assert is_apply_result_question("verify success?")
    assert is_apply_result_question("статус apply")
    assert not is_apply_result_question("что получилось?")
    assert not is_apply_result_question("итог цели")
    (tmp_path / "eurika_fix_report.json").write_text(
        json.dumps(
            {
                "run_id": "20260904_140203",
                "modified": ["eurika/polygon/refactor_code_smell_drill.py"],
                "verify": {"success": True},
                "verify_duration_ms": 1998,
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    text = format_last_fix_status(tmp_path)
    assert "20260904_140203" in text
    assert "True" in text
    assert "refactor_code_smell_drill.py" in text

    calls: list[str] = []

    def fake_chat(_root: Path, message: str, **_kwargs):
        calls.append(message)
        return {"text": "nope", "error": None}

    out = handle_text_message(
        tmp_path,
        1,
        "Нажал run apply approved, получилось?",
        allowed_chat_ids={1},
        chat_send=fake_chat,
    )
    assert calls == []
    assert "20260904_140203" in out


def test_format_telegram_reply_mentions_approvals() -> None:
    text = format_telegram_reply(
        {"text": "C.14 ok", "approvalsQueued": 1, "error": None}
    )
    assert "C.14 ok" in text
    assert "Approvals" in text
    assert "apply-approved" in text


def test_handle_text_message_allowlist(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_chat(_root: Path, message: str, **_kwargs):
        calls.append(message)
        return {"text": f"echo:{message}", "error": None, "approvalsQueued": 0}

    denied = handle_text_message(
        tmp_path, 99, "scan", allowed_chat_ids={1}, chat_send=fake_chat
    )
    assert "allowlist" in denied.lower()
    assert calls == []

    ok = handle_text_message(
        tmp_path, 1, "scan", allowed_chat_ids={1}, chat_send=fake_chat
    )
    assert ok.startswith("echo:scan")
    assert calls == ["scan"]


def test_process_updates_sends_reply(tmp_path: Path) -> None:
    sent: list[tuple[int, str]] = []

    def fake_chat(_root: Path, message: str, **_kwargs):
        return {"text": f"got {message}", "approvalsQueued": 2}

    max_id = process_updates(
        tmp_path,
        [
            {"update_id": 10, "message": {"chat": {"id": 5}, "text": "третий полигон"}},
            {"update_id": 11, "message": {"chat": {"id": 5}, "sticker": {}}},
        ],
        token="t",
        allowed_chat_ids={5},
        chat_send=fake_chat,
        send_message=lambda _tok, cid, text: sent.append((cid, text)),
    )
    assert max_id == 11
    assert len(sent) == 1
    assert sent[0][0] == 5
    assert "got третий полигон" in sent[0][1]
    assert "Approvals" in sent[0][1]


def test_run_telegram_bot_once_mocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EURIKA_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("EURIKA_TELEGRAM_CHAT_IDS", "7")
    calls: list[str] = []
    sent: list[str] = []

    def fake_api(token: str, method: str, params=None, **_kwargs):
        assert token == "tok"
        if method == "getUpdates":
            return [
                {"update_id": 3, "message": {"chat": {"id": 7}, "text": "hello"}},
            ]
        if method == "sendMessage":
            sent.append(str((params or {}).get("text") or ""))
            return {"message_id": 1}
        raise AssertionError(method)

    def fake_chat(_root: Path, message: str, **_kwargs):
        calls.append(message)
        return {"text": "pong", "error": None}

    out = run_telegram_bot(
        tmp_path,
        once=True,
        api=fake_api,
        chat_send=fake_chat,
    )
    assert out.get("ok") is True
    assert out.get("return_code") == 0
    assert out.get("offset") == 4
    assert calls == ["hello"]
    assert sent and sent[0].startswith("pong")


def test_run_telegram_bot_requires_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EURIKA_TELEGRAM_BOT_TOKEN", raising=False)
    out = run_telegram_bot(tmp_path, once=True, token="")
    assert out.get("ok") is False
    assert "TOKEN" in (out.get("error") or "")
