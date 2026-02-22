"""Tests for eurika.api.serve transport-level request validation."""

from pathlib import Path

import pytest

from eurika.api import serve as api_serve


class _DummyHandler:
    """Minimal handler stub for _json_response monkeypatching tests."""


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
