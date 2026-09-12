"""Read-only host admin v0 (VISION Stage 6).

Default is observe: facts via host_shell / tool-loop. Commands that would
change the OS (packages, services, reboot, network radio, …) are queued for
HITL — the existing Chat phrases «одобрить» / «применяй» / «отклонить».
Sudo stays a separate privilege dialog after approve.

Not a user phrase-book: classification is on the *command*, not the request.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from eurika.storage.paths import STORAGE_DIR, ensure_storage_dir

POLICY_VERSION = 1
PENDING_NAME = "pending_host_admin.json"
MAX_QUEUED = 5

HostAdminClass = str  # observe | mutate | workspace_write

_ALWAYS_MUTATE = frozenset(
    {
        "reboot",
        "shutdown",
        "poweroff",
        "halt",
        "mkfs",
        "wipefs",
        "useradd",
        "userdel",
        "usermod",
        "passwd",
        "visudo",
        "modprobe",
        "insmod",
        "rmmod",
        "lpadmin",
        "cupsenable",
        "cupsdisable",
    }
)

_SYSTEMCTL_OBSERVE = frozenset(
    {
        "status",
        "show",
        "cat",
        "help",
        "list-units",
        "list-unit-files",
        "list-jobs",
        "list-timers",
        "list-sockets",
        "list-dependencies",
        "is-active",
        "is-enabled",
        "is-failed",
        "is-system-running",
        "get-default",
        "show-environment",
    }
)

_APT_OBSERVE = frozenset(
    {"list", "show", "search", "policy", "depends", "rdepends", "changelog"}
)

_NMCLI_MUTATE = frozenset(
    {
        "up",
        "down",
        "add",
        "modify",
        "delete",
        "clone",
        "connect",
        "disconnect",
        "off",
        "on",
        "edit",
    }
)

_BLUETOOTH_MUTATE = frozenset(
    {"pair", "connect", "disconnect", "power", "remove", "trust", "untrust", "scan"}
)

_TOKEN_SPLIT = re.compile(r"\s+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strip_sudo(cmd: str) -> str:
    s = (cmd or "").strip()
    if s.lower().startswith("sudo "):
        return s[5:].lstrip()
    return s


def _tokens(cmd: str) -> List[str]:
    return [t for t in _TOKEN_SPLIT.split(_strip_sudo(cmd)) if t]


def _first_subcommand(tokens: Sequence[str]) -> str:
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        return tok.lower()
    return ""


def _pacman_class(tokens: Sequence[str]) -> HostAdminClass:
    letters = ""
    longs: List[str] = []
    for tok in tokens[1:]:
        if tok.startswith("--"):
            longs.append(tok.lower())
        elif tok.startswith("-") and len(tok) > 1 and tok[1].isalpha():
            letters += tok[1:]
    if "Q" in letters or "--query" in longs:
        return "observe"
    if "F" in letters or "--files" in longs:
        return "observe"
    if any(flag in longs for flag in ("--search", "--info", "--list", "--groups")):
        if not any(flag in longs for flag in ("--refresh", "--sysupgrade")):
            return "observe"
    if "S" in letters:
        rest = letters.replace("S", "")
        if rest and set(rest) <= set("silg") and "y" not in rest.lower() and "u" not in rest.lower():
            return "observe"
    return "mutate"


def _apt_class(tokens: Sequence[str]) -> HostAdminClass:
    sub = _first_subcommand(tokens)
    if sub in _APT_OBSERVE:
        return "observe"
    return "mutate"


def _systemctl_class(tokens: Sequence[str]) -> HostAdminClass:
    joined = " ".join(tokens).lower()
    if "--failed" in joined and not _first_subcommand(tokens):
        return "observe"
    sub = _first_subcommand(tokens)
    if sub in _SYSTEMCTL_OBSERVE:
        return "observe"
    return "mutate"


def _nmcli_class(tokens: Sequence[str]) -> HostAdminClass:
    low = [t.lower() for t in tokens]
    if any(t in _NMCLI_MUTATE for t in low[1:]):
        return "mutate"
    return "observe"


def _bluetooth_class(tokens: Sequence[str]) -> HostAdminClass:
    sub = _first_subcommand(tokens)
    if sub in _BLUETOOTH_MUTATE:
        return "mutate"
    return "observe"


def host_command_mutates_os(cmd: str) -> bool:
    """True when the command would change the host (not just read it)."""
    return classify_host_admin_command(cmd) == "mutate"


def classify_host_admin_command(cmd: str) -> HostAdminClass:
    """observe | mutate | workspace_write.

    ``workspace_write`` is delegated to the project-tree gate so callers can
    branch once. OS mutate is deny-by-default for known admin binaries.
    """
    raw = (cmd or "").strip()
    if not raw:
        return "observe"
    from eurika.api.chat_host_ops import host_command_mutates_workspace

    if host_command_mutates_workspace(raw):
        return "workspace_write"
    tokens = _tokens(raw)
    if not tokens:
        return "observe"
    binary = tokens[0].rsplit("/", 1)[-1].lower()
    if binary in _ALWAYS_MUTATE:
        return "mutate"
    if binary == "systemctl":
        return _systemctl_class(tokens)
    if binary == "pacman":
        return _pacman_class(tokens)
    if binary in {"apt", "apt-get"}:
        return _apt_class(tokens)
    if binary in {"dnf", "zypper", "apk", "yum"}:
        sub = _first_subcommand(tokens)
        if sub in {"list", "search", "info", "show"}:
            return "observe"
        return "mutate"
    if binary == "nmcli":
        return _nmcli_class(tokens)
    if binary == "bluetoothctl":
        return _bluetooth_class(tokens)
    if binary in {"pip", "pip3"} and any(t.lower() in {"install", "uninstall"} for t in tokens[1:]):
        return "mutate"
    if binary in {"flatpak", "snap"}:
        sub = _first_subcommand(tokens)
        if sub in {"install", "remove", "uninstall", "update"}:
            return "mutate"
        return "observe"
    if binary == "udevadm":
        sub = _first_subcommand(tokens)
        return "observe" if sub in {"info", "settle"} or not sub else "mutate"
    return "observe"


def pending_host_admin_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / STORAGE_DIR / PENDING_NAME


def load_pending_host_admin(project_root: Path) -> Optional[Dict[str, Any]]:
    path = pending_host_admin_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    cmds = data.get("commands")
    if not isinstance(cmds, list) or not cmds:
        return None
    return data


def clear_pending_host_admin(project_root: Path) -> bool:
    path = pending_host_admin_path(project_root)
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def queue_host_admin(
    project_root: Path,
    commands: Sequence[str],
    *,
    source: str = "tool_loop",
) -> Dict[str, Any]:
    """Append unique mutating commands to the HITL queue (cap MAX_QUEUED)."""
    root = Path(project_root).resolve()
    ensure_storage_dir(root)
    existing = load_pending_host_admin(root) or {}
    queued = [str(c).strip() for c in (existing.get("commands") or []) if str(c).strip()]
    for cmd in commands:
        body = (cmd or "").strip()
        if not body or body in queued:
            continue
        queued.append(body)
        if len(queued) >= MAX_QUEUED:
            break
    payload = {
        "version": POLICY_VERSION,
        "created_at": str(existing.get("created_at") or _utc_now()),
        "updated_at": _utc_now(),
        "pipeline": "host_admin_v0",
        "source": source,
        "policy": "read-only default; mutate queued for HITL",
        "commands": queued[:MAX_QUEUED],
    }
    path = pending_host_admin_path(root)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def format_host_admin_blocked(cmd: str) -> str:
    return (
        f"$ {cmd}\n(exit 126)\n"
        "отказ: host admin — read-only. Команда меняет ОС "
        "(пакеты / сервисы / reboot / radio). "
        "Поставлена в очередь HITL (.eurika/pending_host_admin.json). "
        "Подтверждение — существующей фразой «одобрить» / «применяй»; "
        "sudo — отдельный диалог после approve. "
        "Не повторяй ту же команду и не обходи через sudo."
    )


def format_pending_host_admin_text(pending: Dict[str, Any]) -> str:
    cmds = [str(c) for c in (pending.get("commands") or []) if str(c).strip()]
    if not cmds:
        return "Нет очереди host admin."
    lines = [
        "Host admin (read-only v0) — очередь HITL:",
        *[f"- `{c}`" for c in cmds],
        "Подтверди «одобрить» / «применяй» или отклони. После approve sudo — отдельный диалог.",
    ]
    return "\n".join(lines)


def format_host_admin_brief(project_root: Path) -> List[str]:
    pending = load_pending_host_admin(project_root)
    if not pending:
        return []
    cmds = [str(c) for c in (pending.get("commands") or []) if str(c).strip()]
    if not cmds:
        return []
    lines = ["", "Host admin HITL (read-only default):"]
    for cmd in cmds[:MAX_QUEUED]:
        lines.append(f"- {cmd}")
    lines.append("- подтверждение: «одобрить» / «применяй»")
    return lines


def refuse_mutating_host_command(
    cmd: str,
    *,
    project_root: Optional[Path] = None,
    source: str = "tool_loop",
):
    """If the command mutates the OS, queue HITL and return a refused result."""
    from eurika.api.chat_host_ops import HostCommandResult

    kind = classify_host_admin_command(cmd)
    if kind != "mutate":
        return None
    if project_root is not None:
        try:
            queue_host_admin(Path(project_root), [cmd], source=source)
        except OSError:
            pass
    return HostCommandResult(
        126,
        format_host_admin_blocked(cmd),
        privilege_note="host_admin_hitl",
    )


def apply_pending_host_admin(
    project_root: Path,
    *,
    privilege_prompt=None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Run queued mutating commands after HITL. Workspace writes stay refused."""
    from eurika.api.chat_host_ops import (
        HostCommandResult,
        host_command_mutates_workspace,
        run_host_command_with_privilege,
    )

    root = Path(project_root).resolve()
    pending = load_pending_host_admin(root)
    if not pending:
        return {
            "ok": False,
            "text": "Нет очереди host admin на подтверждение.",
            "error": "no pending host admin",
            "terminal_cmd": "",
            "terminal_output": "",
            "terminal_exit_code": 0,
        }
    commands = [str(c).strip() for c in (pending.get("commands") or []) if str(c).strip()]
    log_parts: List[str] = []
    worst = 0
    ran = 0
    for cmd in commands[:MAX_QUEUED]:
        if host_command_mutates_workspace(cmd):
            result = HostCommandResult(
                126,
                "отказ: команда меняет файлы проекта; host admin HITL этого не обходит.",
            )
        else:
            result = run_host_command_with_privilege(
                cmd,
                privilege_prompt=privilege_prompt,
                timeout=timeout,
                cwd=str(root),
            )
            ran += 1
        display = cmd
        if result.used_sudo and not cmd.lower().startswith("sudo "):
            display = f"sudo {cmd}"
        block = f"$ {display}\n{result.output}"
        if result.privilege_note:
            block += f"\n[{result.privilege_note}]"
        log_parts.append(block)
        if result.exit_code not in (0, 127) and worst == 0:
            worst = int(result.exit_code)
    clear_pending_host_admin(root)
    text = "\n\n".join(log_parts) if log_parts else "(empty)"
    prefix = "Host admin HITL: выполнено после «одобрить».\n\n"
    return {
        "ok": worst == 0,
        "text": prefix + text,
        "error": None if worst == 0 else "host admin command failed",
        "terminal_cmd": f"$ {commands[0]}" if commands else "$ # host admin",
        "terminal_output": text,
        "terminal_exit_code": int(worst),
        "ran": ran,
    }
