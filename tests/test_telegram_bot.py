"""Tests for Telegram → chat_send bridge (VISION C.12 v1)."""

from __future__ import annotations

from pathlib import Path

from eurika.integrations.telegram_bot import (
    extract_text_update,
    format_telegram_reply,
    handle_text_message,
    parse_allowed_chat_ids,
    process_updates,
    run_telegram_bot,
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
