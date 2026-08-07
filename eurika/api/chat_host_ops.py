"""Agent tool-loop: LLM decides → read-only commands run → LLM answers from output.

No per-device / per-domain intent lists and no canned reply templates.
The whole answer is written by the model; this module only provides the tool
(a read-only command sandbox) and the loop that feeds output back.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

# Safety sandbox only — not product logic / not domain routing.
_ALLOWED_BINS = frozenset(
    {
        "bluetoothctl",
        "pactl",
        "wpctl",
        "pw-cli",
        "amixer",
        "nmcli",
        "ip",
        "iw",
        "rfkill",
        "lsusb",
        "lsblk",
        "lspci",
        "lscpu",
        "free",
        "df",
        "uptime",
        "uname",
        "systemctl",
        "journalctl",
        "loginctl",
        "timedatectl",
        "hostnamectl",
        "ss",
        "ping",
        "resolvectl",
        "cat",
        "head",
        "tail",
        "wc",
        "true",
        "echo",
        "test",
        "hciconfig",
        "hcitool",
        "nvidia-smi",
        "glxinfo",
        "vulkaninfo",
        "radeontop",
        "inxi",
        "ps",
        "pgrep",
        "pidof",
    }
)

_DENIED_METACHAR = re.compile(r"[;&|`$<>\n\r]|&&|\|\||\$\(|`")
_MAX_CMDS = 5
_MAX_OUT = 2000
_MAX_OBS = 8000
_GROUND_FACTS = (
    "Больше команд не запускай. Ответь пользователю ТОЛЬКО по фактам из "
    "[Вывод выполненных команд] выше. Не выдумывай CPU/GPU, диски, вендоров и "
    "устройства, которых нет в выводе. Если данных нет — так и скажи. "
    "Краткий структурированный список своими словами."
)
# Tool-call syntax. A language tag is required so ordinary code blocks
# (```python, bare ```) are never treated as commands nor stripped.
_TOOL_FENCE = re.compile(
    r"```(?:eurika-cmds|eurika_cmds|bash|sh|shell|zsh)[^\S\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def is_safe_host_command(cmd: str) -> bool:
    """Allow only simple read-only argv lines (no shell metacharacters)."""
    s = (cmd or "").strip()
    if not s or len(s) > 240:
        return False
    if _DENIED_METACHAR.search(s):
        return False
    low = s.lower()
    if any(
        bad in low
        for bad in (
            " rm ",
            "mkfs",
            "dd ",
            "shutdown",
            "reboot",
            "poweroff",
            "systemctl start",
            "systemctl stop",
            "systemctl restart",
            "systemctl enable",
            "systemctl disable",
            "bluetoothctl remove",
            "bluetoothctl disconnect",
            "nmcli c up",
            "nmcli c down",
            "nmcli device disconnect",
            "> /",
        )
    ):
        return False
    parts = s.split()
    if not parts:
        return False
    bin_name = parts[0]
    if "/" in bin_name:
        bin_name = bin_name.rsplit("/", 1)[-1]
    if bin_name not in _ALLOWED_BINS:
        return False
    if bin_name == "systemctl":
        rest = " ".join(parts[1:]).lower()
        if not any(
            rest.startswith(p)
            for p in (
                "status",
                "is-active",
                "is-failed",
                "is-enabled",
                "list-units",
                "list-timers",
                "list-sockets",
                "--failed",
                "show",
            )
        ):
            return False
    if bin_name == "journalctl":
        if any(x in low for x in (" --vacuum", " --rotate", " --flush")):
            return False
    if bin_name in {"cat", "head", "tail"}:
        if len(parts) < 2:
            return False
        path = parts[-1]
        if not path.startswith(("/proc/", "/sys/", "/etc/")):
            return False
        if any(s in path.lower() for s in ("shadow", "passwd", "ssh", "credential", "token", "secret")):
            return False
    return True


def _normalize_candidate_cmd(line: str) -> Optional[str]:
    """Turn LLM command lines into allowlisted argv (drop `| grep …`)."""
    cmd = (line or "").strip().lstrip("$ ").strip()
    if not cmd or cmd.startswith("#"):
        return None
    if " #" in cmd:
        cmd = cmd.split(" #", 1)[0].strip()
    if "|" in cmd:
        left = cmd.split("|", 1)[0].strip()
        right = cmd.split("|", 1)[1].strip().lower()
        if right.startswith(("grep", "rg ", "head", "tail", "wc ")):
            cmd = left
        else:
            return None
    if is_safe_host_command(cmd):
        return cmd
    return None


def extract_eurika_cmds(text: str) -> List[str]:
    """Parse a ```eurika-cmds``` tool call into safe commands."""
    if not (text or "").strip():
        return []
    blocks: List[str] = list(_TOOL_FENCE.findall(text))
    out: List[str] = []
    for block in blocks:
        for line in str(block).splitlines():
            cmd = _normalize_candidate_cmd(line)
            if cmd and cmd not in out:
                out.append(cmd)
            if len(out) >= _MAX_CMDS:
                return out
    return out


def has_tool_call(text: str) -> bool:
    return bool(_TOOL_FENCE.search(text or ""))


def strip_tool_calls(text: str) -> str:
    """Drop protocol fences so the user (and history) see only the answer."""
    out = _TOOL_FENCE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def tool_protocol_instructions() -> str:
    """Prompt fragment describing the host_shell tool. Skeleton, not domain knowledge."""
    allow = ", ".join(sorted(_ALLOWED_BINS))
    return (
        "Инструмент host_shell (Linux, только чтение). Если для ответа нужны факты о "
        "машине пользователя — не угадывай и не описывай, как проверить: выведи блок "
        "```eurika-cmds``` c 1–5 командами, по одной в строке. Я выполню их сам и верну "
        "вывод, после чего ты дашь окончательный ответ своими словами строго по этому "
        "выводу (без выдуманных устройств и цифр). Не проси пользователя запускать "
        "команды и не жди подтверждения.\n"
        f"Разрешённые бинарники: {allow}. Без sudo, пайпов, редиректов и ; | & $ ` < >."
    )


def _pack_observations(observations: Sequence[str], budget: int = _MAX_OBS) -> str:
    """Fit tool outputs into the prompt budget without chopping off command heads.

    Taking ``joined[-budget:]`` dropped hostname/CPU model first; small models then
    invented devices. Prefer equal per-command head slices instead.
    """
    parts = [str(o) for o in observations if str(o).strip()]
    if not parts:
        return ""
    joined = "\n\n".join(parts)
    if len(joined) <= budget:
        return joined
    n = len(parts)
    per = max(600, budget // n)
    packed: List[str] = []
    for obs in parts:
        if len(obs) <= per:
            packed.append(obs)
        else:
            packed.append(obs[: per - 20].rstrip() + "\n…")
    out = "\n\n".join(packed)
    if len(out) > budget:
        return out[: budget - 1].rstrip() + "…"
    return out


def run_safe_host_command(cmd: str, *, timeout: float = 20.0) -> Tuple[int, str]:
    if not is_safe_host_command(cmd):
        return 126, f"(blocked unsafe command: {cmd})"
    argv = cmd.split()
    bin0 = argv[0]
    if bin0 not in {"echo", "true", "test", "cat", "head", "tail", "wc"} and not shutil.which(bin0):
        return 127, f"(not found: {bin0})"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if len(out) > _MAX_OUT:
            out = out[:_MAX_OUT] + "\n…"
        return int(r.returncode), out or "(empty)"
    except subprocess.TimeoutExpired:
        return -1, f"(timeout: {cmd})"
    except Exception as exc:
        return -1, f"({type(exc).__name__}: {exc})"


@dataclass
class ToolLoopResult:
    """Final model answer plus what the loop actually executed."""

    text: str
    terminal_log: str = ""
    commands: List[str] = field(default_factory=list)
    exit_code: int = 0

    @property
    def ran_tools(self) -> bool:
        return bool(self.commands)


def _llm_call(prompt: str, max_tokens: int) -> Tuple[Optional[str], Optional[str]]:
    from eurika.reasoning.architect import call_llm_with_prompt

    return call_llm_with_prompt(prompt, max_tokens=max_tokens)


def run_llm_tool_loop(
    base_prompt: str,
    *,
    max_iters: int = 3,
    max_tokens: int = 1024,
    call: Optional[Callable[[str, int], Tuple[Optional[str], Optional[str]]]] = None,
) -> Tuple[ToolLoopResult, Optional[str]]:
    """Run LLM ↔ host_shell until the model answers without asking for tools."""
    ask = call or _llm_call
    steps = max(1, int(max_iters))
    observations: List[str] = []
    log_parts: List[str] = []
    executed: List[str] = []
    worst = 0
    text = ""
    for step in range(steps):
        final_step = step == steps - 1
        prompt = base_prompt
        if observations:
            prompt += "\n\n[Вывод выполненных команд]\n" + _pack_observations(observations)
        if final_step and observations:
            prompt += "\n\n" + _GROUND_FACTS
        raw, err = ask(prompt, max_tokens)
        text = raw or ""
        if err:
            return ToolLoopResult(strip_tool_calls(text), "\n\n".join(log_parts), executed, worst or 1), err
        cmds = extract_eurika_cmds(text)
        if final_step or (not cmds and not has_tool_call(text)):
            break
        if not cmds:
            allow = ", ".join(sorted(_ALLOWED_BINS))
            observations.append(
                "Команды не выполнены: они вне read-only allowlist или содержат "
                f"запрещённые символы. Разрешено только: {allow}. "
                "Предложи другие команды или ответь текстом."
            )
            continue
        if not log_parts:
            log_parts.append("=== HOST TOOL LOOP (read-only) ===")
        obs: List[str] = []
        for cmd in cmds:
            code, out = run_safe_host_command(cmd)
            executed.append(cmd)
            log_parts.append(f"$ {cmd}\n{out}")
            obs.append(f"$ {cmd}\n(exit {code})\n{out}")
            if code not in (0, 127) and worst == 0:
                worst = code
        observations.append("\n\n".join(obs))
    return ToolLoopResult(strip_tool_calls(text), "\n\n".join(log_parts), executed, worst), None
