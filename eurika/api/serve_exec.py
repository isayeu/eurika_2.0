"""POST /api/exec: run whitelisted eurika commands. ROADMAP 3.5.8."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

_FLAG_TAKES_VALUE = 1
_FLAG_IS_BOOL = 0

EXEC_WHITELIST = {"scan", "doctor", "fix", "cycle", "explain", "report-snapshot", "learning-kpi"}
EXEC_TIMEOUT_MIN = 1
EXEC_TIMEOUT_MAX = 3600
EXEC_ALLOWED_FLAGS: dict[str, dict[str, int]] = {
    "scan": {"--format": _FLAG_TAKES_VALUE, "-f": _FLAG_TAKES_VALUE, "--color": _FLAG_IS_BOOL, "--no-color": _FLAG_IS_BOOL},
    "doctor": {"--window": _FLAG_TAKES_VALUE, "--no-llm": _FLAG_IS_BOOL, "--online": _FLAG_IS_BOOL, "--runtime-mode": _FLAG_TAKES_VALUE},
    "fix": {
        "--window": _FLAG_TAKES_VALUE,
        "--dry-run": _FLAG_IS_BOOL,
        "--quiet": _FLAG_IS_BOOL,
        "-q": _FLAG_IS_BOOL,
        "--no-clean-imports": _FLAG_IS_BOOL,
        "--no-code-smells": _FLAG_IS_BOOL,
        "--verify-cmd": _FLAG_TAKES_VALUE,
        "--verify-timeout": _FLAG_TAKES_VALUE,
        "--interval": _FLAG_TAKES_VALUE,
        "--runtime-mode": _FLAG_TAKES_VALUE,
        "--non-interactive": _FLAG_IS_BOOL,
        "--session-id": _FLAG_TAKES_VALUE,
        "--allow-campaign-retry": _FLAG_IS_BOOL,
        "--allow-low-risk-campaign": _FLAG_IS_BOOL,
        "--online": _FLAG_IS_BOOL,
        "--apply-suggested-policy": _FLAG_IS_BOOL,
        "--team-mode": _FLAG_IS_BOOL,
        "--apply-approved": _FLAG_IS_BOOL,
        "--approve-ops": _FLAG_TAKES_VALUE,
        "--reject-ops": _FLAG_TAKES_VALUE,
    },
    "cycle": {
        "--window": _FLAG_TAKES_VALUE,
        "--dry-run": _FLAG_IS_BOOL,
        "--quiet": _FLAG_IS_BOOL,
        "-q": _FLAG_IS_BOOL,
        "--no-llm": _FLAG_IS_BOOL,
        "--no-clean-imports": _FLAG_IS_BOOL,
        "--no-code-smells": _FLAG_IS_BOOL,
        "--verify-cmd": _FLAG_TAKES_VALUE,
        "--verify-timeout": _FLAG_TAKES_VALUE,
        "--interval": _FLAG_TAKES_VALUE,
        "--runtime-mode": _FLAG_TAKES_VALUE,
        "--non-interactive": _FLAG_IS_BOOL,
        "--session-id": _FLAG_TAKES_VALUE,
        "--allow-campaign-retry": _FLAG_IS_BOOL,
        "--allow-low-risk-campaign": _FLAG_IS_BOOL,
        "--online": _FLAG_IS_BOOL,
        "--apply-suggested-policy": _FLAG_IS_BOOL,
        "--team-mode": _FLAG_IS_BOOL,
        "--apply-approved": _FLAG_IS_BOOL,
        "--approve-ops": _FLAG_TAKES_VALUE,
        "--reject-ops": _FLAG_TAKES_VALUE,
    },
    "explain": {"--window": _FLAG_TAKES_VALUE},
    "report-snapshot": {},
    "learning-kpi": {"--json": _FLAG_IS_BOOL, "--top-n": _FLAG_TAKES_VALUE, "--polygon": _FLAG_IS_BOOL},
}


def _normalize_exec_args_for_subcommand(
    project_root: Path,
    subcmd: str,
    raw_args: list[str],
) -> tuple[list[str] | None, str | None]:
    """Validate/normalize argv for a whitelisted eurika subcommand."""
    allowed_flags = EXEC_ALLOWED_FLAGS.get(subcmd, {})
    flags: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(raw_args):
        tok = str(raw_args[i])
        if tok.startswith("-"):
            arity = allowed_flags.get(tok)
            if arity is None:
                allowed = ", ".join(sorted(allowed_flags.keys()))
                hint = f"Allowed flags for '{subcmd}': {allowed}" if allowed else f"'{subcmd}' does not accept flags"
                return None, f"flag not allowed for '{subcmd}': {tok}. {hint}"
            flags.append(tok)
            if arity == _FLAG_TAKES_VALUE:
                if i + 1 >= len(raw_args):
                    return None, f"flag '{tok}' requires a value"
                flags.append(str(raw_args[i + 1]))
                i += 1
            i += 1
            continue
        positional.append(tok)
        i += 1

    path_str = str(project_root)
    if subcmd == "explain":
        if not positional:
            return None, "explain requires module positional argument (e.g. 'eurika explain cli/handlers.py')"
        if len(positional) > 2:
            return None, f"too many positional arguments for explain: {positional}"
        module = positional[0]
        return [module, path_str] + flags, None

    if len(positional) > 1:
        return None, f"too many positional arguments for '{subcmd}': {positional}"
    return [path_str] + flags, None


def exec_eurika_command(project_root: Path, command: str, timeout: int | None = 120) -> dict:
    """Execute a whitelisted eurika command in project_root."""
    cmd_str = (command or "").strip()
    if not cmd_str:
        return {"error": "command required", "stdout": "", "stderr": "", "exit_code": -1}
    parts = shlex.split(cmd_str)
    if not parts:
        return {"error": "empty command", "stdout": "", "stderr": "", "exit_code": -1}
    subcmd = parts[0].lower()
    if subcmd == "eurika" and len(parts) > 1:
        subcmd = parts[1].lower()
        args = parts[2:]
    else:
        args = parts[1:] if len(parts) > 1 else []
    if subcmd not in EXEC_WHITELIST:
        return {
            "error": f"command not allowed: '{subcmd}'. Allowed: {', '.join(sorted(EXEC_WHITELIST))}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    normalized_args, normalize_error = _normalize_exec_args_for_subcommand(
        project_root, subcmd, args
    )
    if normalize_error:
        return {"error": normalize_error, "stdout": "", "stderr": "", "exit_code": -1}

    full_args = [sys.executable, "-m", "eurika_cli", subcmd] + (normalized_args or [])
    try:
        r = subprocess.run(
            full_args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "exit_code": r.returncode,
            "command": " ".join(full_args),
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "stdout": "", "stderr": "Command timed out", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "stdout": "", "stderr": str(e), "exit_code": -1}
