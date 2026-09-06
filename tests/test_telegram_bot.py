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


def test_telegram_bot_background_status_and_stop(tmp_path: Path, monkeypatch) -> None:
    from eurika.integrations.telegram_bot import (
        format_telegram_bot_status,
        start_telegram_bot_background,
        stop_telegram_bot_background,
        telegram_bot_status,
    )

    monkeypatch.setenv("EURIKA_TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("EURIKA_TELEGRAM_ALLOW_ANY", "1")

    class FakeProc:
        pid = 5555

        def poll(self):
            return None

    monkeypatch.setattr(
        "eurika.integrations.telegram_bot.subprocess.Popen",
        lambda *a, **k: FakeProc(),
    )
    out = start_telegram_bot_background(tmp_path)
    assert out.get("ok") is True
    assert out.get("pid") == 5555

    def alive_kill(pid, sig=0):
        if pid != 5555:
            raise OSError("unexpected")
        if sig == 0:
            return None
        raise OSError("no stop yet")

    monkeypatch.setattr("eurika.integrations.telegram_bot.os.kill", alive_kill)
    assert telegram_bot_status(tmp_path).get("running") is True
    text = format_telegram_bot_status(tmp_path)
    assert "running: **True**" in text
    assert "5555" in text

    killed: list[int] = []

    def fake_kill(pid, sig=0):
        if sig == 0 and pid in killed:
            raise OSError("gone")
        if sig != 0:
            killed.append(pid)

    monkeypatch.setattr("eurika.integrations.telegram_bot.os.kill", fake_kill)
    stop = stop_telegram_bot_background(tmp_path)
    assert stop.get("stopped") is True


def test_handle_text_status_slash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EURIKA_TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("EURIKA_TELEGRAM_ALLOW_ANY", "1")
    (tmp_path / ".eurika").mkdir(parents=True)
    (tmp_path / ".eurika" / "telegram_bot.pid").write_text("99999", encoding="utf-8")

    def fake_kill(pid, sig=0):
        raise OSError("dead")

    monkeypatch.setattr("eurika.integrations.telegram_bot.os.kill", fake_kill)
    out = handle_text_message(
        tmp_path, 1, "/status", allowed_chat_ids={1}, chat_send=lambda *_a, **_k: {}
    )
    assert "Telegram-bot" in out
    assert "running" in out.lower()


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


def test_format_approvals_notify_message() -> None:
    from eurika.integrations.telegram_bot import format_approvals_notify_message

    text = format_approvals_notify_message(
        Path("/tmp/demo"),
        [
            {
                "kind": "remove_unused_import",
                "target_file": "eurika/polygon/imports_ok.py",
                "team_decision": "pending",
            }
        ],
        patch_plan={"source": "prove_cycle_propose:imports", "summary": "C.14"},
    )
    assert "Approvals" in text
    assert "imports_ok.py" in text
    assert "prove_cycle_propose:imports" in text
    assert "/approve" in text
    assert "apply-approved" in text


def test_notify_approvals_pending_sends_and_dedupes(tmp_path: Path, monkeypatch) -> None:
    from eurika.integrations.telegram_bot import notify_approvals_pending

    monkeypatch.setenv("EURIKA_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("EURIKA_TELEGRAM_CHAT_IDS", "11,22")
    monkeypatch.delenv("EURIKA_TELEGRAM_ALLOW_ANY", raising=False)
    monkeypatch.delenv("EURIKA_TELEGRAM_NOTIFY_APPROVALS", raising=False)

    sent: list[tuple[int, str]] = []

    def fake_api(_token: str, method: str, params=None, **_k):
        assert method == "sendMessage"
        assert params.get("reply_markup")
        sent.append((int(params["chat_id"]), str(params["text"])))
        return {"message_id": 1}

    ops = [
        {
            "kind": "remove_unused_import",
            "target_file": "eurika/polygon/imports_ok.py",
            "team_decision": "pending",
        }
    ]
    out = notify_approvals_pending(
        tmp_path,
        operations=ops,
        patch_plan={"source": "idle_self_dev"},
        created_at="2026-09-06T00:00:00Z",
        api=fake_api,
    )
    assert out.get("skipped") is None
    assert out.get("sent") == 2
    assert {c for c, _ in sent} == {11, 22}
    assert "Approvals" in sent[0][1]

    again = notify_approvals_pending(
        tmp_path,
        operations=ops,
        patch_plan={"source": "idle_self_dev"},
        created_at="2026-09-06T00:00:00Z",
        api=fake_api,
    )
    assert again.get("skipped") == "already_notified"
    assert again.get("sent") == 0


def test_save_pending_plan_notifies_telegram(tmp_path: Path, monkeypatch) -> None:
    from eurika.orchestration.team_mode import save_pending_plan

    calls: list[dict] = []

    def fake_notify(root, **kwargs):
        calls.append({"root": str(root), **kwargs})
        return {"ok": True, "sent": 1, "skipped": None}

    monkeypatch.setattr(
        "eurika.integrations.telegram_bot.notify_approvals_pending",
        fake_notify,
    )
    save_pending_plan(
        tmp_path,
        {"source": "unit-test", "summary": "one op"},
        [{"kind": "agent_edit", "target_file": "a.py"}],
        [],
    )
    assert len(calls) == 1
    assert calls[0]["operations"][0]["kind"] == "agent_edit"


def test_decide_all_pending_approve_reject(tmp_path: Path) -> None:
    from eurika.orchestration.team_mode import (
        decide_all_pending,
        load_pending_plan,
        save_pending_plan,
    )

    save_pending_plan(
        tmp_path,
        {"source": "t", "summary": "1"},
        [
            {
                "kind": "remove_unused_import",
                "target_file": "a.py",
                "critic_verdict": "allow",
            }
        ],
        [],
        notify_telegram=False,
    )
    out = decide_all_pending(tmp_path, decision="approve", approved_by="tg")
    assert out["ok"] is True and out["decision"] == "approve"
    plan = load_pending_plan(tmp_path)
    assert plan["operations"][0]["team_decision"] == "approve"
    assert plan["operations"][0]["approved_by"] == "tg"
    out2 = decide_all_pending(tmp_path, decision="reject")
    assert out2["ok"] is True
    plan2 = load_pending_plan(tmp_path)
    assert plan2["operations"][0]["team_decision"] == "reject"


def test_telegram_approve_slash_and_callback(tmp_path: Path) -> None:
    from eurika.integrations.telegram_bot import (
        handle_text_message,
        process_updates,
    )
    from eurika.orchestration.team_mode import load_pending_plan, save_pending_plan

    save_pending_plan(
        tmp_path,
        {"source": "idle", "summary": "op"},
        [
            {
                "kind": "extract_block_to_helper",
                "target_file": "eurika/polygon/deep_nesting.py",
                "critic_verdict": "allow",
            }
        ],
        [],
        notify_telegram=False,
    )
    reply = handle_text_message(
        tmp_path, 42, "/approve", allowed_chat_ids={42}
    )
    assert "approve" in reply.lower()
    assert "apply-approved" in reply
    plan = load_pending_plan(tmp_path)
    assert plan["operations"][0]["team_decision"] == "approve"

    save_pending_plan(
        tmp_path,
        {"source": "idle", "summary": "op"},
        [
            {
                "kind": "remove_unused_import",
                "target_file": "a.py",
                "critic_verdict": "allow",
            }
        ],
        [],
        notify_telegram=False,
    )
    answered: list[str] = []
    sent: list[str] = []

    def fake_api(_tok: str, method: str, params=None, **_k):
        if method == "answerCallbackQuery":
            answered.append(str(params.get("text") or ""))
            return {}
        if method == "sendMessage":
            sent.append(str(params.get("text") or ""))
            return {"message_id": 1}
        return {}

    process_updates(
        tmp_path,
        [
            {
                "update_id": 9,
                "callback_query": {
                    "id": "cq1",
                    "data": "eurika:reject",
                    "message": {"chat": {"id": 42}},
                },
            }
        ],
        token="tok",
        allowed_chat_ids={42},
        api=fake_api,
    )
    assert answered and "reject" in answered[0].lower()
    assert sent and "reject" in sent[0].lower()
    plan3 = load_pending_plan(tmp_path)
    assert plan3["operations"][0]["team_decision"] == "reject"


def test_notify_apply_result_sends_and_dedupes(tmp_path: Path, monkeypatch) -> None:
    from eurika.integrations.telegram_bot import notify_apply_result

    monkeypatch.setenv("EURIKA_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("EURIKA_TELEGRAM_CHAT_IDS", "11")
    monkeypatch.delenv("EURIKA_TELEGRAM_ALLOW_ANY", raising=False)
    monkeypatch.delenv("EURIKA_TELEGRAM_NOTIFY_APPROVALS", raising=False)

    sent: list[str] = []

    def fake_api(_token: str, method: str, params=None, **_k):
        assert method == "sendMessage"
        sent.append(str(params["text"]))
        return {"message_id": 1}

    out = notify_apply_result(
        tmp_path,
        text="apply-approved (exit 0)\n\nverify ok",
        ok=True,
        exit_code=0,
        run_id="run_a",
        modified=["eurika/polygon/imports_ok.py"],
        api=fake_api,
    )
    assert out.get("skipped") is None
    assert out.get("sent") == 1
    assert "apply-approved" in sent[0]
    assert "imports_ok.py" in sent[0] or "verify" in sent[0].lower()

    again = notify_apply_result(
        tmp_path,
        text="apply-approved (exit 0)\n\nverify ok",
        ok=True,
        exit_code=0,
        run_id="run_a",
        modified=["eurika/polygon/imports_ok.py"],
        api=fake_api,
    )
    assert again.get("skipped") == "already_notified"
    assert again.get("sent") == 0
