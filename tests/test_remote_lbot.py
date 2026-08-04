"""Tests for remote lbot SSH status probe (mocked ssh)."""

from __future__ import annotations

import json

import pytest

from eurika.integrations import remote_lbot as rl


def test_probe_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_LBOT_PROBE", "0")
    out = rl.probe_remote_lbot()
    assert out["skipped"] is True
    assert out["ok"] is False


def test_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_LBOT_PROBE", "1")
    monkeypatch.setenv("EURIKA_LBOT_SSH_HOST", "prodg")
    payload = {
        "ok": True,
        "remote_dir": "/home/andrei/lbot",
        "dir_exists": True,
        "hostname": "qboexstiil",
        "running": True,
        "processes": [{"pid": 42, "cmdline": "python main.py"}],
        "tmux_sessions": ["0"],
        "open_trades": 2,
        "trades": [
            {"symbol": "BTCUSDT", "mode": "live", "roi": 1.2, "pnl": 0.01, "open": True},
            {"symbol": "ETHUSDT", "mode": "live", "roi": -0.5, "pnl": -0.001, "open": True},
        ],
        "log": {"size_bytes": 100, "age_sec": 3, "tail": ["tick ok"]},
        "error": None,
    }

    def fake_ssh(host: str, script: str, *, timeout: float):
        assert host == "prodg"
        assert "REMOTE_DIR" in script
        return 0, json.dumps(payload) + "\n", ""

    out = rl.probe_remote_lbot(ssh_run=fake_ssh)
    assert out["ok"] is True
    assert out["running"] is True
    assert out["open_trades"] == 2
    assert out["hostname"] == "qboexstiil"
    blob = json.dumps(out)
    assert "api_key" not in blob.lower()


def test_probe_ssh_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_LBOT_PROBE", "1")

    def fake_ssh(host: str, script: str, *, timeout: float):
        return 255, "", "Permission denied (publickey)."

    out = rl.probe_remote_lbot(ssh_run=fake_ssh)
    assert out["ok"] is False
    assert "Permission denied" in (out.get("error") or "")


def test_format_block_contains_note() -> None:
    text = rl.format_remote_lbot_block(
        {
            "ok": True,
            "host": "prodg",
            "remote_dir": "~/lbot",
            "hostname": "qboexstiil",
            "latency_ms": 12.3,
            "running": True,
            "processes": [{"pid": 1, "cmdline": "python main.py"}],
            "tmux_sessions": ["0"],
            "open_trades": 1,
            "trades": [{"symbol": "AAA", "mode": "live", "roi": 0, "pnl": 0}],
            "log": {"size_bytes": 10, "age_sec": 1, "tail": ["hello"]},
        }
    )
    assert "LBOT (remote read-only)" in text
    assert "open_trades: 1" in text
    assert "no start/stop/orders" in text


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EURIKA_LBOT_SSH_HOST", raising=False)
    monkeypatch.delenv("EURIKA_LBOT_REMOTE_DIR", raising=False)
    monkeypatch.delenv("EURIKA_LBOT_PROBE", raising=False)
    cfg = rl.lbot_ssh_config()
    assert cfg["host"] == "prodg"
    assert cfg["remote_dir"] == "~/lbot"
    assert cfg["enabled"] is True
