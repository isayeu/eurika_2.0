from types import SimpleNamespace

from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter
from qt_app.ui.agent_pending import (
    approval_button_label,
    approval_details,
    first_pending_hitl_call,
    first_side_effect_call,
    format_proposal_preview,
    wants_local_agent,
    with_approval,
)
from qt_app.ui.handlers import agent_hitl_handlers


def test_wants_local_agent_for_implement_not_greeting() -> None:
    assert wants_local_agent("IMPLEMENT: split chat_handlers")
    assert wants_local_agent("добавь тест на git HITL")
    assert wants_local_agent(
        "Мне не нравится как выглядит вкладка Models/LLM, слишком много свободного места справа, "
        "но при этом приходится прокручивать вниз. Сделай более эргономичной."
    )
    assert wants_local_agent(
        "когда нажимаю на воркспейс рут поднимается вверх, фиксированно на местах"
    )
    assert not wants_local_agent("привет")
    assert not wants_local_agent("применяй")
    assert not wants_local_agent("собери коммит")


def test_first_side_effect_call_prefers_git() -> None:
    calls = [
        {"tool": "edit", "callId": "e1", "proposal": {"proposalId": "p"}},
        {"tool": "git_commit", "callId": "c1", "arguments": {"message": "hitl", "paths": ["a.py"]}},
    ]
    found = first_side_effect_call(calls)
    assert found is not None
    assert found["tool"] == "git_commit"
    assert approval_button_label("git_commit") == "Commit"
    assert approval_button_label("git_push") == "Push"
    details = approval_details(found)
    assert "hitl" in details
    assert "a.py" in details
    assert "Never --force" in approval_details({"tool": "git_push", "arguments": {}})
    assert with_approval({"message": "x"})["approval"] is True


def test_first_edit_proposal_and_preview() -> None:
    calls = [
        {
            "tool": "edit",
            "callId": "e1",
            "proposal": {
                "proposalId": "p1",
                "files": [{"path": "qt_app/ui/agent_pending.py", "created": False}],
            },
        }
    ]
    found = first_pending_hitl_call(calls)
    assert found is not None
    assert found["tool"] == "edit"
    preview = format_proposal_preview(
        [{"path": "a.py", "created": True, "after": "print(1)\n"}]
    )
    assert "a.py" in preview
    assert "created" in preview
    assert "print(1)" in preview


def test_chat_send_routes_models_layout_to_agent_chat(monkeypatch) -> None:
    api = EurikaApiAdapter(".")
    captured = {}

    def _fake_agent(message, *, session_id=None):
        captured["message"] = message
        return {
            "ok": True,
            "text": "Prepared an edit proposal for Models/LLM layout.",
            "pendingToolCalls": [
                {
                    "tool": "edit",
                    "callId": "e1",
                    "proposal": {"proposalId": "p1", "files": [{"path": "qt_app/ui/tabs/models_tab.py"}]},
                }
            ],
            "sessionId": "sess-layout",
        }

    monkeypatch.setattr(api, "agent_chat", _fake_agent)
    msg = (
        "Мне не нравится как выглядит вкладка Models/LLM, слишком много свободного места справа, "
        "но при этом приходится прокручивать вниз. Сделай более эргономичной."
    )
    out = api.chat_send(message=msg, history=[])
    assert captured["message"] == msg
    assert out["pendingToolCalls"][0]["tool"] == "edit"


def test_chat_send_routes_implement_to_agent_chat(monkeypatch) -> None:
    api = EurikaApiAdapter(".")
    captured = {}

    def _fake_agent(message, *, session_id=None):
        captured["message"] = message
        return {
            "ok": True,
            "text": "Prepared tool action(s) for your review.",
            "pendingToolCalls": [
                {"tool": "git_commit", "callId": "1", "arguments": {"message": "x", "paths": []}}
            ],
            "sessionId": "sess-1",
        }

    monkeypatch.setattr(api, "agent_chat", _fake_agent)
    out = api.chat_send(message="IMPLEMENT: commit note.txt", history=[])
    assert captured["message"] == "IMPLEMENT: commit note.txt"
    assert out["pendingToolCalls"][0]["tool"] == "git_commit"


def test_chat_send_greeting_stays_on_core_chat(monkeypatch) -> None:
    import qt_app.adapters.eurika_api_adapter as adapter_mod

    api = EurikaApiAdapter(".")
    captured = {}

    def _fake_chat(_root, message, _history, **kwargs):
        captured["message"] = message
        return {"text": "привет", "error": None}

    monkeypatch.setattr(adapter_mod, "_chat_send", _fake_chat)
    out = api.chat_send(message="привет", history=[])
    assert captured["message"] == "привет"
    assert out["text"] == "привет"


def test_chat_send_local_agent_missing_http_fails_loud(monkeypatch) -> None:
    import qt_app.adapters.eurika_api_adapter as adapter_mod

    api = EurikaApiAdapter(".")
    core_calls: list[str] = []

    def _boom(_message, *, session_id=None):
        raise FileNotFoundError(".eurika/agent_http.json")

    def _fake_chat(_root, message, _history, **kwargs):
        core_calls.append(message)
        return {"text": "should not run", "error": None}

    monkeypatch.setattr(api, "agent_chat", _boom)
    monkeypatch.setattr(adapter_mod, "_chat_send", _fake_chat)
    out = api.chat_send(message="IMPLEMENT: split handlers", history=[])
    assert out["ok"] is False
    assert "agent HTTP" in out["error"]
    assert core_calls == []
    assert out["pendingToolCalls"] == []


def test_maybe_focus_approvals_after_agent_queues_timer(monkeypatch) -> None:
    from qt_app.ui.handlers import chat_handlers

    scheduled: list = []

    class _Tabs:
        def __init__(self) -> None:
            self.index = -1

        def setCurrentIndex(self, index: int) -> None:
            self.index = index

    main = SimpleNamespace(
        approvals_tab_index=3,
        tabs=_Tabs(),
        _api=SimpleNamespace(
            get_pending_plan=lambda: {
                "operations": [{"kind": "agent_edit", "target_file": "a.py"}]
            }
        ),
    )
    loaded: list[str] = []

    monkeypatch.setattr(
        chat_handlers.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.approve_handlers.load_pending_plan",
        lambda m: loaded.append("yes"),
    )
    chat_handlers.maybe_focus_approvals_after_agent(
        main, {"approvalsQueued": 2, "text": "queued"}
    )
    assert len(scheduled) == 1
    scheduled[0]()
    assert main.tabs.index == 3
    assert loaded == ["yes"]
    chat_handlers.maybe_focus_approvals_after_agent(main, {"approvalsQueued": 0})
    assert len(scheduled) == 1


def test_paint_pending_unlocks_commit_button() -> None:
    apply_btn = SimpleNamespace(text="Apply", enabled=False, tooltip="")
    reject_btn = SimpleNamespace(enabled=False, tooltip="")
    pending_label = SimpleNamespace(text="", tooltip="")
    diff_btn = SimpleNamespace(enabled=False, tooltip="")
    diff_view = SimpleNamespace(text="")

    apply_btn.setText = lambda value: setattr(apply_btn, "text", value)
    apply_btn.setEnabled = lambda value: setattr(apply_btn, "enabled", value)
    apply_btn.setToolTip = lambda value: setattr(apply_btn, "tooltip", value)
    reject_btn.setEnabled = lambda value: setattr(reject_btn, "enabled", value)
    reject_btn.setToolTip = lambda value: setattr(reject_btn, "tooltip", value)
    pending_label.setText = lambda value: setattr(pending_label, "text", value)
    pending_label.setToolTip = lambda value: setattr(pending_label, "tooltip", value)
    diff_btn.setEnabled = lambda value: setattr(diff_btn, "enabled", value)
    diff_btn.setToolTip = lambda value: setattr(diff_btn, "tooltip", value)
    diff_view.setPlainText = lambda value: setattr(diff_view, "text", value)

    main = SimpleNamespace(
        _agent_pending_call={
            "tool": "git_commit",
            "callId": "c1",
            "arguments": {"message": "hitl", "paths": ["a.py"]},
        },
        chat_apply_btn=apply_btn,
        chat_reject_btn=reject_btn,
        chat_pending_label=pending_label,
        chat_diff_btn=diff_btn,
        chat_diff_view=diff_view,
    )
    assert agent_hitl_handlers.paint_pending(main) is True
    assert apply_btn.text == "Commit"
    assert apply_btn.enabled is True
    assert reject_btn.enabled is True
    assert "hitl" in diff_view.text


def test_paint_pending_edit_uses_hydrated_preview() -> None:
    apply_btn = SimpleNamespace(text="Apply", enabled=False, tooltip="")
    reject_btn = SimpleNamespace(enabled=False, tooltip="")
    pending_label = SimpleNamespace(text="", tooltip="")
    diff_btn = SimpleNamespace(enabled=False, tooltip="")
    diff_view = SimpleNamespace(text="")
    apply_btn.setText = lambda value: setattr(apply_btn, "text", value)
    apply_btn.setEnabled = lambda value: setattr(apply_btn, "enabled", value)
    apply_btn.setToolTip = lambda value: setattr(apply_btn, "tooltip", value)
    reject_btn.setEnabled = lambda value: setattr(reject_btn, "enabled", value)
    reject_btn.setToolTip = lambda value: setattr(reject_btn, "tooltip", value)
    pending_label.setText = lambda value: setattr(pending_label, "text", value)
    pending_label.setToolTip = lambda value: setattr(pending_label, "tooltip", value)
    diff_btn.setEnabled = lambda value: setattr(diff_btn, "enabled", value)
    diff_btn.setToolTip = lambda value: setattr(diff_btn, "tooltip", value)
    diff_view.setPlainText = lambda value: setattr(diff_view, "text", value)

    class _Api:
        def agent_get_proposal(self, proposal_id: str, path: str | None = None):
            assert proposal_id == "p1"
            return {
                "files": [
                    {"path": "note.txt", "created": True, "after": "hello\n"},
                ]
            }

    main = SimpleNamespace(
        _agent_pending_call={
            "tool": "edit",
            "callId": "e1",
            "proposal": {"proposalId": "p1", "files": [{"path": "note.txt"}]},
        },
        _api=_Api(),
        chat_apply_btn=apply_btn,
        chat_reject_btn=reject_btn,
        chat_pending_label=pending_label,
        chat_diff_btn=diff_btn,
        chat_diff_view=diff_view,
    )
    assert agent_hitl_handlers.paint_pending(main) is True
    assert apply_btn.text == "Apply"
    assert apply_btn.enabled is True
    assert "hello" in diff_view.text
    assert "note.txt" in diff_view.text


def test_agent_decide_proposal_applies_then_continues(monkeypatch) -> None:
    api = EurikaApiAdapter(".")
    api._agent_session_id = "sess-1"
    calls = []

    class _Client:
        def rpc(self, method, params=None, request_id=1, *, timeout=None):
            calls.append((method, params))
            if method == "proposal/apply":
                return {"result": {"applied": ["note.txt"], "remaining": []}}
            return {"result": {"text": "applied", "pendingToolCalls": [], "sessionId": "sess-1"}}

    def _discover(cls, workspace="."):
        return _Client()

    monkeypatch.setattr(
        "eurika.agent.http_client.AgentHttpClient.discover",
        classmethod(_discover),
    )
    out = api.agent_decide_proposal(
        {
            "tool": "edit",
            "callId": "e1",
            "proposal": {"proposalId": "p1", "files": [{"path": "note.txt"}]},
        },
        approved=True,
    )
    assert calls[0][0] == "proposal/apply"
    assert calls[0][1]["approval"] is True
    assert calls[1][0] == "session/chat"
    assert out["text"] == "applied"
    assert out["ok"] is True


def test_agent_continue_payload_surfaces_rpc_error() -> None:
    api = EurikaApiAdapter(".")
    api._agent_session_id = "sess-err"
    out = api._agent_continue_payload(
        {"error": {"code": -32602, "message": "Every edit requires a workspace-relative path"}}
    )
    assert out["ok"] is False
    assert "workspace-relative path" in out["error"]
    assert out["pendingToolCalls"] == []


def test_agent_chat_sends_review_in_approvals_context(monkeypatch) -> None:
    captured: dict = {}

    class _FakeClient:
        @classmethod
        def discover(cls, _root):
            return cls()

        def post(self, path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return {
                "sessionId": "s1",
                "text": "queued",
                "pendingToolCalls": [],
                "approvalsQueued": 2,
            }

    monkeypatch.setattr("eurika.agent.http_client.AgentHttpClient", _FakeClient)
    api = EurikaApiAdapter(".")
    out = api.agent_chat("сделай вкладку эргономичнее")
    assert captured["path"] == "/chat"
    assert captured["payload"]["context"]["reviewInApprovals"] is True
    assert captured["payload"]["context"]["client"] == "qt"
    assert out["approvalsQueued"] == 2


def test_persist_table_decisions_writes_approve() -> None:
    from qt_app.ui.handlers.approve_handlers import (
        collect_approval_payload,
        persist_table_decisions,
    )

    saved: list = []

    class _Combo:
        def currentText(self) -> str:
            return "approve"

    class _Table:
        def cellWidget(self, _row: int, _col: int) -> _Combo:
            return _Combo()

    class _Api:
        def save_approvals(self, operations: list) -> dict:
            saved.append(operations)
            return {"ok": True, "saved": len(operations), "approved": 1}

    main = SimpleNamespace(
        _pending_operations=[{"target_file": "a.py", "kind": "agent_edit"}],
        approvals_table=_Table(),
        _api=_Api(),
    )
    payload = collect_approval_payload(main)
    assert payload[0]["team_decision"] == "approve"
    result = persist_table_decisions(main)
    assert result["approved"] == 1
    assert saved[0][0]["team_decision"] == "approve"


def test_run_apply_approved_persists_before_cli(monkeypatch) -> None:
    from qt_app.ui.handlers import command_handlers

    persisted: list[str] = []

    class _Tabs:
        def indexOf(self, _tab: object) -> int:
            return 0

        def setCurrentIndex(self, _index: int) -> None:
            return None

    main = SimpleNamespace(
        root_edit=SimpleNamespace(text=lambda: "/tmp/proj"),
        _pending_operations=[{"target_file": "a.py", "kind": "agent_edit"}],
        tabs=_Tabs(),
        commands_tab=object(),
        _command_service=SimpleNamespace(run_apply_approved=lambda **_kw: persisted.append("cli")),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.command_handlers.validate_project_root",
        lambda _root: (True, ""),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.approve_handlers.persist_table_decisions",
        lambda _main: persisted.append("save") or {"ok": True, "saved": 1, "approved": 1},
    )
    command_handlers.run_apply_approved(main)
    assert persisted == ["save", "cli"]
    assert main._pending_operations
