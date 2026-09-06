"""Cursor SDK bridge lifecycle: close client cleanly + prune orphan node bridges.

``Agent.prompt`` closes the agent, but the Node ``cursor-sdk-bridge`` lives on the
process-wide default ``Client``. Eurika Qt exits via ``os._exit`` (skips atexit),
and killed telegram/Qt parents leave bridges reparented under the desktop session
(~100–250 MiB RSS each). This module shuts the SDK client down on purpose and
can SIGTERM orphan bridge trees whose Python owner is gone.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from typing import Any


def shutdown_cursor_sdk() -> dict[str, Any]:
    """Close the process-wide Cursor SDK default client + owned bridge."""
    try:
        from cursor_sdk._client import close_default_client
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        close_default_client()
        return {"ok": True, "closed": True}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [p.decode(errors="replace") for p in raw.split(b"\0") if p]


def _ppid(pid: int) -> int | None:
    try:
        parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace").split()
        return int(parts[3])
    except (OSError, IndexError, ValueError):
        return None


def _ancestors(pid: int, *, limit: int = 8) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    cur = _ppid(pid)
    for _ in range(limit):
        if cur is None or cur <= 1:
            if cur is not None:
                out.append((cur, "init"))
            break
        cmd = " ".join(_cmdline(cur)) or f"pid:{cur}"
        out.append((cur, cmd[:160]))
        cur = _ppid(cur)
    return out


def _workspace_from_cmdline(parts: list[str]) -> str:
    for i, p in enumerate(parts):
        if p == "--workspace" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _callback_port(parts: list[str]) -> int | None:
    for i, p in enumerate(parts):
        if p == "--tool-callback-url" and i + 1 < len(parts):
            url = parts[i + 1]
            # http://127.0.0.1:38437/
            try:
                hostport = url.split("//", 1)[1].split("/", 1)[0]
                return int(hostport.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                return None
    return None


def _port_has_listener(port: int | None) -> bool:
    if not port:
        return False
    try:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.15)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def _has_live_owner(ancestors: list[tuple[int, str]]) -> bool:
    """True when a still-running Eurika/Cursor Python/Electron owns the bridge."""
    for _pid, cmd in ancestors:
        low = cmd.lower()
        # Match argv0 / known launchers — not substrings inside site-packages paths
        # like ``.../lib/python3.14/site-packages/cursor_sdk/...``.
        tokens = low.replace("\\", "/").split()
        argv0 = tokens[0] if tokens else ""
        base = argv0.rsplit("/", 1)[-1]
        if base in {"eurika-qt", "eurika_cli"} or argv0.endswith("/eurika-qt"):
            return True
        if "telegram-bot" in low and ("python" in base or base.startswith("python")):
            return True
        if base.startswith("python") and ("eurika" in low or "qt_app" in low):
            return True
        if "cursor.mjs" in low or "/usr/share/cursor/" in low:
            return True
        if base == "electron" and "cursor" in low:
            return True
    return False


def list_cursor_bridges() -> list[dict[str, Any]]:
    """Snapshot running ``cursor-sdk-bridge.js`` processes."""
    import subprocess

    try:
        out = subprocess.check_output(["pgrep", "-f", "cursor-sdk-bridge.js"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    rows: list[dict[str, Any]] = []
    for line in out.split():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        parts = _cmdline(pid)
        if not any("cursor-sdk-bridge.js" in p for p in parts):
            continue
        anc = _ancestors(pid)
        port = _callback_port(parts)
        live = _has_live_owner(anc)
        cb_alive = _port_has_listener(port)
        # Dead tool-callback port ⇒ Python client gone even if PPID was reparented.
        orphan = (not live) or (not cb_alive)
        rows.append(
            {
                "pid": pid,
                "workspace": _workspace_from_cmdline(parts),
                "callback_port": port,
                "callback_alive": cb_alive,
                "live_owner": live,
                "orphan": orphan,
                "ancestors": [{"pid": a, "cmd": c} for a, c in anc[:4]],
            }
        )
    return rows


def prune_orphan_cursor_bridges(
    *,
    workspace: str | Path | None = None,
    only_dead_callback: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """SIGTERM orphan bridges (no live Eurika/Cursor owner / dead callback).

    By default only kills when the tool-callback port is no longer listening —
    safe for leftover bridges after ``os._exit`` / kill -9.
    """
    want = str(Path(workspace).resolve()) if workspace else None
    killed: list[int] = []
    skipped: list[dict[str, Any]] = []
    for row in list_cursor_bridges():
        ws = str(row.get("workspace") or "")
        if want and ws and Path(ws).resolve().as_posix() != Path(want).resolve().as_posix():
            skipped.append({"pid": row["pid"], "reason": "other_workspace"})
            continue
        if only_dead_callback:
            if row.get("callback_alive"):
                skipped.append({"pid": row["pid"], "reason": "callback_alive"})
                continue
        elif not row.get("orphan"):
            skipped.append({"pid": row["pid"], "reason": "live_owner"})
            continue
        pid = int(row["pid"])
        if dry_run:
            killed.append(pid)
            continue
        try:
            # Kill the node bridge; the wrapping ``sh`` usually exits after.
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            skipped.append({"pid": pid, "reason": "gone"})
        except PermissionError:
            skipped.append({"pid": pid, "reason": "permission"})
    if not dry_run and killed:
        time.sleep(0.4)
        for pid in list(killed):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    return {
        "ok": True,
        "dry_run": dry_run,
        "killed": killed,
        "killed_n": len(killed),
        "skipped": skipped,
        "remaining_n": len(list_cursor_bridges()) if not dry_run else None,
    }
