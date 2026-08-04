"""Read-only status of remote lbot (bbot) via SSH.

Default target: prodg.winex.org ~/lbot. Never reads remote .env / API secrets.
Does not start, stop, or trade — status only.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Optional

_DEFAULT_HOST = "prodg"
_DEFAULT_REMOTE_DIR = "~/lbot"
_DEFAULT_TIMEOUT = 15.0

_REMOTE_SCRIPT = r"""
import json, os, time
from pathlib import Path

root = Path(os.path.expanduser(REMOTE_DIR)).resolve()
out = {
    "ok": False,
    "remote_dir": str(root),
    "dir_exists": root.is_dir(),
    "hostname": None,
    "running": False,
    "processes": [],
    "tmux_sessions": [],
    "open_trades": 0,
    "trades": [],
    "log": None,
    "error": None,
}
try:
    out["hostname"] = Path("/etc/hostname").read_text(encoding="utf-8").strip()
except Exception:
    out["hostname"] = os.uname().nodename if hasattr(os, "uname") else None

if not root.is_dir():
    out["error"] = "remote_dir missing"
    print(json.dumps(out, ensure_ascii=False))
    raise SystemExit(0)

# Processes whose cwd is under lbot root
procs = []
try:
    for ent in Path("/proc").iterdir():
        if not ent.name.isdigit():
            continue
        try:
            cwd = (ent / "cwd").resolve()
        except Exception:
            continue
        if cwd != root and not str(cwd).startswith(str(root) + os.sep):
            continue
        try:
            cmd = (ent / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        except Exception:
            cmd = ""
        if not cmd:
            continue
        low = cmd.lower()
        # Ignore interactive shells attached to the bot directory (tmux panes).
        if low.startswith("-bash") or low.startswith("bash") or low.startswith("-zsh") or low.startswith("zsh"):
            continue
        if "python" not in low:
            continue
        procs.append({"pid": int(ent.name), "cmdline": cmd[:160]})
except Exception as exc:
    out["error"] = f"proc scan: {type(exc).__name__}"
out["processes"] = procs[:12]
out["running"] = bool(procs)

# tmux sessions (names only)
try:
    import subprocess as sp
    r = sp.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if r.returncode == 0:
        out["tmux_sessions"] = [s for s in r.stdout.splitlines() if s.strip()]
except Exception:
    pass

# Open trades snapshot (no secrets)
trades_path = root / "active_trades.json"
trade_rows = []
if trades_path.is_file():
    try:
        raw = json.loads(trades_path.read_text(encoding="utf-8"))
        items = []
        if isinstance(raw, dict):
            items = [v for v in raw.values() if isinstance(v, dict)]
        elif isinstance(raw, list):
            items = [v for v in raw if isinstance(v, dict)]
        for row in items:
            if row.get("open") is False:
                continue
            trade_rows.append(
                {
                    "symbol": str(row.get("symbol") or ""),
                    "mode": str(row.get("mode") or ""),
                    "roi": row.get("roi"),
                    "pnl": row.get("pnl"),
                    "entry_price": row.get("entry_price"),
                    "current_price": row.get("current_price"),
                    "open": bool(row.get("open", True)),
                }
            )
    except Exception as exc:
        out["error"] = f"trades: {type(exc).__name__}: {exc}"
out["trades"] = trade_rows[:24]
out["open_trades"] = len(trade_rows)

# Log metadata + short tail (no .env)
log_path = root / "trading_bot.log"
if log_path.is_file():
    try:
        st = log_path.stat()
        tail_lines = []
        with log_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 4096))
            chunk = fh.read().decode("utf-8", "replace")
        for line in chunk.splitlines()[-5:]:
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if "api_key" in low or "api_secret" in low or "secret" in low or "password" in low:
                continue
            tail_lines.append(s[:200])
        out["log"] = {
            "path": str(log_path),
            "size_bytes": int(st.st_size),
            "mtime_epoch": int(st.st_mtime),
            "age_sec": int(time.time() - st.st_mtime),
            "tail": tail_lines,
        }
    except Exception as exc:
        out["log"] = {"error": f"{type(exc).__name__}: {exc}"}

out["ok"] = True
print(json.dumps(out, ensure_ascii=False))
"""


def lbot_ssh_config() -> dict[str, Any]:
    """SSH probe settings from env (no secrets)."""
    host = (os.environ.get("EURIKA_LBOT_SSH_HOST") or _DEFAULT_HOST).strip() or _DEFAULT_HOST
    remote_dir = (os.environ.get("EURIKA_LBOT_REMOTE_DIR") or _DEFAULT_REMOTE_DIR).strip() or _DEFAULT_REMOTE_DIR
    try:
        timeout = float(os.environ.get("EURIKA_LBOT_SSH_TIMEOUT") or _DEFAULT_TIMEOUT)
    except ValueError:
        timeout = _DEFAULT_TIMEOUT
    enabled = True
    raw = (os.environ.get("EURIKA_LBOT_PROBE") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        enabled = False
    return {
        "enabled": enabled,
        "host": host,
        "remote_dir": remote_dir,
        "timeout": timeout,
    }


def _build_remote_script(remote_dir: str) -> str:
    return f"REMOTE_DIR = {json.dumps(remote_dir)}\n" + _REMOTE_SCRIPT


def _ssh_run(host: str, script: str, *, timeout: float) -> tuple[int, str, str]:
    """Run remote python via SSH stdin. Returns (returncode, stdout, stderr)."""
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, int(timeout))}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        host,
        "python3",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout + 5.0,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def probe_remote_lbot(
    *,
    host: Optional[str] = None,
    remote_dir: Optional[str] = None,
    timeout: Optional[float] = None,
    ssh_run=_ssh_run,
) -> dict[str, Any]:
    """Fetch read-only lbot status from remote host.

    Returns a dict safe to log (no API keys). On failure sets ok=False and error.
    """
    cfg = lbot_ssh_config()
    if not cfg["enabled"] and host is None:
        return {
            "ok": False,
            "skipped": True,
            "error": "EURIKA_LBOT_PROBE disabled",
            "host": cfg["host"],
            "remote_dir": cfg["remote_dir"],
        }
    use_host = (host or cfg["host"]).strip()
    use_dir = (remote_dir or cfg["remote_dir"]).strip()
    use_timeout = float(timeout if timeout is not None else cfg["timeout"])
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "ok": False,
        "skipped": False,
        "host": use_host,
        "remote_dir": use_dir,
        "latency_ms": None,
        "error": None,
    }
    try:
        code, stdout, stderr = ssh_run(use_host, _build_remote_script(use_dir), timeout=use_timeout)
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        if code != 0:
            err = (stderr or stdout or f"ssh exit {code}").strip().splitlines()
            result["error"] = (err[-1] if err else f"ssh exit {code}")[:300]
            return result
        line = stdout.strip().splitlines()[-1] if stdout.strip() else ""
        if not line:
            result["error"] = "empty remote response"
            return result
        payload = json.loads(line)
        if not isinstance(payload, dict):
            result["error"] = "unexpected remote payload"
            return result
        result.update(payload)
        result["host"] = use_host
        result["latency_ms"] = result.get("latency_ms") or round((time.perf_counter() - t0) * 1000.0, 1)
        result["skipped"] = False
        if "ok" not in result:
            result["ok"] = True
        return result
    except subprocess.TimeoutExpired:
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        result["error"] = "ssh timeout"
        return result
    except json.JSONDecodeError as exc:
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        result["error"] = f"invalid JSON: {exc}"
        return result
    except Exception as exc:
        result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def format_remote_lbot_block(probe: Optional[dict[str, Any]] = None) -> str:
    """Human-readable self-check block (never raises)."""
    try:
        data = probe if probe is not None else probe_remote_lbot()
    except Exception:
        return "\n".join(["", "LBOT (remote read-only)", "", "  ok: no", "  detail: probe failed"])
    lines = ["", "LBOT (remote read-only)", ""]
    if data.get("skipped"):
        lines.append("  skipped: yes")
        lines.append(f"  reason: {data.get('error') or 'disabled'}")
        return "\n".join(lines)
    lines.append(f"  host: {data.get('host')}")
    lines.append(f"  remote_dir: {data.get('remote_dir')}")
    if data.get("hostname"):
        lines.append(f"  hostname: {data.get('hostname')}")
    if data.get("latency_ms") is not None:
        lines.append(f"  latency_ms: {data.get('latency_ms')}")
    lines.append(f"  ok: {'yes' if data.get('ok') else 'no'}")
    if data.get("error"):
        lines.append(f"  error: {data.get('error')}")
    if data.get("ok"):
        lines.append(f"  running: {'yes' if data.get('running') else 'no'}")
        procs = data.get("processes") or []
        if procs:
            for p in procs[:3]:
                lines.append(f"    pid {p.get('pid')}: {p.get('cmdline')}")
        sessions = data.get("tmux_sessions") or []
        lines.append(f"  tmux: {', '.join(sessions) if sessions else '(none)'}")
        lines.append(f"  open_trades: {data.get('open_trades', 0)}")
        for t in (data.get("trades") or [])[:8]:
            lines.append(
                f"    {t.get('symbol')}: mode={t.get('mode')} roi={t.get('roi')} pnl={t.get('pnl')}"
            )
        extra = int(data.get("open_trades") or 0) - min(8, int(data.get("open_trades") or 0))
        if extra > 0:
            lines.append(f"    ... +{extra} more")
        log = data.get("log") or {}
        if isinstance(log, dict) and log.get("size_bytes") is not None:
            lines.append(
                f"  log: size={log.get('size_bytes')} age_sec={log.get('age_sec')}"
            )
            for row in (log.get("tail") or [])[-3:]:
                lines.append(f"    | {row}")
        elif isinstance(log, dict) and log.get("error"):
            lines.append(f"  log_error: {log.get('error')}")
    lines.append("  note: status only (no start/stop/orders)")
    return "\n".join(lines)
