"""Tests for eurika.api.serve transport-level request validation."""

import io
from pathlib import Path

from eurika.api import serve as api_serve


class _DummyHandler:
    """Minimal handler stub for _json_response monkeypatching tests."""


class _BodyHandler:
    """Minimal handler stub for _read_json_body tests."""

    def __init__(self, body: bytes, content_length: str | int) -> None:
        self.rfile = io.BytesIO(body)
        self.headers = {"Content-Length": str(content_length)}


def test_dispatch_api_get_summary_returns_dict(tmp_path: Path, monkeypatch) -> None:
    """GET /api/summary should return dict with system or error (CR-B1 Skill example)."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(_DummyHandler(), tmp_path, "/api/summary", {})
    assert handled is True
    assert captured.get("status") == 200
    data = captured.get("data") or {}
    assert "path" in data or "system" in data or "error" in data


def test_dispatch_api_get_pattern_library_missing(tmp_path: Path, monkeypatch) -> None:
    """GET /api/pattern_library returns exists=False when no pattern library."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(_DummyHandler(), tmp_path, "/api/pattern_library", {})
    assert handled is True
    assert captured.get("status") == 200
    data = captured.get("data") or {}
    assert data.get("exists") is False
    assert "hint" in data


def test_dispatch_api_get_pattern_library_with_data(tmp_path: Path, monkeypatch) -> None:
    """GET /api/pattern_library returns counts when .eurika/pattern_library.json exists."""
    (tmp_path / ".eurika").mkdir(parents=True, exist_ok=True)
    lib = {
        "long_function": [{"project": "starlette", "module": "a.py", "location": "foo", "hint": "Extract"}],
        "deep_nesting": [],
    }
    (tmp_path / ".eurika" / "pattern_library.json").write_text(
        __import__("json").dumps(lib, ensure_ascii=False),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(_DummyHandler(), tmp_path, "/api/pattern_library", {})
    assert handled is True
    data = captured.get("data") or {}
    assert data.get("exists") is True
    assert data.get("counts", {}).get("long_function") == 1
    assert "starlette" in (data.get("projects") or [])


def test_dispatch_api_get_self_guard_returns_dict(tmp_path: Path, monkeypatch) -> None:
    """GET /api/self_guard should return dict with forbidden_count, layer_viol_count, pass (CR-B1)."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(_DummyHandler(), tmp_path, "/api/self_guard", {})
    assert handled is True
    assert captured.get("status") == 200
    data = captured.get("data") or {}
    assert "forbidden_count" in data
    assert "layer_viol_count" in data
    assert "pass" in data


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


def test_dispatch_api_get_history_returns_dict(tmp_path: Path, monkeypatch) -> None:
    """GET /api/history should return dict (CR-B1)."""
    captured: dict[str, object] = {}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve._dispatch_api_get(_DummyHandler(), tmp_path, "/api/history", {})
    assert handled is True
    assert captured.get("status") == 200
    data = captured.get("data") or {}
    assert isinstance(data, dict)


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
