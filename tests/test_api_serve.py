"""Tests for eurika.api.serve transport-level request validation."""

import io
from pathlib import Path

import pytest

from eurika.api import serve as api_serve


class _DummyHandler:
    """Minimal handler stub for _json_response monkeypatching tests."""


class _BodyHandler:
    """Minimal handler stub for _read_json_body tests."""

    def __init__(self, body: bytes, content_length: str | int) -> None:
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(content_length)}


def test_run_post_handler_approve_rejects_non_list_operations(tmp_path: Path, monkeypatch) -> None:
    """POST /api/approve should return 400 when operations is not a list."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/approve",
        {"operations": "bad"},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid operations payload"


def test_run_post_handler_approve_rejects_non_dict_operation_items(tmp_path: Path, monkeypatch) -> None:
    """POST /api/approve should return 400 when operations contains non-object items."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/approve",
        {"operations": ["bad"]},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid operations payload"


def test_run_post_handler_exec_rejects_non_string_command(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should return 400 when command is not a string."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": 123},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid command payload"


def test_run_post_handler_exec_rejects_invalid_timeout(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should return 400 when timeout cannot be parsed as integer."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": "not-a-number"},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid timeout payload"


def test_run_post_handler_exec_rejects_non_positive_timeout(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should return 400 when timeout is out of allowed range."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": 0},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid timeout range"


def test_run_post_handler_exec_rejects_too_large_timeout(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should return 400 when timeout exceeds allowed max."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": 100000},
    )

    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid timeout range"


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"operations": None},
        {"operations": "bad"},
        {"operations": ["bad"]},
        {"operations": [1, 2]},
    ],
)
def test_run_post_handler_approve_malformed_payloads_return_400(tmp_path: Path, monkeypatch, body) -> None:
    """POST /api/approve should consistently reject malformed payload variants."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/approve",
        body,
    )

    assert handled is True
    assert captured.get("status") == 400
    assert "error" in (captured.get("data") or {})


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"command": None},
        {"command": 123},
        {"command": "eurika scan .", "timeout": "oops"},
        {"command": "eurika scan .", "timeout": 0},
        {"command": "eurika scan .", "timeout": 100000},
    ],
)
def test_run_post_handler_exec_malformed_payloads_return_400(tmp_path: Path, monkeypatch, body) -> None:
    """POST /api/exec should consistently reject malformed payload variants."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        body,
    )

    assert handled is True
    assert captured.get("status") == 400
    assert "error" in (captured.get("data") or {})


def test_run_post_handler_chat_rejects_non_string_message(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should return 400 when message is not string."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": 123},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid message payload"


def test_run_post_handler_chat_rejects_invalid_history_shape(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should return 400 when history has invalid structure."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": "hi", "history": [{"role": "user", "content": 1}]},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid history payload"


def test_run_post_handler_chat_passes_normalized_payload_to_chat_send(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should pass validated message/history to chat_send."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_chat_send(project_root, message, history=None):
        called["project_root"] = project_root
        called["message"] = message
        called["history"] = history
        return {"text": "ok", "error": None}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "chat_send", _fake_chat_send)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": "hello", "history": [{"role": "user", "content": "x"}]},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert (captured.get("data") or {}).get("text") == "ok"
    assert called.get("message") == "hello"
    assert called.get("history") == [{"role": "user", "content": "x"}]


def test_run_post_handler_exec_accepts_timeout_min_boundary(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should accept minimum timeout boundary."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_exec(project_root, command, timeout=120):
        called["project_root"] = project_root
        called["command"] = command
        called["timeout"] = timeout
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "_exec_eurika_command", _fake_exec)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": api_serve.EXEC_TIMEOUT_MIN},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("timeout") == api_serve.EXEC_TIMEOUT_MIN


def test_run_post_handler_exec_accepts_timeout_max_boundary(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should accept maximum timeout boundary."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_exec(_project_root, _command, timeout=120):
        called["timeout"] = timeout
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "_exec_eurika_command", _fake_exec)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": api_serve.EXEC_TIMEOUT_MAX},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("timeout") == api_serve.EXEC_TIMEOUT_MAX


def test_run_post_handler_exec_accepts_unlimited_timeout_null(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should accept timeout=null as unlimited."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_exec(_project_root, _command, timeout=120):
        called["timeout"] = timeout
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "_exec_eurika_command", _fake_exec)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika scan .", "timeout": None},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("timeout") is None


def test_run_post_handler_exec_ignores_extra_payload_fields(tmp_path: Path, monkeypatch) -> None:
    """POST /api/exec should ignore unknown fields and still run."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_exec(_project_root, command, timeout=120):
        called["command"] = command
        called["timeout"] = timeout
        return {"stdout": "ok", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "_exec_eurika_command", _fake_exec)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/exec",
        {"command": "eurika doctor .", "timeout": 10, "unexpected": {"a": 1}},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("command") == "eurika doctor ."
    assert called.get("timeout") == 10


def test_run_post_handler_chat_allows_empty_message_passthrough(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should pass empty message to chat layer without transport 400."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_chat_send(_project_root, message, history=None):
        called["message"] = message
        called["history"] = history
        return {"text": "", "error": "message is empty"}

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(api_serve, "chat_send", _fake_chat_send)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": ""},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("message") == ""
    assert (captured.get("data") or {}).get("error") == "message is empty"


def test_run_post_handler_chat_rejects_history_non_list(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should reject non-list history payload."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": "hi", "history": "bad"},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid history payload"


def test_run_post_handler_chat_rejects_history_non_dict_item(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should reject history arrays with non-object entries."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": "hi", "history": [1]},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid history payload"


def test_run_post_handler_chat_rejects_history_non_string_role(tmp_path: Path, monkeypatch) -> None:
    """POST /api/chat should reject history where role is not string."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/chat",
        {"message": "hi", "history": [{"role": 1, "content": "x"}]},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid history payload"


def test_run_post_handler_ask_architect_passes_no_llm_value(tmp_path: Path, monkeypatch) -> None:
    """POST /api/ask_architect should pass no_llm value through to doctor cycle."""
    captured: dict[str, object] = {}
    called: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    def _fake_run_doctor_cycle(project_root, window=5, no_llm=False):
        called["project_root"] = project_root
        called["window"] = window
        called["no_llm"] = no_llm
        return {"architect_text": "ok"}

    import cli.orchestration.doctor as doctor_mod

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    monkeypatch.setattr(doctor_mod, "run_doctor_cycle", _fake_run_doctor_cycle)
    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/ask_architect",
        {"no_llm": "yes"},
    )
    assert handled is True
    assert captured.get("status") == 200
    assert called.get("no_llm") is True
    assert (captured.get("data") or {}).get("text") == "ok"


def test_dispatch_api_get_file_rejects_empty_path(tmp_path: Path, monkeypatch) -> None:
    """GET /api/file should return 400 when path query value is empty."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(
        _DummyHandler(),
        tmp_path,
        "/api/file",
        {"path": [""]},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid path"


def test_run_post_handler_ask_architect_rejects_invalid_no_llm_payload(tmp_path: Path, monkeypatch) -> None:
    """POST /api/ask_architect should return 400 when no_llm cannot be parsed to boolean."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)

    handled = api_serve._run_post_handler(
        _DummyHandler(),
        tmp_path,
        "/api/ask_architect",
        {"no_llm": {"bad": "value"}},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid no_llm payload"


def test_dispatch_api_get_file_rejects_traversal_like_path(tmp_path: Path, monkeypatch) -> None:
    """GET /api/file should reject traversal-like relative path."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(
        _DummyHandler(),
        tmp_path,
        "/api/file",
        {"path": ["a/../b.py"]},
    )
    assert handled is True
    assert captured.get("status") == 400
    assert (captured.get("data") or {}).get("error") == "invalid path"


def test_read_json_body_returns_parsed_dict_on_valid_json() -> None:
    """_read_json_body should parse valid JSON body."""
    handler = _BodyHandler(b'{"a": 1}', "8")
    out = api_serve._read_json_body(handler)
    assert out == {"a": 1}


def test_read_json_body_returns_none_on_invalid_json() -> None:
    """_read_json_body should return None on malformed JSON."""
    handler = _BodyHandler(b"{not json", "9")
    out = api_serve._read_json_body(handler)
    assert out is None


def test_normalize_exec_args_explain_requires_module(tmp_path: Path) -> None:
    """explain command must include module positional argument."""
    args, err = api_serve._normalize_exec_args_for_subcommand(tmp_path, "explain", [])
    assert args is None
    assert err is not None
    assert "requires module positional" in err


def test_normalize_exec_args_rejects_unknown_flag_for_subcommand(tmp_path: Path) -> None:
    """Unknown flag for subcommand should be rejected with explicit hint."""
    args, err = api_serve._normalize_exec_args_for_subcommand(
        tmp_path,
        "scan",
        ["--runtime-mode", "hybrid"],
    )
    assert args is None
    assert err is not None
    assert "flag not allowed for 'scan'" in err


def test_normalize_exec_args_allows_explain_module_and_window(tmp_path: Path) -> None:
    """explain should keep module and allow --window value."""
    args, err = api_serve._normalize_exec_args_for_subcommand(
        tmp_path,
        "explain",
        ["eurika/api/serve.py", "--window", "7"],
    )
    assert err is None
    assert args is not None
    assert args[0] == "eurika/api/serve.py"
    assert args[1] == str(tmp_path)
    assert "--window" in args
    assert "7" in args


def test_resolve_project_root_override_accepts_absolute_existing_dir(tmp_path: Path) -> None:
    """project_root override should accept existing absolute directory."""
    out, err = api_serve._resolve_project_root_override(tmp_path, str(tmp_path))
    assert err is None
    assert out == tmp_path.resolve()


def test_resolve_project_root_override_resolves_relative_path(tmp_path: Path) -> None:
    """Relative project_root should be resolved against server root."""
    child = tmp_path / "child"
    child.mkdir(parents=True, exist_ok=True)
    out, err = api_serve._resolve_project_root_override(tmp_path, "child")
    assert err is None
    assert out == child.resolve()


def test_resolve_project_root_override_rejects_non_string_payload(tmp_path: Path) -> None:
    """Non-string project_root payload should be rejected."""
    out, err = api_serve._resolve_project_root_override(tmp_path, {"bad": 1})
    assert out is None
    assert err is not None
    assert "expected string" in err


def test_resolve_project_root_override_rejects_missing_directory(tmp_path: Path) -> None:
    """Missing project_root path should return explicit validation error."""
    out, err = api_serve._resolve_project_root_override(tmp_path, str(tmp_path / "missing"))
    assert out is None
    assert err is not None
    assert "not found" in err
