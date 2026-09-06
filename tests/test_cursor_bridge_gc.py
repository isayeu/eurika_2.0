"""Tests for Cursor SDK bridge GC (orphan prune + shutdown)."""

from __future__ import annotations

from eurika.agent import cursor_bridge_gc as gc


def test_shutdown_cursor_sdk_without_import_crash() -> None:
    out = gc.shutdown_cursor_sdk()
    assert "ok" in out


def test_has_live_owner_detects_eurika() -> None:
    assert gc._has_live_owner([(1, "/mnt/storage/project/venv/bin/eurika-qt")]) is True
    assert gc._has_live_owner([(1, "python -m eurika_cli telegram-bot /tmp")]) is True
    assert gc._has_live_owner([(1, "lxqt-session")]) is False
    # site-packages path contains "python3.14" but is not a live owner
    assert (
        gc._has_live_owner(
            [
                (
                    1,
                    "sh /mnt/storage/project/venv/lib/python3.14/site-packages/"
                    "cursor_sdk/_vendor/bridge/bin/cursor-sdk-bridge",
                )
            ]
        )
        is False
    )

def test_callback_port_parse() -> None:
    parts = [
        "node",
        "cursor-sdk-bridge.js",
        "--workspace",
        "/tmp/ws",
        "--tool-callback-url",
        "http://127.0.0.1:38437/",
    ]
    assert gc._workspace_from_cmdline(parts) == "/tmp/ws"
    assert gc._callback_port(parts) == 38437


def test_prune_dry_run_shape() -> None:
    out = gc.prune_orphan_cursor_bridges(dry_run=True, only_dead_callback=True)
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert "killed" in out
    assert "skipped" in out
