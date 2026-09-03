"""Agent tool-loop: LLM decides → host commands run → LLM answers from output.

Protocol fence is only ``eurika-cmds`` (ordinary ``bash``/``python`` blocks are
left for the UI Copy/Run chips). Commands run via ``bash -c`` in the project
cwd with no binary allowlist. If a command needs privileges, an optional
``privilege_prompt`` may ask for a sudo password, continue with the limited
output, or skip.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Literal, Optional, Sequence, Tuple

_MAX_CMDS = 5
_MAX_OUT = 4000
_MAX_OBS = 8000
_MAX_CMD_LEN = 2000
_HOST_GREP_EXCLUDES = (
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    ".tox",
    "dist",
    "build",
)
_RECURSIVE_GREP = re.compile(r"(?:^|[\s;|&])grep\s+-[A-Za-z0-9]*[rR]|(?:^|[\s;|&])grep\s+[^\n]*--recursive\b")
_GROUND_FACTS = (
    "Больше команд не запускай. Ответь пользователю ТОЛЬКО по фактам из "
    "[Вывод выполненных команд], [Host identity] и [Market facts] выше (если есть). "
    "Не выдумывай CPU/GPU, диски, вендоров, ОС, процессы и устройства, которых нет в выводе. "
    "Не предполагай macOS/Windows и не советуй Activity Monitor / ifconfig, если этого "
    "нет в выводе. Если в выводе есть nmcli/ip — назови конкретные линки "
    "(SSID, ethernet, wg/VPN, IP, шлюз) словами из вывода; не пиши «несколько подключений». "
    "ss/netstat/lsof — это порты/сокеты, не ответ про Wi‑Fi/VPN. "
    "Не выдумывай имена вроде Eurika-server. Если данных нет — так и скажи. "
    "На вопрос про соединения к сети начни с именованных линков из nmcli/ip "
    "(SSID, VPN/wg, ethernet up/down, default route); не открывай фразой "
    "«несколько подключений» и не считай localhost/loopback ответом про интернет. "
    "Ответ — обычным текстом (1–5 предложений), БЕЗ блоков ```bash``` / ```code``` и без "
    "повторного eurika-cmds: не оформляй вывод команд как code fence. "
    "Если есть MARKET LEARNING / Paper-экзамен / строка «вердикт:» — не сжимай "
    "ответ в 3 абзаца: сохрани markdown-таблицы (банк, live, головы, ворота, LLM-учитель) "
    "и экономический вердикт. Убыток/отрицательный equity Δ / отрицательный net edge = "
    "плохо для paper; не говори «неплохо/хорошо/потенциал», подменяя убыток accuracy. "
    "Accuracy ≠ прибыль. Если есть строка «дальше:» / «Дальше:» — копируй её: "
    "убыток при работающих воротах ≠ «пересмотреть стратегию»."
)

_MARKET_LEARNING_CMD = (
    'python -c "from eurika.ml.root import resolve_market_root; '
    "from eurika.ml.learning_status import format_market_learning_report; "
    'print(format_market_learning_report(resolve_market_root()))"'
)

_MARKET_ASK_RE = re.compile(
    r"(?is)("
    r"маркет|market|paper[\s_-]?trad|"
    r"успех\w*.{0,40}(ml|мл|обучен|market|маркет)|"
    r"(обучен|learning).{0,20}(ml|мл|market|маркет)|"
    r"(разбор|аудит|статус|pnl|прибыл|убыт|equity|банк|стратег).{0,40}(маркет|market|paper|обучен|ml)|"
    r"(маркет|market|paper).{0,40}(разбор|аудит|успех|статус|pnl|прибыл|убыт|стратег)"
    r")"
)

_LLM_TEACHER_ASK_RE = re.compile(
    r"(?is)("
    r"(llm|ллм).{0,30}(прогноз|учител|teacher|в плюс|прибыл|исход)|"
    r"(прогноз).{0,30}(llm|ллм|учител)"
    r")"
)

_LLM_TEACHER_EXEC_ASK_RE = re.compile(
    r"(?is)("
    r"(ml|mlp).{0,25}(совет|llm|ллм|учител|teacher)|"
    r"(отработал|исполнил|следует|execut).{0,25}(llm|ллм|учител|teacher|совет)|"
    r"по совету.{0,15}(llm|ллм)|"
    r"(хоть раз).{0,20}(llm|ллм|совет)"
    r")"
)
_BARE_FILE_READ = re.compile(
    r"^(?:sed\s+-n\s+'[0-9,]+p'|head(?:\s+-n)?\s+\d+|cat)\s+"
    r"(?!/)(?!\.\./)([a-zA-Z0-9_./-]+\.py)\s*$"
)
_BARE_PYTHON_PRINT = re.compile(
    r"^python(?:3)?\s+-c\s+['\"].*['\"]\s*$",
    re.IGNORECASE,
)
_TOOL_FENCE = re.compile(
    r"```(?:eurika-cmds|eurika_cmds)[^\S\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
# Small models often put the protocol name inside a generic fence:
#   ```code\neurika-cmds:\npwd\n```   or   ```\neurika-cmds\npwd\n```
_GENERIC_FENCE = re.compile(r"```([\w+-]*)[^\S\n]*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_INLINE_TOOL_HEADER = re.compile(
    r"(?im)^\s*eurika[-_]?cmds\s*:?\s*$"
)
_PERM_HINT = re.compile(
    r"permission denied|operation not permitted|must be root|"
    r"a password is required|sudo:|not permitted|доступ запрещ",
    re.IGNORECASE,
)
# Stale chat history / small models still invent the retired binary allowlist.
_FAKE_ALLOWLIST = re.compile(
    r"allowlist|разрешенн\w+\s+allowlist|Разрешены только следующие команды|"
    r"вне\s+(?:разреш|read-only).*allowlist|amixer\s*\n\s*bluetoothctl",
    re.IGNORECASE,
)
# Tutorial instead of observation: tell the user how to check, often the wrong OS.
_ADVICE_WITHOUT_TOOLS = re.compile(
    r"activity\s*monitor|ifconfig\b|ipconfig\b|"
    r"\bnetstat\b|"
    r"lsof\s+-i|"
    r"на macos|on macos|в macos|"
    r"вы можете использовать|"
    r"you can use (the )?(command|команд)",
    re.IGNORECASE,
)
_ADVICE_NUDGE = (
    "ОШИБКА: ты описал, КАК проверить хост, вместо того чтобы проверить. "
    "Это Linux (см. [Host identity]). Не советуй Activity Monitor / ifconfig / "
    "netstat пользователю и не проси его запускать команды. Выведи только блок "
    "```eurika-cmds``` с командами (например: nmcli device status; "
    "nmcli connection show --active; ip -br addr; ip route), по одной в строке."
)
_UPLINK_ASK_RE = re.compile(
    r"(?is)("
    r"соединен|подключен|wifi|wi-?fi|wlan|vpn|wireguard|"
    r"к сети|сетев\w+\s+соедин|интерфейс"
    r")"
)
_SOCKET_CMD_RE = re.compile(r"^(?:sudo\s+)?(?:netstat|ss|lsof)\b", re.IGNORECASE)
_UPLINK_CMD_RE = re.compile(
    r"^(?:sudo\s+)?(?:nmcli|ip\s+(?:-br\s+)?addr|ip\s+route|iw\s+dev)\b",
    re.IGNORECASE,
)
_UPLINK_NUDGE = (
    "ОШИБКА: ss/netstat/lsof показывают порты и сокеты, а не каналы выхода в сеть. "
    "Для вопроса про текущие соединения хоста выведи только ```eurika-cmds``` с "
    "`nmcli device status`, `nmcli connection show --active`, `ip -br addr`, `ip route` "
    "(по одной в строке). Не повторяй ss/lsof/netstat."
)

PrivilegeAction = Literal["password", "continue", "skip"]
PrivilegePrompt = Callable[[str, str], Tuple[PrivilegeAction, str]]


@dataclass
class HostCommandResult:
    exit_code: int
    output: str
    used_sudo: bool = False
    privilege_note: str = ""


def is_safe_host_command(cmd: str) -> bool:
    """Backward-compatible name: any non-empty host command is runnable.

    Kept so older imports/tests keep working. Privilege is handled at run time,
    not by a binary allowlist.
    """
    s = (cmd or "").strip()
    return bool(s) and len(s) <= _MAX_CMD_LEN


_DEV_NULL_REDIR = re.compile(r"(?:\d)?>>?\s*/dev/null|\b2>&1\b")
_MUTATING_BIN = re.compile(
    r"(?:^|[;&|]\s*)(?:rm|mv|cp|chmod|chown|chgrp|truncate|dd|install|touch|mkdir|"
    r"rmdir|ln|tee|sed\s+-i|perl\s+-i)\b",
    re.IGNORECASE,
)
_WRITE_OPEN = re.compile(
    r"""open\s*\([^)]*['\"][wa]|\.write_text\s*\(|\.write_bytes\s*\(|"""
    r"""Path\([^)]*\)\.write|to_json\s*\(|dump\s*\([^,]*,\s*open\s*\(""",
    re.IGNORECASE,
)
_FILE_REDIRECT = re.compile(r"(?:^|[^0-9])(?:>>|>)\s*(?!/dev/)")
_MUTATING_GIT = re.compile(
    r"(?:^|[;&|]\s*)git\s+"
    r"(?:add|commit|push|reset|checkout|switch|merge|rebase|stash|tag|"
    r"branch\s+-[dD]|clean|cherry-pick|revert)\b",
    re.IGNORECASE,
)


def host_command_mutates_workspace(cmd: str) -> bool:
    """True when a host_shell line would create/overwrite/delete files.

    Chat tool-loop is for facts (grep/sed/python -c print). Mutations go through
    HITL Apply / agent ``edit`` proposals — same boundary as Cursor Agent.
    """
    s = (cmd or "").strip()
    if not s:
        return False
    cleaned = _DEV_NULL_REDIR.sub(" ", s)
    if _MUTATING_BIN.search(cleaned):
        return True
    if _MUTATING_GIT.search(cleaned):
        return True
    if _FILE_REDIRECT.search(cleaned):
        return True
    if _WRITE_OPEN.search(cleaned):
        return True
    return False


def harden_host_command(cmd: str) -> str:
    """Keep recursive grep out of venv/cache trees without a binary allowlist."""
    raw = (cmd or "").strip()
    if not raw or not _RECURSIVE_GREP.search(raw):
        return raw
    missing = [name for name in _HOST_GREP_EXCLUDES if f"--exclude-dir={name}" not in raw]
    if not missing:
        return raw
    return raw + "".join(f" --exclude-dir={name}" for name in missing)


def _normalize_candidate_cmd(line: str) -> Optional[str]:
    """Normalize one tool-call line (keep pipes/redirects — runs under bash -c)."""
    cmd = (line or "").strip().lstrip("$ ").strip()
    if not cmd or cmd.startswith("#"):
        return None
    if " #" in cmd:
        cmd = cmd.split(" #", 1)[0].strip()
    if not cmd or len(cmd) > _MAX_CMD_LEN:
        return None
    return cmd


def unwrap_fact_code_fence(text: str) -> str:
    """If the answer is a code fence of command *output*, return plain text.

    Unwrap only path-like / fact output (e.g. ``/home/...``). Keep real command
    examples (``pwd``, ``ls -la``) as fences so the UI can show Copy/Run.
    Rate-limit footers (``—\\nЛимит …``) are preserved.
    """
    raw = (text or "").strip()
    if not raw:
        return text

    footer = ""
    body = raw
    foot = re.search(r"\n\n—\n", raw)
    if foot:
        body = raw[: foot.start()].rstrip()
        footer = raw[foot.start() :]

    if not body.startswith("```"):
        return text

    m = re.fullmatch(
        r"```([\w+-]*)[^\S\n]*\n(.*)\n```",
        body,
        flags=re.DOTALL,
    )
    if not m:
        m = re.fullmatch(
            r"```([\w+-]*)[^\S\n]*\n(.*?)```",
            body,
            flags=re.DOTALL,
        )
    if not m:
        return text

    lang = (m.group(1) or "").strip().lower()
    inner = (m.group(2) or "").strip()
    if not inner:
        return text
    if lang in {"python", "py", "javascript", "js", "ts", "json", "yaml", "yml", "diff"}:
        return text
    lines = [ln.rstrip() for ln in inner.splitlines() if ln.strip()]
    if not lines:
        return text

    # Command examples must stay fenced (Copy/Run). Only unwrap output-looking bodies.
    shellish_prefix = (
        "sudo ",
        "cd ",
        "ls ",
        "cat ",
        "echo ",
        "export ",
        "for ",
        "if ",
        "while ",
        "git ",
        "eurika ",
        "python ",
        "pip ",
    )
    _bare_cmds = frozenset(
        {
            "pwd",
            "ls",
            "ll",
            "whoami",
            "hostname",
            "uname",
            "date",
            "id",
            "env",
            "df",
            "free",
            "ps",
            "top",
            "clear",
            "history",
        }
    )
    for ln in lines:
        s = ln.lstrip()
        if s.startswith("$") or s.startswith(shellish_prefix):
            return text
        first = s.split(None, 1)[0] if s.split() else ""
        if first in _bare_cmds or first.startswith("./"):
            return text

    if len(lines) == 1 and (lines[0].startswith("/") or lines[0].startswith("~")):
        plain = f"Текущий каталог: {lines[0]}"
    elif all(
        ln.startswith("/") or ln.startswith("~") or bool(re.match(r"^[\w./:-]+\s*[:=]", ln))
        for ln in lines
    ):
        plain = inner
    else:
        return text

    return f"{plain}{footer}" if footer else plain


def _cmds_from_block_body(body: str) -> List[str]:
    """Extract command lines; tolerate a leading ``eurika-cmds:`` header inside the body."""
    lines = str(body or "").splitlines()
    out: List[str] = []
    for line in lines:
        raw = line.strip()
        if _INLINE_TOOL_HEADER.match(raw):
            after = raw.split(":", 1)[1].strip() if ":" in raw else ""
            if after:
                cmd = _normalize_candidate_cmd(after)
                if cmd and cmd not in out:
                    out.append(cmd)
            continue
        cmd = _normalize_candidate_cmd(line)
        if not cmd:
            continue
        if cmd.lower().replace("_", "-") in {"eurika-cmds", "eurika-cmd"}:
            continue
        if cmd not in out:
            out.append(cmd)
        if len(out) >= _MAX_CMDS:
            break
    return out


def extract_eurika_cmds(text: str) -> List[str]:
    """Parse tool calls, including common LLM malformations of the protocol fence."""
    if not (text or "").strip():
        return []
    out: List[str] = []

    def _add(cmds: Sequence[str]) -> None:
        nonlocal out
        for cmd in cmds:
            if cmd not in out:
                out.append(cmd)
            if len(out) >= _MAX_CMDS:
                return

    for block in _TOOL_FENCE.findall(text):
        _add(_cmds_from_block_body(block))
        if len(out) >= _MAX_CMDS:
            return out

    for lang, body in _GENERIC_FENCE.findall(text):
        lang_l = (lang or "").strip().lower().replace("_", "-")
        if lang_l in {"eurika-cmds", "eurika-cmd"}:
            continue
        # Keep real code samples for Copy/Run — never auto-execute them.
        if lang_l in {
            "python",
            "py",
            "javascript",
            "js",
            "ts",
            "json",
            "yaml",
            "yml",
            "diff",
            "html",
            "css",
            "rust",
            "go",
            "java",
            "c",
            "cpp",
        }:
            continue
        body_s = str(body or "")
        if _INLINE_TOOL_HEADER.search(body_s) or body_s.strip().lower().startswith("eurika"):
            _add(_cmds_from_block_body(body_s))
        if len(out) >= _MAX_CMDS:
            return out

    if not out and _INLINE_TOOL_HEADER.search(text or ""):
        lines = (text or "").splitlines()
        capture = False
        buf: List[str] = []
        for line in lines:
            if _INLINE_TOOL_HEADER.match(line.strip()):
                capture = True
                after = line.split(":", 1)[1].strip() if ":" in line else ""
                if after:
                    buf.append(after)
                continue
            if capture:
                if not line.strip() or line.strip().startswith("```"):
                    break
                buf.append(line)
        _add(_cmds_from_block_body("\n".join(buf)))

    if not out:
        bare = (text or "").strip().strip("`").strip()
        if "\n" not in bare and _BARE_FILE_READ.match(bare):
            _add([bare])
        elif "\n" not in bare and _BARE_PYTHON_PRINT.match(bare) and not host_command_mutates_workspace(bare):
            _add([bare])

    return out


def has_tool_call(text: str) -> bool:
    """True if the model attempted a host tool call (even with an empty body)."""
    if not (text or "").strip():
        return False
    if _TOOL_FENCE.search(text):
        return True
    if extract_eurika_cmds(text):
        return True
    if _INLINE_TOOL_HEADER.search(text):
        return True
    for lang, body in _GENERIC_FENCE.findall(text):
        lang_l = (lang or "").strip().lower().replace("_", "-")
        body_s = str(body or "")
        if lang_l in {"eurika-cmds", "eurika-cmd"}:
            return True
        if _INLINE_TOOL_HEADER.search(body_s) or body_s.strip().lower().startswith("eurika-cmds"):
            return True
    return False


def strip_tool_calls(text: str) -> str:
    """Drop protocol fences (canonical and malformed) from the user-visible answer."""

    def _sub_generic(m: re.Match[str]) -> str:
        lang = (m.group(1) or "").strip().lower().replace("_", "-")
        body = m.group(2) or ""
        if lang in {"eurika-cmds", "eurika-cmd"}:
            return ""
        if _INLINE_TOOL_HEADER.search(body) or body.strip().lower().startswith("eurika-cmds"):
            return ""
        if body.strip().lower().startswith("eurika_cmds"):
            return ""
        return m.group(0)

    out = _GENERIC_FENCE.sub(_sub_generic, text or "")
    if _INLINE_TOOL_HEADER.search(out):
        lines = out.splitlines()
        kept: List[str] = []
        skip = False
        for line in lines:
            if _INLINE_TOOL_HEADER.match(line.strip()):
                skip = True
                continue
            if skip:
                if not line.strip() or line.strip().startswith("```"):
                    skip = False
                    if line.strip().startswith("```"):
                        kept.append(line)
                continue
            kept.append(line)
        out = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def message_asks_market_learning(message: str) -> bool:
    """True when the user is asking about paper Market results / learning."""
    return bool(_MARKET_ASK_RE.search(message or ""))


def message_asks_llm_teacher_stats(message: str) -> bool:
    """True when the user asks for settled LLM teacher win/loss counts."""
    return bool(_LLM_TEACHER_ASK_RE.search(message or ""))


def message_asks_llm_teacher_execution(message: str) -> bool:
    """True when the user asks if paper MLP ever traded on LLM advice."""
    return bool(_LLM_TEACHER_EXEC_ASK_RE.search(message or ""))


def llm_teacher_execution_prompt_facts() -> str:
    try:
        from eurika.ml.llm_teacher_stats import format_llm_teacher_execution_report
        from eurika.ml.root import resolve_market_root

        root = resolve_market_root()
        block = format_llm_teacher_execution_report(root)
        return (
            f"[LLM execution facts — root={root}]\n{block}\n"
            "Правило ответа: paper MLP не исполняет LLM; назови 0 llm-tagged trades и архитектуру. "
            "Не запускай rg/python/shell для этого."
        )
    except Exception as exc:
        return f"[LLM execution facts]\n{type(exc).__name__}: {exc}"


def llm_teacher_prompt_facts() -> str:
    """Inject LLM teacher aggregate stats (no shell)."""
    try:
        from eurika.ml.llm_teacher_stats import format_llm_teacher_stats_report
        from eurika.ml.root import resolve_market_root

        root = resolve_market_root()
        block = format_llm_teacher_stats_report(root, refresh=False)
        return (
            f"[LLM teacher facts — root={root}]\n{block}\n"
            "Правило ответа: назови n+ / n− / graded из таблицы; не запускай python/cat/shell. "
            "Не путай всего строк в файле с числом прибыльных прогнозов."
        )
    except Exception as exc:
        return f"[LLM teacher facts]\nне удалось прочитать: {type(exc).__name__}: {exc}"


def market_learning_prompt_facts() -> str:
    """Inject live paper facts from the stable Market root (no shell, no Path('.'))."""
    try:
        from eurika.ml.learning_status import (
            format_market_learning_report,
            market_economic_verdict,
            market_learning_status,
        )
        from eurika.ml.root import resolve_market_root

        root = resolve_market_root()
        st = market_learning_status(root)
        verdict = market_economic_verdict(st)
        block = format_market_learning_report(st)
        return (
            f"[Market facts — root={root}]\n{block}\n"
            f"Правило ответа: экономический вердикт = «{verdict.get('label')}». "
            f"Следующий шаг = «{verdict.get('next_step')}». "
            "Ответ пользователю — полный markdown с таблицами из блока выше "
            "(банк, live, тени, открытые, головы, ворота, LLM-учитель). "
            "Не сжимай в 3 абзаца и не выкидывай таблицы. "
            "Не смягчай убыток словами «неплохо/хорошо»; accuracy сама по себе не успех. "
            "Не предлагай «пересмотреть стратегию», новый entry или explore on только из-за "
            "отрицательного банка — это экзамен под воротами. "
            "Не запускай python/cat для этих фактов — они уже выше."
        )
    except Exception as exc:
        return (
            f"[Market facts]\nне удалось прочитать статус: {type(exc).__name__}: {exc}"
        )


def looks_like_ungrounded_host_advice(text: str) -> bool:
    """True when the model tells the user how to inspect the host instead of inspecting it."""
    raw = text or ""
    if extract_eurika_cmds(raw):
        return False
    return bool(_ADVICE_WITHOUT_TOOLS.search(raw))


def message_asks_host_uplinks(message: str) -> bool:
    """True when the user asks which network links are up (Wi‑Fi/VPN), not which ports listen."""
    return bool(_UPLINK_ASK_RE.search(message or ""))


def commands_are_socket_inventory(commands: Sequence[str]) -> bool:
    """True when every command is netstat/ss/lsof (ports), none are nmcli/ip/iw."""
    cmds = [str(c).strip() for c in (commands or []) if str(c).strip()]
    if not cmds:
        return False
    if any(_UPLINK_CMD_RE.search(c) for c in cmds):
        return False
    return all(_SOCKET_CMD_RE.search(c) for c in cmds)


def _os_release_pretty() -> str:
    path = Path("/etc/os-release")
    if not path.is_file():
        return ""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return ""
    return ""


def host_identity_prompt_facts() -> str:
    """Cheap live OS identity so the model does not invent macOS/Windows."""
    uname = ""
    try:
        r = subprocess.run(
            ["uname", "-srm"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        uname = (r.stdout or "").strip()
    except Exception:
        uname = ""
    pretty = _os_release_pretty()
    lines = ["[Host identity]"]
    if uname:
        lines.append(f"  uname: {uname}")
    if pretty:
        lines.append(f"  os: {pretty}")
    if not uname and not pretty:
        lines.append("  os: Linux (Qt Chat host)")
    lines.append(
        "Это Linux-хост. Не предполагай macOS/Windows. "
        "Текущие соединения, устройства, процессы, диски — только через ```eurika-cmds``` "
        "(nmcli / ip / ss / iw / lsblk), затем ответь по выводу. "
        "Не советуй Activity Monitor и не проси пользователя запускать команды."
    )
    return "\n".join(lines)


def tool_protocol_instructions(experience_snippet: str | None = None) -> str:
    """Prompt fragment describing host_shell / project facts. No binary allowlist."""
    base = (
        "Инструмент host_shell (Linux, cwd = корень текущего проекта). "
        "Если для ответа нужны факты о машине ИЛИ о проекте "
        "(сеть, устройства, процессы, ls, дерево, git status/diff, файлы в .eurika/) — "
        "не угадывай и не читай лекции: первый ответ — блок ```eurika-cmds``` с 1–5 "
        "командами, по одной в строке (можно пайпы и обычный shell). Я выполню их сам "
        "и верну вывод; после этого ответь своими словами строго по этому выводу. "
        "Не пиши «вы можете использовать netstat/ifconfig» и не упоминай Activity Monitor "
        "или macOS — хост Linux (см. [Host identity]). "
        "Успехи/статус обучения market ML — НЕ через `eurika scan` (это запахи кода). "
        "Если в промпте уже есть блок [Market facts] — опирайся на него и НЕ дублируй "
        "python/cat для learning_status. Иначе читай факты так: "
        f"`{_MARKET_LEARNING_CMD}` "
        "и/или `cat .eurika/ml/weights/meta.json .eurika/ml/weights/exit_meta.json "
        ".eurika/ml/weights/entry_cost_gate.json .eurika/ml/paper_portfolio.json` "
        "(только в корне Eurika / EURIKA_MARKET_ROOT). "
        "Судьбу paper суди по строке «вердикт:» / equity Δ / net edge после fee — "
        "не по accuracy. Убыток ≠ «неплохие результаты». "
        "Отвечай на языке пользователя (для русского — только русский, без смеси языков). "
        "Коммит/push не делай через eurika-cmds (`git add`/`commit`/`push` будут "
        "отказаны). Пользователь пишет «собери коммит» / «запушь» / "
        "«закоммить и запушь» — HITL покажет файлы и сообщение, затем «применяй». "
        "Не пиши в файлы проекта из eurika-cmds (нет `>`, `tee`, `rm`, `sed -i`, "
        "Path.write_text): такие команды будут отказаны. Правки кода — через "
        "предложение diff / «применяй», не через shell. "
        "Обычные примеры кода показывай в ```bash``` / ```python``` — их увидит "
        "пользователь (Copy/Run), они НЕ запускаются автоматически. "
        "Сравнение файлов/ролей — таблицей GitHub (`| колонка |`), Qt рисует сетку; "
        "не собирай таблицу пробелами и ASCII-рамкой. "
        "Вопрос про внешний сайт / «посмотри в интернете» + http(s) URL — не открывай "
        "локальные docs/ проекта (URL с /docs/ — это не наш каталог). "
        "Если в промпте есть [Web page: …] или «Результаты поиска» — ответь по ним; "
        "не повторяй curl по 300+ КБ Next.js-каркаса без цен. "
        "cursor.com/docs и /pricing — SPA: plain curl не видит таблицы; "
        "используй уже подставленный web search или скажи открыть Settings → Models. "
        "Не проси пользователя запускать команды вручную, если можешь сделать это "
        "через eurika-cmds. Если команде нужны права root, UI может запросить пароль "
        "или продолжить с ограничениями без sudo.\n"
        "ВАЖНО: бинарного allowlist НЕТ. Запрещено выдумывать отказы вида "
        "«команды вне allowlist» и списки вроде amixer/bluetoothctl/wpctl — это устарело. "
        "Нужен факт (например pwd, nmcli, ip addr) → сразу блок ровно в таком виде "
        "(язык = eurika-cmds, команды со следующей строки, без слова eurika-cmds "
        "внутри тела):\n"
        "```eurika-cmds\nls -la\n```\n"
        "Рекурсивный поиск по репозиторию: не ходи в .venv / node_modules / .mypy_cache; "
        "лучше `rg -n PATTERN eurika tests` или grep с --exclude-dir=.venv."
    )
    # Skeleton teaching (not user phrase→reply YAML): which tools answer which questions.
    bootstrap = (
        "[Скелет опыта tool-loop]\n"
        "- вопрос про успехи/статус обучения market ML → "
        f"`{_MARKET_LEARNING_CMD}` "
        "(не `eurika scan`); если [Market facts] уже в промпте — не повторяй команду\n"
        "- текущие сетевые соединения/интерфейсы хоста → "
        "`nmcli device status`, `nmcli connection show --active`, "
        "`ip -br addr`, `ip route` "
        "(не ss -tuln, не lsof, не netstat — это порты; не Activity Monitor, не ifconfig)"
    )
    parts = [base, bootstrap]
    snippet = (experience_snippet or "").strip()
    if snippet:
        parts.append(snippet)
    return "\n\n".join(parts)


_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_.-]{3,}")
_STOP_TOKENS = frozenset(
    {
        "the",
        "and",
        "для",
        "что",
        "как",
        "это",
        "есть",
        "или",
        "при",
        "покажи",
        "скажи",
        "проект",
        "проекте",
        "через",
        "можно",
        "нужно",
        "про",
        "где",
        "мне",
        "мой",
        "моя",
    }
)


def _tokenize_for_tool_exp(text: str) -> set[str]:
    toks = {t.lower() for t in _TOKEN_RE.findall(text or "")}
    return {t for t in toks if t not in _STOP_TOKENS}


def infer_tool_turn_hint(
    message: str,
    commands: Sequence[str],
    *,
    answer: str | None = None,
) -> str:
    """Short outcome hint from commands (and optional answer) — not a phrase book."""
    del message  # reserved for future answer-grounded hints; keep API stable
    blob = "\n".join(str(c) for c in (commands or [])).lower()
    ans = (answer or "").lower()
    hay = blob + "\n" + ans
    if (
        "format_market_learning_block" in hay
        or "format_market_learning_report" in hay
        or "learning_status" in hay
        or "entry_cost_gate" in hay
        or "weights/meta.json" in hay
    ):
        return "успехи/статус обучения market ML (не eurika scan)"
    if re.search(r"\bgit\s+(status|diff)\b", blob) or "git status" in blob or "git diff" in blob:
        return "git status/diff (read-only)"
    if re.search(r"\b(ls|find|tree)\b", blob) or "project-tree" in blob:
        return "список/дерево файлов проекта"
    if "pwd" in blob or "whoami" in blob or "hostnamectl" in blob:
        return "факт о машине/окружении"
    if re.search(r"\b(nmcli|ip\s+(?:-br\s+)?addr|ip\s+route|iw\s+dev|\bss\b)\b", blob):
        return "текущие сетевые соединения/интерфейсы хоста"
    first = str(commands[0]).strip() if commands else ""
    if first:
        return f"команды: {first[:80]}"
    return "tool-loop"


def record_tool_turn(
    project_root: Path,
    *,
    message: str,
    commands: Sequence[str],
    exit_code: int,
    ok: bool,
    answer: str | None = None,
) -> None:
    """Append a successful/failed tool-loop turn for later self-learning (not YAML)."""
    root = Path(project_root).resolve()
    cmds = [str(c).strip() for c in (commands or []) if str(c).strip()]
    if not cmds:
        return
    try:
        eurika = root / ".eurika"
        eurika.mkdir(parents=True, exist_ok=True)
        hint = infer_tool_turn_hint(message, cmds, answer=answer)
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": "tool_turn",
            "ok": bool(ok),
            "exit_code": int(exit_code),
            "message": (message or "")[:240],
            "commands": cmds[:8],
            "outcome_hint": hint[:160],
        }
        path = eurika / "chat_tool_turns.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _score_tool_turn(row: dict, query_tokens: set[str]) -> int:
    if not query_tokens:
        return 0
    hay = " ".join(
        [
            str(row.get("message") or ""),
            str(row.get("outcome_hint") or ""),
            " ".join(str(c) for c in (row.get("commands") or [])),
        ]
    ).lower()
    score = 0
    for tok in query_tokens:
        if tok in hay:
            score += 2 if len(tok) >= 5 else 1
    # Prefer turns that already solved ML-learning without scan when query smells like it.
    if {"обучен", "обучения", "ml", "маркет", "market"}.intersection(query_tokens):
        if (
            "format_market_learning_block" in hay
            or "format_market_learning_report" in hay
            or "learning_status" in hay
        ):
            score += 6
        if "eurika scan" in hay and "не eurika scan" not in hay:
            score -= 4
    if {"соединен", "соединения", "сеть", "wifi", "wlan", "nmcli"}.intersection(query_tokens):
        if "nmcli" in hay or "ip -br" in hay or "ip route" in hay:
            score += 6
        if "activity monitor" in hay or "macos" in hay:
            score -= 4
    return score


def load_tool_turn_experience(
    project_root: Path,
    *,
    message: str | None = None,
    limit: int = 5,
) -> str:
    """Relevant successful tool turns from `.eurika/chat_tool_turns.jsonl` for the prompt."""
    path = Path(project_root).resolve() / ".eurika" / "chat_tool_turns.jsonl"
    if not path.is_file():
        return ""
    rows: List[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    row = json.loads(ln)
                except Exception:
                    continue
                if isinstance(row, dict) and row.get("ok") and row.get("commands"):
                    rows.append(row)
    except Exception:
        return ""
    if not rows:
        return ""
    n = max(1, int(limit))
    query_tokens = _tokenize_for_tool_exp(message or "")
    scored: List[tuple[int, int, dict]] = []
    for idx, row in enumerate(rows):
        scored.append((_score_tool_turn(row, query_tokens), idx, row))
    # Highest score first; among equals prefer newer (higher idx).
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    relevant = [r for s, _i, r in scored if s > 0][:n]
    if len(relevant) < n:
        recent = list(reversed(rows[-n:]))
        seen = {id(r) for r in relevant}
        for row in recent:
            if id(row) in seen:
                continue
            relevant.append(row)
            if len(relevant) >= n:
                break
    if not relevant and not query_tokens:
        relevant = rows[-n:]
    lines = ["[Опыт tool-loop — релевантные удачные ходы, образец, не догма]"]
    for row in relevant[:n]:
        msg = str(row.get("message") or "").replace("\n", " ").strip()
        cmds = row.get("commands") or []
        cmd_s = " ; ".join(str(c) for c in cmds[:4])
        hint = str(row.get("outcome_hint") or "").strip()
        if not (msg and cmd_s):
            continue
        line = f"- «{msg[:120]}» → `{cmd_s}`"
        if hint:
            line += f"  ({hint})"
        lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else ""


def _pack_observations(observations: Sequence[str], budget: int = _MAX_OBS) -> str:
    """Fit tool outputs into the prompt budget without chopping off command heads."""
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


def _trim_out(out: str) -> str:
    text = (out or "").strip() or "(empty)"
    if len(text) > _MAX_OUT:
        return text[:_MAX_OUT] + "\n…"
    return text


def _looks_like_privilege_error(exit_code: int, output: str) -> bool:
    if _PERM_HINT.search(output or ""):
        return True
    return exit_code in (1, 13, 126) and bool(
        re.search(r"denied|not permitted|root", output or "", re.I)
    )


def _strip_sudo_prefix(cmd: str) -> tuple[bool, str]:
    s = (cmd or "").strip()
    if s.lower().startswith("sudo "):
        return True, s[5:].lstrip()
    if s.lower() == "sudo":
        return True, ""
    return False, s


def run_host_command(
    cmd: str,
    *,
    password: str | None = None,
    use_sudo: bool = False,
    timeout: float = 60.0,
    cwd: str | None = None,
) -> HostCommandResult:
    """Run ``cmd`` under ``bash -c`` (not login shell); optionally via ``sudo -S``."""
    raw = (cmd or "").strip()
    if not raw:
        return HostCommandResult(126, "(empty command)")
    wants_sudo, body = _strip_sudo_prefix(raw)
    if not body:
        return HostCommandResult(126, "(empty command after sudo)")
    body = harden_host_command(body)
    run_sudo = bool(use_sudo or wants_sudo or (password is not None and password != ""))
    work = cwd if cwd else None
    try:
        if run_sudo:
            # Never echo the sudo prompt into captured output.
            r = subprocess.run(
                ["sudo", "-S", "-p", "", "bash", "-c", body],
                input=((password or "") + "\n"),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=work,
            )
        else:
            r = subprocess.run(
                ["bash", "-c", body],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=work,
            )
        out = _trim_out((r.stdout or "") + (r.stderr or ""))
        return HostCommandResult(int(r.returncode), out, used_sudo=run_sudo)
    except subprocess.TimeoutExpired:
        return HostCommandResult(-1, f"(timeout: {body})", used_sudo=run_sudo)
    except Exception as exc:
        return HostCommandResult(-1, f"({type(exc).__name__}: {exc})", used_sudo=run_sudo)


def _default_privilege_prompt(_cmd: str, _hint: str) -> Tuple[PrivilegeAction, str]:
    """Headless default: keep limited output, do not block automation/tests."""
    return "continue", ""


def run_host_command_with_privilege(
    cmd: str,
    *,
    privilege_prompt: Optional[PrivilegePrompt] = None,
    timeout: float = 60.0,
    cwd: str | None = None,
) -> HostCommandResult:
    """Run command; on permission errors ask how to proceed (password / continue / skip)."""
    ask = privilege_prompt or _default_privilege_prompt
    wants_sudo, body = _strip_sudo_prefix(cmd)
    if not body:
        return HostCommandResult(126, "(empty command)")

    if wants_sudo:
        action, password = ask(
            body,
            "Команда запрошена с sudo. Введите пароль, продолжите без повышенных "
            "прав (возможны ограничения) или пропустите команду.",
        )
        if action == "skip":
            return HostCommandResult(
                126,
                "(пропущено: нужны права sudo, пользователь отказался)",
                privilege_note="skipped",
            )
        if action == "password":
            return run_host_command(
                body, password=password, use_sudo=True, timeout=timeout, cwd=cwd
            )
        # continue without sudo
        result = run_host_command(body, use_sudo=False, timeout=timeout, cwd=cwd)
        result.privilege_note = (
            "выполнено без sudo (возможны ограничения: часть данных недоступна)"
        )
        if result.output and result.privilege_note not in result.output:
            result.output = f"{result.output}\n[{result.privilege_note}]"
        return result

    result = run_host_command(body, use_sudo=False, timeout=timeout, cwd=cwd)
    if result.exit_code == 0 or not _looks_like_privilege_error(result.exit_code, result.output):
        return result

    action, password = ask(
        body,
        "Команда выполнена с ограничениями или отказано в доступе.\n"
        f"Вывод: {result.output[:400]}\n\n"
        "Ввести пароль sudo и повторить, продолжить с этим ограниченным выводом "
        "или пропустить?",
    )
    if action == "skip":
        return HostCommandResult(
            result.exit_code,
            result.output + "\n(пропущено повтор с sudo)",
            privilege_note="skipped",
        )
    if action == "password":
        elevated = run_host_command(
            body, password=password, use_sudo=True, timeout=timeout, cwd=cwd
        )
        elevated.privilege_note = "retried with sudo"
        return elevated
    result.privilege_note = "continued without sudo"
    if "[возможны ограничения" not in result.output:
        result.output = (
            f"{result.output}\n"
            "[продолжено без sudo — возможны ограничения прав доступа]"
        )
    return result


# Compat alias used by older tests/call sites.
def run_safe_host_command(
    cmd: str, *, timeout: float = 20.0, cwd: str | None = None
) -> Tuple[int, str]:
    r = run_host_command_with_privilege(cmd, timeout=timeout, cwd=cwd)
    return r.exit_code, r.output


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
    privilege_prompt: Optional[PrivilegePrompt] = None,
    cwd: str | None = None,
    user_message: str | None = None,
) -> Tuple[ToolLoopResult, Optional[str]]:
    """Run LLM ↔ host_shell until the model answers without asking for tools."""
    ask = call or _llm_call
    steps = max(1, int(max_iters))
    observations: List[str] = []
    log_parts: List[str] = []
    executed: List[str] = []
    worst = 0
    text = ""
    workdir = str(cwd) if cwd else None
    allowlist_nudge = (
        "ОШИБКА: бинарного allowlist больше нет. Не пиши отказы «вне allowlist» и не "
        "перечисляй amixer/bluetoothctl/wpctl. Нужен факт о машине — выведи блок "
        "```eurika-cmds``` с командами (например pwd), по одной в строке."
    )

    def _run_cmds(cmds: Sequence[str]) -> List[str]:
        nonlocal worst
        if not log_parts:
            log_parts.append("=== HOST TOOL LOOP ===")
        obs: List[str] = []
        for cmd in cmds:
            if host_command_mutates_workspace(cmd):
                msg = (
                    f"$ {cmd}\n(exit 126)\n"
                    "отказ: команда меняет файлы. Чтение — sed/grep/python -c print; "
                    "правка кода — diff / «применяй», не redirect и не write_text."
                )
                executed.append(cmd)
                log_parts.append(msg)
                obs.append(msg)
                if worst == 0:
                    worst = 126
                continue
            result = run_host_command_with_privilege(
                cmd,
                privilege_prompt=privilege_prompt,
                timeout=60.0,
                cwd=workdir,
            )
            display = cmd
            if result.used_sudo and not cmd.strip().lower().startswith("sudo "):
                display = f"sudo {cmd}"
            executed.append(display)
            log_parts.append(f"$ {display}\n{result.output}")
            note = f" [{result.privilege_note}]" if result.privilege_note else ""
            obs.append(f"$ {display}\n(exit {result.exit_code}){note}\n{result.output}")
            if result.exit_code not in (0, 127) and worst == 0:
                worst = result.exit_code
        return obs

    def _finalize(answer: str) -> ToolLoopResult:
        cleaned = unwrap_fact_code_fence(strip_tool_calls(answer))
        return ToolLoopResult(cleaned, "\n\n".join(log_parts), executed, worst)

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
            return _finalize(text), err
        cmds = extract_eurika_cmds(text)
        if not cmds and not has_tool_call(text):
            if (
                not executed
                and _FAKE_ALLOWLIST.search(text)
                and not final_step
                and allowlist_nudge not in observations
            ):
                observations.append(allowlist_nudge)
                continue
            if (
                not executed
                and looks_like_ungrounded_host_advice(text)
                and not final_step
                and _ADVICE_NUDGE not in observations
            ):
                observations.append(_ADVICE_NUDGE)
                continue
            break
        if final_step:
            break
        if not cmds:
            observations.append(
                "Блок ```eurika-cmds``` пуст или не содержит команд. "
                "Выведи реальные команды (по одной в строке) или ответь текстом без блока."
            )
            continue
        observations.append("\n\n".join(_run_cmds(cmds)))
        if (
            not final_step
            and message_asks_host_uplinks(user_message or "")
            and commands_are_socket_inventory(executed)
            and _UPLINK_NUDGE not in observations
        ):
            observations.append(_UPLINK_NUDGE)

    if not executed and _FAKE_ALLOWLIST.search(text or ""):
        recovery = (
            f"{base_prompt}\n\n[Система]\n{allowlist_nudge}\n"
            "Сейчас выведи только ```eurika-cmds``` с нужными командами."
        )
        raw, err = ask(recovery, max_tokens)
        if err:
            return ToolLoopResult("", "\n\n".join(log_parts), executed, 1), err
        text = raw or ""
        cmds = extract_eurika_cmds(text)
        if cmds:
            obs = _run_cmds(cmds)
            final_prompt = (
                f"{base_prompt}\n\n[Вывод выполненных команд]\n"
                f"{_pack_observations(obs)}\n\n{_GROUND_FACTS}"
            )
            raw2, err2 = ask(final_prompt, max_tokens)
            if err2:
                return _finalize(text), err2
            text = raw2 or text
        elif _FAKE_ALLOWLIST.search(text):
            text = (
                "Не удалось получить факты о хосте: модель повторила устаревший allowlist. "
                "Нажми Clear в чате и спроси ещё раз (например: «какой сейчас pwd?»)."
            )

    if not executed and looks_like_ungrounded_host_advice(text or ""):
        recovery = (
            f"{base_prompt}\n\n[Система]\n{_ADVICE_NUDGE}\n"
            "Сейчас выведи только ```eurika-cmds``` с нужными командами."
        )
        raw, err = ask(recovery, max_tokens)
        if err:
            return ToolLoopResult("", "\n\n".join(log_parts), executed, 1), err
        text = raw or ""
        cmds = extract_eurika_cmds(text)
        if cmds:
            obs = _run_cmds(cmds)
            final_prompt = (
                f"{base_prompt}\n\n[Вывод выполненных команд]\n"
                f"{_pack_observations(obs)}\n\n{_GROUND_FACTS}"
            )
            raw2, err2 = ask(final_prompt, max_tokens)
            if err2:
                return _finalize(text), err2
            text = raw2 or text

    return _finalize(text), None
