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
_GROUND_FACTS = (
    "Больше команд не запускай. Ответь пользователю ТОЛЬКО по фактам из "
    "[Вывод выполненных команд] выше. Не выдумывай CPU/GPU, диски, вендоров и "
    "устройства, которых нет в выводе. Если данных нет — так и скажи. "
    "Ответ — обычным текстом (1–5 предложений), БЕЗ блоков ```bash``` / ```code``` "
    "и без повторного eurika-cmds: не оформляй вывод команд как code fence."
)
# Canonical tool fence.
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


def tool_protocol_instructions(experience_snippet: str | None = None) -> str:
    """Prompt fragment describing host_shell / project facts. No binary allowlist."""
    base = (
        "Инструмент host_shell (Linux, cwd = корень текущего проекта). "
        "Если для ответа нужны факты о машине ИЛИ о проекте "
        "(ls, дерево, git status/diff, файлы в .eurika/) — не угадывай: "
        "выведи блок ```eurika-cmds``` с 1–5 командами, по одной в строке "
        "(можно пайпы и обычный shell). Я выполню их сам и верну вывод; после этого "
        "ответь своими словами строго по этому выводу. "
        "Успехи/статус обучения market ML — НЕ через `eurika scan` (это запахи кода). "
        "Читай факты обучения, например: "
        "`python -c \"from pathlib import Path; from eurika.ml.learning_status import format_market_learning_block; print(format_market_learning_block(Path('.')))\"` "
        "и/или `cat .eurika/ml/weights/meta.json .eurika/ml/weights/exit_meta.json "
        ".eurika/ml/weights/entry_cost_gate.json .eurika/ml/paper_portfolio.json`. "
        "Отвечай на языке пользователя (для русского — только русский, без смеси языков). "
        "Коммит/push/запись файлов через git commit — не делай сам: опиши план "
        "и дождись подтверждения «применяй». "
        "Обычные примеры кода показывай в ```bash``` / ```python``` — их увидит "
        "пользователь (Copy/Run), они НЕ запускаются автоматически. "
        "Не проси пользователя запускать команды вручную, если можешь сделать это "
        "через eurika-cmds. Если команде нужны права root, UI может запросить пароль "
        "или продолжить с ограничениями без sudo.\n"
        "ВАЖНО: бинарного allowlist НЕТ. Запрещено выдумывать отказы вида "
        "«команды вне allowlist» и списки вроде amixer/bluetoothctl/wpctl — это устарело. "
        "Нужен факт (например pwd или ls) → сразу блок ровно в таком виде "
        "(язык = eurika-cmds, команды со следующей строки, без слова eurika-cmds "
        "внутри тела):\n"
        "```eurika-cmds\nls -la\n```"
    )
    # Skeleton teaching (not user phrase→reply YAML): which tools answer ML-learning questions.
    bootstrap = (
        "[Скелет опыта tool-loop]\n"
        "- вопрос про успехи/статус обучения market ML → "
        "`python -c \"from pathlib import Path; from eurika.ml.learning_status "
        "import format_market_learning_block; print(format_market_learning_block(Path('.')))\"` "
        "(не `eurika scan`)"
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
        if "format_market_learning_block" in hay or "learning_status" in hay:
            score += 6
        if "eurika scan" in hay and "не eurika scan" not in hay:
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

    return _finalize(text), None
