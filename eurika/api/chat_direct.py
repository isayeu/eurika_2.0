"""Direct handler detection and extraction (P0.4 split from chat.py)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

SCAFFOLD_TEST_API_SERVE = '''"""Tests for eurika.api.serve API endpoints."""

from pathlib import Path

import pytest

from eurika.api import serve as api_serve


class _DummyHandler:
    """Minimal handler stub for tests."""

'''


def _norm_msg(m: str) -> str:
    """Normalize message for legacy pattern matching."""
    from eurika.api.chat_intents_config import normalize_intent_text

    return normalize_intent_text(m)


def run_eurika_fix(project_root: Path, dry_run: bool = False, timeout: int = 180) -> str:
    """Run eurika fix . in project; return stdout+stderr. ROADMAP 3.5.11.C."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "eurika_cli", "fix", str(project_root), "--quiet"]
            + (["--dry-run"] if dry_run else []),
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        suffix = f" (exit {r.returncode})" if r.returncode != 0 else ""
        return (out or "(no output)").strip() + suffix
    except subprocess.TimeoutExpired:
        return "eurika fix: timeout"
    except Exception as e:
        return f"eurika fix: {e}"


def is_apply_confirmation(message: str) -> bool:
    """Detect explicit confirmation to execute a pending action.

    Avoid bare substring ``apply`` — it false-positives on commit texts like
    ``собери коммит: Gate Apply after Diff``. Long eval briefs that mention
    the HITL verb inside instructions are not confirms (same gate as reject).
    """
    raw = (message or "").strip()
    if not raw:
        return False
    if len(raw) > 96 or "\n" in raw:
        return False
    msg = _norm_msg(raw)
    if not msg:
        return False
    # Commit/push intents win over HITL apply (message may contain the word Apply).
    if is_git_commit_request(raw) or is_git_push_request(raw):
        return False
    if any(m in msg for m in ("применяй", "выполняй", "это подтверждение")):
        return True
    # English: leading confirm verb, or confirm + token — not mid-sentence nouns.
    if re.match(r"^(apply|go ahead|execute)\b", msg):
        return True
    if re.search(r"\b(apply|execute)\b.{0,48}\btoken\b", msg):
        return True
    return False


def extract_confirmation_token(message: str) -> str:
    """Extract optional confirmation token from message."""
    msg = str(message or "")
    m = re.search(r"(?:token|токен)\s*[:=]?\s*([a-fA-F0-9]{8,32})", msg)
    return str(m.group(1)) if m else ""


def is_reject_confirmation(message: str) -> bool:
    """Detect explicit rejection/cancel for pending plan.

    Long eval/find briefs may mention Apply/Reject as nouns — those are not rejects.
    """
    raw = (message or "").strip()
    if not raw:
        return False
    if len(raw) > 96 or "\n" in raw:
        return False
    msg = _norm_msg(raw)
    markers = ("отклонить", "отмена", "cancel", "reject")
    return any(m in msg for m in markers)


def is_short_affirmation(message: str) -> bool:
    """Yes/да after a pending clarify (e.g. scan typo suggest)."""
    raw = (message or "").strip()
    if not raw or len(raw) > 40:
        return False
    msg = _norm_msg(raw)
    if re.match(r"^(да|ага|угу|ок|okay|ok|yes|y|конечно|верно|точно)[.!…]*$", msg):
        return True
    # Also accept repeating the intended skill.
    if is_scan_request(raw) or re.match(r"^(просканируй|сканируй)[.!…]*$", msg):
        return True
    return False


def is_short_negation(message: str) -> bool:
    """No/нет to dismiss a pending clarify without HITL reject markers only."""
    raw = (message or "").strip()
    if not raw or len(raw) > 24:
        return False
    msg = _norm_msg(raw)
    return bool(re.match(r"^(нет|не|no|n|Nope)[.!…]*$", msg, re.IGNORECASE))


def apply_add_empty_tab_after_chat(root: Path) -> tuple[bool, str]:
    """Apply deterministic edit: add `New Tab` after Chat in Qt UI."""
    target = root / "qt_app" / "ui" / "main_window.py"
    if not target.exists():
        return (False, "target file not found: qt_app/ui/main_window.py")
    try:
        src = target.read_text(encoding="utf-8")
    except OSError as e:
        return (False, f"failed to read target file: {e}")
    if 'self.tabs.addTab(tab, "New Tab")' in src:
        return (True, "tab already exists (no changes required)")
    anchor = 'self.tabs.addTab(tab, "Chat")'
    pos = src.find(anchor)
    if pos < 0:
        return (False, 'anchor not found: self.tabs.addTab(tab, "Chat")')
    line_end = src.find("\n", pos)
    if line_end < 0:
        line_end = len(src)
    insert = '\n        self.tabs.addTab(tab, "New Tab")'
    updated = src[:line_end] + insert + src[line_end:]
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as e:
        return (False, f"failed to write target file: {e}")
    return (True, 'added empty tab `New Tab` after `Chat`')


def run_qt_smoke_test(project_root: Path, timeout: int = 120) -> str:
    """Run minimal Qt smoke test after UI edit."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_qt_smoke.py"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            return f"qt smoke: OK\n{out or '(no output)'}"
        return f"qt smoke: FAIL (exit {r.returncode})\n{out or '(no output)'}"
    except subprocess.TimeoutExpired:
        return "qt smoke: timeout"
    except Exception as e:
        return f"qt smoke: {e}"


_QUESTION_START = re.compile(
    r"^(кто|что|как|зачем|почему|чем|где|какой|какие|каков|в\s*ч[её]м|who|when|why|what|how|where|which)\s",
    re.IGNORECASE,
)


_SHELL_FIRST_TOKENS = frozenset(
    {
        "sudo",
        "pwd",
        "ls",
        "ll",
        "cd",
        "cat",
        "head",
        "tail",
        "whoami",
        "id",
        "uname",
        "hostname",
        "hostnamectl",
        "df",
        "du",
        "free",
        "ps",
        "top",
        "htop",
        "echo",
        "printf",
        "grep",
        "rg",
        "find",
        "which",
        "whereis",
        "env",
        "printenv",
        "export",
        "date",
        "git",
        "python",
        "python3",
        "pip",
        "pip3",
        "npm",
        "node",
        "cargo",
        "make",
        "cmake",
        "docker",
        "systemctl",
        "journalctl",
        "ip",
        "ss",
        "curl",
        "wget",
        "chmod",
        "chown",
        "mkdir",
        "rm",
        "rmdir",
        "cp",
        "mv",
        "touch",
        "ln",
        "tar",
        "zip",
        "unzip",
        "mount",
        "umount",
        "ping",
        "nvidia-smi",
        "lspci",
        "lsusb",
        "lsblk",
        "true",
        "false",
        "test",
        "bash",
        "sh",
        "zsh",
        "eurika",
        "wc",
        "sort",
        "uniq",
        "tee",
        "xargs",
        "sed",
        "awk",
    }
)


def is_bare_shell_request(message: str) -> bool:
    """True when the user pasted a shell command (not Russian prose / chat question).

    Examples: ``pwd``, ``sudo whoami``, ``ls -la``. Counter-examples: «какой pwd?»,
    «покажи пример в блоке bash: pwd», ``remember my name``, ``please refactor``.
    """
    s = (message or "").strip()
    if not s or len(s) > 400:
        return False
    if re.search(r"[а-яА-ЯёЁ]{3,}", s):
        return False
    if _QUESTION_START.search(s) or is_llm_directive_message(s):
        return False
    lines = [
        ln.strip().lstrip("$ ").strip()
        for ln in s.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines or len(lines) > 5:
        return False
    for ln in lines:
        if len(ln) > 240:
            return False
        parts = ln.split()
        if not parts:
            return False
        first = parts[0]
        if first == "sudo":
            if len(parts) < 2:
                return False
            # ``sudo -u root whoami`` — skip flags until a token.
            idx = 1
            while idx < len(parts) and parts[idx].startswith("-"):
                # sudo -u NAME CMD
                if parts[idx] in {"-u", "-g", "-h", "-p"} and idx + 1 < len(parts):
                    idx += 2
                else:
                    idx += 1
            if idx >= len(parts):
                return False
            first = parts[idx]
        if "/" in first or first.startswith("./") or first.startswith("~/"):
            continue
        if first in _SHELL_FIRST_TOKENS:
            continue
        return False
    return True


# Free-form LLM instructions must not be fuzzy-mapped to project_overview/ritual/etc.
_LLM_DIRECTIVE = re.compile(
    r"(?:"
    r"^(?:ответь|скажи|напиши|повтори|выведи|произнеси|reply|say|write|respond|answer)\b"
    r"|одним\s+слов"
    r"|одной\s+фраз"
    r"|in\s+one\s+word"
    r"|only\s+(?:the\s+)?word\b"
    r"|verbatim"
    r")",
    re.IGNORECASE,
)

# Soft-match may invent web_search; require an explicit internet cue.
_WEB_SEARCH_MARKERS = (
    "в интернете",
    "посмотри в интернете",
    "открой в интернете",
    "погугли",
    "загугли",
    "web search",
    "search the web",
    "search online",
    "find on the internet",
    "интернет-поиск",
    "интернет поиск",
    "поищи в интернет",
    "найди в интернет",
)


def is_llm_directive_message(message: str) -> bool:
    """True when the user asks the model to produce free-form text (not a project command)."""
    msg = (message or "").strip()
    if not msg:
        return False
    return bool(_LLM_DIRECTIVE.search(msg))


def looks_like_web_search_request(message: str) -> bool:
    """True only when the user explicitly asked for an internet search."""
    msg = _norm_msg(message)
    if not msg:
        return False
    return any(m in msg for m in _WEB_SEARCH_MARKERS)


def _extract_http_urls(message: str) -> list[str]:
    try:
        from eurika.utils.web_search import extract_http_urls

        return extract_http_urls(message)
    except Exception:
        return []


def looks_like_http_url_question(message: str) -> bool:
    """Explicit http(s) URL + question — treat as external page, not local docs/."""
    if not _extract_http_urls(message):
        return False
    msg = _norm_msg(message)
    cues = (
        "какая",
        "какой",
        "какие",
        "сколько",
        "what",
        "which",
        "how much",
        "cheapest",
        "дешев",
        "дешёв",
    )
    return any(c in msg for c in cues)


def looks_like_cursor_pricing_question(message: str) -> bool:
    """Cursor model/pricing questions (with or without URL)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    product = any(x in msg for x in ("cursor", "курсор", "composer"))
    price = any(
        x in msg
        for x in (
            "дешев",
            "дешёв",
            "cheapest",
            "дорог",
            "прайс",
            "pricing",
            "стоим",
            "тариф",
            "модел",
            "model",
        )
    )
    return product and price


def looks_like_web_page_question(message: str) -> bool:
    """External page question → prefetch/search + LLM, not list_docs."""
    if looks_like_cursor_pricing_question(message):
        return True
    if looks_like_http_url_question(message):
        return True
    if not looks_like_web_search_request(message):
        return False
    try:
        from eurika.utils.web_search import extract_http_urls

        return bool(extract_http_urls(message))
    except Exception:
        return False


def is_read_terminal_request(message: str) -> bool:
    """User asks to interpret Terminal tab output (follow-up after host tools)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    cues = (
        "прочти терминал",
        "посмотри терминал",
        "посмотри вывод терминал",
        "прочитай терминал",
        "что в терминале",
        "что показал терминал",
        "read terminal",
        "read the terminal",
        "terminal output",
    )
    return any(c in msg for c in cues)


def looks_like_market_ml_scope_request(message: str) -> bool:
    """Hard cues for «одна модель vs per-ticker» — not bare «разбор тикера BTC».

    Bare «тикер»/«ticker» alone is too broad: ticker analysis asks share that
    word and must not soft-accept into the architecture FAQ.
    """
    msg = _norm_msg(message)
    if not msg:
        return False
    cues = (
        "per-ticker",
        "per ticker",
        "market_policy",
        "общая модель",
        "одна модель",
        "отдельная модель",
        "как учится market",
        "как учится ml",
        "shared market",
        "policy на все",
        "на каждый тикер",
        "каждого тикера",
        "по разным тикерам",
        "стратегию каждого",
        "в целом для рынка",
        "в отдельности",
    )
    return any(c in msg for c in cues)


def _accept_soft_handler(handler_id: Optional[str], msg: str) -> bool:
    """Reject soft matches that need hard lexical cues (e.g. web_search)."""
    if not handler_id:
        return False
    # Bare shell lines (``sudo whoami``, ``pwd``) must not become list_docs via fuzzy ML.
    if is_bare_shell_request(msg):
        return False
    # Env toggles / ls must never come from ML or vector fuzzy match.
    if handler_id.startswith(("ml_intent_", "vector_intent_")):
        return False
    if handler_id in {"project_ls", "project_tree", "git_push"}:
        return False
    if handler_id == "web_search" and not looks_like_web_search_request(msg):
        return False
    # Soft/vector must not invent release_check / ritual / scan without explicit cues.
    if handler_id == "release_check" and not is_release_check_request(msg):
        return False
    if handler_id == "ritual" and not is_ritual_request(msg):
        return False
    if handler_id == "polygon_propose" and not is_polygon_propose_request(msg):
        return False
    if handler_id == "scan" and not is_scan_request(msg) and not looks_like_scan_typo(msg):
        return False
    if handler_id == "roadmap_verify" and not is_roadmap_verify_request(msg):
        return False
    if handler_id == "host_health" and not is_host_health_request(msg):
        return False
    if handler_id == "self_check" and is_host_health_request(msg):
        return False
    if handler_id == "self_check" and not is_os_env_check_request(msg):
        # Soft path only reaches here; require explicit self-check/env cues.
        return False
    # Soft/vector must never invent goal/docs rituals or persona/count templates.
    if handler_id in {
        "goal_reflection",
        "goal_status",
        "clear_goal",
        "continue_dev",
        "docs_audit",
        "identity",
        "greeting",
        "capabilities",
        "file_recount",
    }:
        return False
    if handler_id == "list_docs":
        if looks_like_web_search_request(msg):
            return False
        try:
            from eurika.utils.web_search import extract_http_urls

            if extract_http_urls(msg):
                return False
        except Exception:
            pass
        n = _norm_msg(msg)
        if not any(
            x in n
            for x in (
                "документ",
                "docs",
                "readme",
                "правил",
                "documentation",
                "документац",
            )
        ):
            return False
    if handler_id == "project_overview" and not is_project_overview_request(msg):
        return False
    if handler_id == "market_ml_scope" and not looks_like_market_ml_scope_request(msg):
        return False
    if handler_id in {
        "market_situation",
        "market_ticker_brief",
        "portfolio_agent_once",
        "portfolio_agent_status",
        "market_logic",
        "session_digest",
        "ml_status",
        "market_learning_report",
        "llm_teacher_execution",
        "llm_teacher_stats",
        "llm_shadow_report",
    }:
        return False
    # Host OS phrases must not soft-map to project skills.
    if is_host_health_request(msg) and handler_id in {
        "scan",
        "docs_audit",
        "list_docs",
        "roadmap_next",
        "roadmap_verify",
        "project_overview",
        "ritual",
        "goal_reflection",
    }:
        return False
    if handler_id == "show_file" and not is_show_file_request(msg):
        return False
    if handler_id == "add_api_test" and not is_add_api_test_request(msg):
        return False
    if handler_id == "add_module_test" and not is_add_module_test_request(msg):
        return False
    if handler_id == "git_commit" and not is_git_commit_request(msg) and not is_git_commit_and_push_request(msg):
        return False
    # Soft/vector must not map scan typos (scsn) to unrelated skills like list_docs.
    if looks_like_scan_typo(msg) and handler_id != "scan":
        return False
    return True


# Read-only project facts go through LLM tool-loop (eurika-cmds), not templates.
_LLM_TOOL_LOOP_FACTS = frozenset({"project_ls", "project_tree"})


def resolve_direct_handler(root: Path, msg: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve direct handler from config or legacy. Returns (handler_id, emit_cmd)."""
    from eurika.api.chat_intent_detectors import detect_run
    from eurika.api.chat_intents_config import match_direct_intent

    # Never fuzzy-route HITL confirmations (vector may map «отклонить» → show_report).
    if is_reject_confirmation(msg) or is_apply_confirmation(msg):
        return (None, None)
    # Explicit commit/push must beat incidental ROADMAP/phase text supplied
    # as the desired commit-message context. Force push is refused in the handler.
    if is_force_push_request(msg):
        return ("git_push", None)
    if is_git_commit_and_push_request(msg) or is_git_commit_request(msg):
        return ("git_commit", None)
    if is_git_push_request(msg):
        return ("git_push", None)
    # A concrete test request belongs to the run_tests executor. Without this
    # guard the vector matcher may turn an arbitrary test path into qt smoke.
    detected_run = detect_run(msg, msg.lower())
    if detected_run is not None and detected_run[0] == "run_tests":
        return (None, None)
    matched = match_direct_intent(root, msg)
    if matched:
        hid = matched[0]
        # YAML may still list status phrases under git_commit — demote those.
        if hid in _LLM_TOOL_LOOP_FACTS:
            pass
        elif hid == "git_commit" and not is_git_commit_request(msg) and not is_git_commit_and_push_request(msg):
            pass
        elif hid == "roadmap_verify" and not is_roadmap_verify_request(msg):
            pass
        elif hid == "web_search" and looks_like_web_page_question(msg):
            pass
        else:
            return matched
    if is_read_terminal_request(msg):
        return ("read_terminal", None)
    if looks_like_cursor_pricing_question(msg) and not _extract_http_urls(msg):
        return ("web_search", None)
    if looks_like_web_search_request(msg) and not looks_like_web_page_question(msg):
        return ("web_search", None)
    # Factual handlers before soft-match — otherwise "что за проект?" goes to LLM.
    if is_identity_question(msg):
        return ("identity", None)
    if is_greeting(msg):
        return ("greeting", None)
    if is_project_overview_request(msg):
        return ("project_overview", None)
    if is_file_recount_request(msg):
        return ("file_recount", None)
    # project_ls / project_tree: demoted to LLM + eurika-cmds (A1 chat-first).
    # Bare ``ls`` / ``ls -la`` still hit host_shell via is_bare_shell_request below.
    if is_scan_request(msg):
        return ("scan", "$ eurika scan .")
    # Typo near scan/скан → clarify (before ML/vector can invent list_docs).
    if looks_like_scan_typo(msg):
        return ("scan_suggest", None)
    if is_saved_file_path_request(msg):
        return ("saved_file_path", None)
    if is_show_report_request(msg):
        return ("show_report", None)
    if is_add_api_test_request(msg):
        return ("add_api_test", None)
    if is_add_module_test_request(msg):
        return ("add_module_test", None)
    if is_show_file_request(msg):
        return ("show_file", None)
    # Hard skills before soft ML/vector — «git commit …» must not become release_check.
    if is_ritual_request(msg):
        return ("ritual", "$ eurika scan . && eurika doctor . && eurika report-snapshot .")
    if is_polygon_propose_request(msg):
        drill = polygon_propose_drill_id(msg)
        cmd = f"$ eurika prove-cycle . --propose --drill {drill}"
        return ("polygon_propose", cmd)
    if is_release_check_request(msg):
        return ("release_check", "$ ./scripts/release_check.sh")
    if is_roadmap_verify_request(msg):
        return ("roadmap_verify", None)
    if is_host_health_request(msg):
        return ("host_health", "$ # host health (read-only probe)")
    # No domain auto-shell: host questions fall through to the LLM tool-loop.
    if is_os_env_check_request(msg):
        return ("self_check", "$ eurika self-check .")
    if is_force_push_request(msg):
        return ("git_push", None)
    if is_git_commit_and_push_request(msg) or (
        is_git_commit_request(msg) and is_git_push_request(msg)
    ):
        return ("git_commit", None)
    if is_git_push_request(msg):
        return ("git_push", None)
    if is_git_commit_request(msg):
        return ("git_commit", None)
    # Soft match (ML/vector) must not steal questions or explicit LLM directives.
    raw = (msg or "").strip()
    if _QUESTION_START.search(raw) or is_llm_directive_message(raw):
        return (None, None)
    # User pasted a shell command — run it (sudo → privilege dialog), do not fuzzy-route.
    if is_bare_shell_request(raw):
        return ("host_shell", None)
    # CR-G3: optional ML intent router (YAML/factual already tried)
    try:
        from eurika.ml.intent_router import match_ml_intent

        ml = match_ml_intent(root, msg)
        if ml and _accept_soft_handler(ml[0], msg):
            return ml
    except Exception:
        pass
    # CR-G2: vector fuzzy match when direct fails (EURIKA_USE_VECTOR_INTENT=1)
    try:
        from eurika.api.chat_vector import match_fuzzy_intent

        fuzzy = match_fuzzy_intent(root, msg)
        if fuzzy and _accept_soft_handler(fuzzy[0], msg):
            return (fuzzy[0], fuzzy[1])
    except Exception:
        pass
    return (None, None)


def is_identity_question(message: str) -> bool:
    """Detect persona / authorship questions («кто ты?», «кто написал программу?»)."""
    from eurika.api.chat_identity import IDENTITY_REGEX_NORM

    msg = _norm_msg(message)
    if not msg:
        return False
    return any(re.match(p, msg) for p in IDENTITY_REGEX_NORM)


def is_greeting(message: str) -> bool:
    """Detect short greetings — answer locally, not via LLM."""
    msg = _norm_msg(message)
    if not msg or len(msg) > 50:
        return False
    patterns = (
        r"^привет[!.…]*$",
        r"^здравствуй",
        r"^добрый\s+(день|вечер|утро)",
        r"^hello[!.]*$",
        r"^hi[!.]*$",
        r"^hey[!.]*$",
        r"^good\s+(morning|evening|afternoon)",
    )
    return any(re.match(p, msg) for p in patterns)


def is_ls_request(message: str) -> bool:
    """Detect explicit request to run ls/list in project root (or show dir contents)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if msg == "ls":
        return True
    keywords = (
        " ls ",
        "команду ls",
        "выполни ls",
        "run ls",
        "execute ls",
        "list root",
        "list files",
        "покажи файлы",
        "содержимое каталог",
        "содержимое папк",
        "содержимое директ",
        "содержимое проект",
        "содержимое корн",
        "что в каталог",
        "что в папк",
        "что в директ",
        "что в корне",
        "list directory",
        "list folder",
        "directory contents",
        "folder contents",
        "покажи каталог",
        "покажи папку",
        "покажи директорию",
        "список файлов",
        "список в корне",
    )
    return any(k in msg for k in keywords)


def is_show_report_request(message: str) -> bool:
    """Detect request to show scan/doctor report."""
    msg = _norm_msg(message)
    if not msg:
        return False
    # Avoid bare «отчет»/«report» — too broad for substring match.
    keywords = (
        "покажи отчет",
        "покажи отчёт",
        "сформируй отчет",
        "сформируй отчёт",
        "посмотри результат",
        "покажи результат",
        "show report",
        "doctor report",
        "scan report",
        "результат scan",
        "результат doctor",
    )
    return any(k in msg for k in keywords)


def is_show_file_request(message: str) -> bool:
    """Detect request to show/read file contents (not directory listing)."""
    msg = (message or "").strip()
    if not msg:
        return False
    if is_ls_request(msg) or is_tree_request(msg):
        return False
    lower = msg.lower()
    # Directory / project contents → project_ls, not show_file.
    if any(
        k in lower
        for k in (
            "каталог",
            "папк",
            "директ",
            "directory",
            "folder",
            "проект",
            "project",
        )
    ) and "файл" not in lower and "file" not in lower:
        # «покажи содержимое каталога проекта» — no explicit file.
        if "содержим" in lower or "содержимое" in lower:
            return False
    triggers = (
        "покажи файл",
        "открой файл",
        "прочитай файл",
        "show file",
        "read file",
        "open file",
        "покажи содержимое файла",
    )
    if any(t in lower for t in triggers):
        return True
    # Legacy: «покажи path/to/file.py» with extension or slash.
    if lower.startswith("покажи ") or lower.startswith("открой "):
        return "." in msg or "/" in msg
    if "покажи содержимое" in lower:
        # Require a path-like token; bare «содержимое» alone is not a file read.
        return ("/" in msg or re.search(r"\.\w{1,8}\b", msg) is not None) and not any(
            k in lower for k in ("каталог", "папк", "директ", "проект", "directory", "folder")
        )
    return False


def extract_file_path_from_show_request(message: str) -> str | None:
    """Extract relative file path from show-file request."""
    msg = (message or "").strip()
    m = re.search(r"(?:^|\s)([./\w][\w./\-]*(?:\.\w+)?)\s*$", msg)
    if m:
        cand = m.group(1).strip()
        if cand and ("/" in cand or cand.startswith(".") or ".py" in cand or ".md" in cand):
            return cand
    for prefix in ("покажи файл ", "show file ", "read file ", "открой файл ", "покажи ", "открой "):
        if prefix in msg.lower():
            rest = msg[msg.lower().find(prefix) + len(prefix) :].strip()
            if rest and ("/" in rest or "." in rest):
                first = rest.split()[0] if rest.split() else rest
                if first and ("/" in first or first.startswith(".")):
                    return first
    return None


def is_add_api_test_request(message: str) -> bool:
    """Detect request to add test for API endpoint."""
    msg = _norm_msg(message)
    if not msg:
        return False
    keywords = (
        "добавь тест",
        "добавить тест",
        "тест для",
        "тест для endpoint",
        "add test",
        "test for",
        "покрой тестами endpoint",
        "покрой тестами /api",
        "тест для /api",
        "test for /api",
    )
    return any(k in msg for k in keywords) and "/api" in msg


def is_add_module_test_request(message: str) -> bool:
    """Detect request to add test for Python module."""
    msg = (message or "").strip()
    if not msg:
        return False
    msg_lower = msg.lower()
    keywords = ("добавь тест", "добавить тест", "тест для", "add test", "test for", "покрой тестами")
    if not any(k in msg_lower for k in keywords):
        return False
    if "/api" in msg_lower:
        return False
    return bool(re.search(r"[\w/]+\.py|[\w.]+\.[\w.]+", msg))


def extract_module_path_from_request(message: str) -> Optional[str]:
    """Extract module path from add-test request."""
    msg = str(message or "").strip()
    m = re.search(r"([\w/]+\.py)", msg)
    if m:
        return m.group(1).replace("\\", "/")
    m = re.search(r"(\b[\w]+(?:\.[\w]+)+)\b", msg)
    if m:
        return m.group(1).replace(".", "/") + ".py"
    return None


def extract_api_endpoint_from_request(message: str) -> Optional[str]:
    """Extract /api/... path from add-test request."""
    msg = str(message or "")
    m = re.search(r"/api/[a-zA-Z0-9_]+", msg)
    return m.group(0) if m else None


def generate_and_append_api_test(root: Path, endpoint: str) -> tuple[bool, str]:
    """Generate test for endpoint and append to tests/test_api_serve.py. CR-B1."""
    POST_BODIES: Dict[str, str] = {
        "/api/approve": '{"operations": []}',
        "/api/exec": '{"command": "eurika scan ."}',
        "/api/chat": '{"message": "hi"}',
        "/api/ask_architect": "{}",
        "/api/operation_preview": '{"operation": {"target_file": "a.py", "kind": "remove_unused_import", "params": {}}}',
    }
    is_post = endpoint in POST_BODIES
    name_part = endpoint.replace("/api/", "").replace("/", "_")
    test_file = root / "tests" / "test_api_serve.py"
    if not test_file.exists():
        try:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(SCAFFOLD_TEST_API_SERVE, encoding="utf-8")
        except Exception as e:
            return (False, f"Не удалось создать {test_file}: {e}")
    body_str = POST_BODIES.get(endpoint, "{}")
    func = "_run_post_handler" if is_post else "_dispatch_api_get"
    args = f'_DummyHandler(), tmp_path, "{endpoint}", {body_str}' if is_post else f'_DummyHandler(), tmp_path, "{endpoint}", {{}}'
    test_code = f'''
def test_{"run_post_handler" if is_post else "dispatch_api_get"}_{name_part}_returns_dict(tmp_path: Path, monkeypatch) -> None:
    """{"POST" if is_post else "GET"} {endpoint} should return dict (CR-B1)."""
    captured: dict[str, object] = {{}}

    def _fake_json_response(_handler, data: dict, status: int = 200) -> None:
        captured["status"] = status
        captured["data"] = data

    monkeypatch.setattr(api_serve, "_json_response", _fake_json_response)
    handled = api_serve.{func}({args})
    assert handled is True
    assert captured.get("status") == 200
    data = captured.get("data") or {{}}
    assert isinstance(data, dict)
'''
    try:
        content = test_file.read_text(encoding="utf-8")
        if f'"{endpoint}"' in content and "tmp_path" in content:
            return (True, f"Тест для {endpoint} уже есть в {test_file.name}.")
        test_file.write_text(content.rstrip() + test_code, encoding="utf-8")
        return (True, f"Добавлен тест для {endpoint} в {test_file.name}.")
    except Exception as e:
        return (False, str(e))


def generate_module_test(root: Path, module_path: str) -> tuple[bool, str]:
    """Create tests/test_<module>.py for given module path."""
    path_normalized = module_path.replace("\\", "/").strip()
    parts = path_normalized.rstrip("/").split("/")
    if not parts:
        return (False, f"Неверный путь к модулю: {module_path}")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if not parts[-1].replace("_", "").replace("-", "").isalnum():
        return (False, f"Имя модуля некорректно: {module_path}")
    module_dot = ".".join(parts)
    test_name = "_".join(parts)
    test_file = root / "tests" / f"test_{test_name}.py"
    src_file = root / (path_normalized if path_normalized.endswith(".py") else f"{path_normalized}.py")
    if not src_file.exists():
        return (False, f"Модуль не найден: {src_file.relative_to(root)}")
    scaffold = f'''"""Tests for {module_dot}."""

import pytest


def test_module_imports():
    """Module should be importable."""
    import {module_dot} as mod
    assert mod is not None
'''
    try:
        if test_file.exists():
            return (True, f"Файл {test_file.name} уже существует.")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(scaffold, encoding="utf-8")
        return (True, f"Добавлен тест для {module_path} в {test_file.relative_to(root)}. Запуск: `pytest {test_file.relative_to(root)} -v`")
    except Exception as e:
        return (False, str(e))


def is_release_check_request(message: str) -> bool:
    """Detect request to run release check (CR-B2)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if re.search(r"^(что|как|зачем|why|what|how)\s", msg):
        return False
    keywords = (
        "прогони release check",
        "прогони release_check",
        "прогони release-check",
        "run release check",
        "запусти release check",
        "выполни release check",
        "release check",
        "release_check",
        "прогони releasecheck",
    )
    return any(k in msg for k in keywords)


def is_roadmap_verify_request(message: str) -> bool:
    """True only with an explicit phase-check command (not a plan-doc mention)."""
    raw = (message or "").strip()
    if not raw:
        return False
    if is_os_env_check_request(raw):
        return False
    msg = _norm_msg(raw)
    if not msg:
        return False
    if re.search(
        r"(?:"
        r"провер(?:ь|ите|ить)\s+фаз|"
        r"verify\s+phase|"
        r"check\s+phase|"
        r"свер(?:ь|ьте|ить|ка|ку|ки|кой)\s+roadmap|"
        r"сверк\w*\s+roadmap|"
        r"roadmap\s+verify|"
        r"verify\s+roadmap|"
        r"проверка\s+фаз"
        r")",
        msg,
        re.I,
    ):
        return True
    return False


def is_host_health_request(message: str) -> bool:
    """Host OS health (Arch/Linux) — not Eurika project self-check."""
    msg = _norm_msg(message)
    if not msg:
        return False
    # Explicit project/env skills win elsewhere; don't steal self-check wording.
    if re.search(r"\bself[-\s]?check\b|eurika\s+self|окружен\w*\s+eurika|статус\s+ml\b", msg):
        return False
    if re.search(
        r"(?:операционк|"
        r"операционн\w*\s+систем|"
        r"здоровь\w*\s+(?:ос\b|системы|систем|хоста|машины)|"
        r"состояни\w*\s+(?:ос\b|системы|систем|хоста)|"
        r"нагрузк\w*\s+(?:на\s+)?(?:систем|ос\b|хост|машин)|"
        r"\barch\b|\barchlinux\b|"
        r"\bжелезо\b|\bhardware\b|"
        r"(?:проверь|проверить)\s+(?:мою\s+|нашу\s+)?(?:ос\b|os\b|хост|сервер)|"
        r"хорошо\s+ли\s+(?:настроен|работает)\s+(?:операцион|систем|хост|машин)|"
        r"host\s+health|os\s+health|system\s+health)",
        msg,
        re.I,
    ):
        return True
    return False


def is_os_env_check_request(message: str) -> bool:
    """Eurika project/env probe via self-check (torch/binance/lbot) — not host OS."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if is_host_health_request(message):
        return False
    if re.search(
        r"(?:self[-\s]?check|"
        r"eurika\s+self|"
        r"окружен\w*\s+(?:eurika|проекта)|"
        r"системн\w*\s+требован|"
        r"проверь\s+окружение\s+проекта)",
        msg,
        re.I,
    ):
        return True
    return False


def is_ritual_request(message: str) -> bool:
    """Detect request to run Ritual 2.1: scan → doctor → report-snapshot."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if re.search(r"(?:выполни|запусти|run|execute)\s+(?:команд[ау]\s+)", msg) or "run command" in msg:
        return False
    keywords = (
        "проведи ритуал",
        "прогони ритуал",
        "запусти ритуал",
        "run ritual",
        "прогони scan",
        "запусти scan doctor",
        "scan doctor",
        "scan → doctor",
        "eurika scan",
        "eurika doctor",
        "report-snapshot",
    )
    return any(k in msg for k in keywords)


def is_polygon_propose_request(message: str) -> bool:
    """C.14 HITL: seed polygon drill into Approvals via prove-cycle --propose."""
    msg = _norm_msg(message)
    if not msg:
        return False
    needles = (
        "prove-cycle --propose",
        "prove cycle --propose",
        "eurika prove-cycle --propose",
        "предложи полигон",
        "полигон эксперимент",
        "полигон-эксперимент",
        "polygon propose",
        "propose polygon",
        "саморазвитие полигон",
        "c.14 полигон",
        "ритуал саморазвития",
        "propose hitl",
        "второй полигон",
        "полигон extract",
        "третий полигон",
        "полигон long",
        "полигон nested",
        "long_function",
        "четвёртый полигон",
        "четвертый полигон",
        "полигон llm",
        "llm_extract",
    )
    if any(n in msg for n in needles):
        return True
    if "prove-cycle" in msg and "propose" in msg:
        return True
    if "полигон" in msg and any(
        w in msg
        for w in ("предложи", "propose", "hitl", "approvals", "extract", "long", "nested", "llm")
    ):
        return True
    return False


def polygon_propose_drill_id(message: str) -> str:
    """Pick prove-cycle --drill for a polygon propose chat phrase."""
    msg = _norm_msg(message)
    llm_needles = (
        "llm_extract",
        "llm extract",
        "--drill llm",
        "drill llm",
        "четвёртый полигон",
        "четвертый полигон",
        "полигон llm",
        "предложи llm",
        "refactor_code_smell",
    )
    if any(n in msg for n in llm_needles):
        return "llm_extract"
    long_needles = (
        "long_function",
        "extract_nested",
        "--drill long",
        "drill long",
        "третий полигон",
        "полигон long",
        "полигон nested",
        "предложи long",
        "предложи nested",
    )
    if any(n in msg for n in long_needles):
        return "long_function"
    extract_needles = (
        "extractable",
        "extract_block",
        "extractable_block",
        "--drill extract",
        "drill extract",
        "второй полигон",
        "полигон extract",
        "предложи extract",
    )
    if any(n in msg for n in extract_needles):
        return "extractable_block"
    return "imports"


def is_force_push_request(message: str) -> bool:
    """True when the user asked for a force push — always refused."""
    msg = _norm_msg(message)
    if not msg:
        return False
    needles = (
        "force push",
        "push --force",
        "push -f",
        "--force-with-lease",
        "force-with-lease",
        "force-пуш",
        "force пуш",
        "пуш с force",
        "форс пуш",
        "форс-пуш",
    )
    return any(k in msg for k in needles)


def is_git_commit_and_push_request(message: str) -> bool:
    """Detect combined commit+push (HITL → apply does both)."""
    span = _command_like_intent_span(message)
    if span is None:
        return False
    msg = _norm_msg(span)
    if not msg:
        return False
    phrases = (
        "commit and push",
        "commit & push",
        "commit+push",
        "закоммить и запушь",
        "закоммить и пуш",
        "собери коммит и запушь",
        "сделай коммит и запушь",
        "создай коммит и запушь",
        "закоммить и отправь",
        "коммит и пуш",
        "коммит и push",
    )
    if any(p in msg for p in phrases):
        return True
    return is_git_commit_request(message) and is_git_push_request(message)


def _command_like_intent_span(message: str) -> str | None:
    """Skill detectors see a short command, not a multi-line eval brief.

    Returns None when the message is a long instruction (find/train), not a skill.
    """
    raw = (message or "").strip()
    if not raw:
        return None
    if "\n" in raw or len(raw) > 200:
        first = raw.split("\n", 1)[0].strip()
        if len(first) > 88:
            return None
        return first
    return raw


def is_git_push_request(message: str) -> bool:
    """Detect git push request (HITL → ``применяй``; never auto-push)."""
    span = _command_like_intent_span(message)
    if span is None:
        return False
    msg = _norm_msg(span)
    if not msg:
        return False
    if re.search(r"^(что|как|зачем|why|what|how)\s", msg):
        return False
    keywords = (
        "git push",
        "запушь",
        "запуш",
        "push в remote",
        "push to remote",
        "отправь на github",
        "отправь в remote",
        "отправь на origin",
    )
    if any(k in msg for k in keywords):
        return True
    return bool(re.match(r"^\s*push\s*$", msg))


def is_git_commit_request(message: str) -> bool:
    """Detect request to prepare/create a commit (HITL → ``применяй``).

    Read-only ``git status`` / ``git diff`` are *not* commit requests — they go
    to the LLM tool-loop (or bare ``host_shell``).
    Long find/eval briefs that mention those words are also not commit skills.
    """
    span = _command_like_intent_span(message)
    if span is None:
        return False
    msg = _norm_msg(span)
    if not msg:
        return False
    keywords = (
        "собери коммит",
        "сделай коммит",
        "создай коммит",
        "закоммить",
        "закоммит",
        "собери commit",
        "сделай commit",
        "commit changes",
        "commit the changes",
        "git commit",
    )
    if any(k in msg for k in keywords):
        return True
    if re.match(r"^\s*commit\s*$", msg) or re.match(r"^\s*коммит\s*$", msg):
        return True
    return False


def is_git_status_request(message: str) -> bool:
    """Detect read-only git status/diff (A1: LLM tool-loop, not commit HITL)."""
    if is_git_commit_request(message) or is_git_push_request(message):
        return False
    msg = _norm_msg(message)
    if not msg:
        return False
    keywords = (
        "git status",
        "git diff",
        "покажи status",
        "покажи diff",
        "покажи git status",
        "покажи git diff",
        "статус репозитория",
        "статус git",
        "git статус",
        "что изменено в git",
        "какие изменения в git",
        "show git status",
        "show git diff",
        "repository status",
    )
    return any(k in msg for k in keywords)

def extract_commit_message_from_request(message: str) -> Optional[str]:
    """Extract explicit commit message from user message."""
    msg_raw = (message or "").strip()
    patterns = [
        r'(?:в\s+сообщении\s+напиши|напиши\s+в\s+сообщении|сообщение\s+напиши)\s*[:=]\s*["\']?([^"\'\n]+)',
        r'(?:с\s+сообщением|with\s+message)\s*[:=]?\s*["\']?([^"\'\n]+)["\']?',
        r'(?:message\s*[:=])\s*["\']?([^"\'\n]+)["\']?',
    ]
    for pat in patterns:
        m = re.search(pat, msg_raw, re.IGNORECASE)
        if m:
            proposed = m.group(1).strip().lstrip(":").strip().strip("\"'")
            return proposed or None
    return None


def infer_commit_message_via_llm(
    user_message: str, status_out: str, diff_snippet: str, log_snippet: str = ""
) -> Optional[str]:
    """Infer commit message from user intent via LLM. Fallback-safe."""
    if not user_message or not user_message.strip():
        return None
    style = (log_snippet or "").strip()[:600]
    style_block = f"\nRecent commit subjects (match this style):\n{style}\n" if style else ""
    prompt = f"""User wants to commit. Their message: "{user_message.strip()[:500]}"
Changed files (git status): {status_out[:600]}
Diff snippet: {diff_snippet[:800]}
{style_block}
Reply with ONLY the commit message (1-2 sentences), no quotes, no explanation.
Focus on WHY, not a file count. Do not mention secrets. Do not write "Update N files"."""
    try:
        from eurika.reasoning.architect import call_llm_with_prompt

        raw, err = call_llm_with_prompt(prompt, max_tokens=80)
        if err or not raw:
            return None
        line = raw.strip().split("\n")[0].strip()
        line = line.strip('"\'`')
        if len(line) > 200:
            line = line[:200].rsplit(" ", 1)[0]
        return line if line else None
    except Exception:
        return None


def _paths_from_git_status(status_out: str) -> list[str]:
    """Best-effort path list from ``git status --short`` (or porcelain-ish) text."""
    files: list[str] = []
    for line in (status_out or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        # short: " M path", "?? path", "R  old -> new"
        if " -> " in raw:
            files.append(raw.split(" -> ", 1)[-1].strip())
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) >= 2 and re.match(r"^[?AMDRCU ]{1,2}$", parts[0].replace("?", "?")):
            # XY path — XY may be "M", "??", "AM"
            path = parts[1].strip()
            if path:
                files.append(path)
            continue
        parts = raw.split()
        if len(parts) >= 2:
            files.append(parts[-1])
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _paths_from_git_diff(diff_out: str) -> list[str]:
    files: list[str] = []
    for line in (diff_out or "").splitlines():
        if line.startswith("+++ b/"):
            p = line[6:].strip()
            if p and p != "/dev/null":
                files.append(p)
        elif line.startswith("diff --git "):
            m = re.search(r" b/(.+)$", line)
            if m:
                files.append(m.group(1).strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _added_symbols_from_diff(diff_out: str, *, limit: int = 5) -> list[str]:
    """Names from newly added def/class lines; prefer public APIs over ``_helpers``."""
    public: list[str] = []
    private: list[str] = []
    for line in (diff_out or "").splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:].strip()
        m = re.match(
            r"^(?:async\s+)?def\s+([A-Za-z_][\w]*)|"
            r"^class\s+([A-Za-z_][\w]*)",
            body,
        )
        if not m:
            continue
        name = m.group(1) or m.group(2)
        if not name:
            continue
        bucket = private if name.startswith("_") else public
        if name not in bucket:
            bucket.append(name)
    # Prefer propose_/format_/handle_/is_/build_ among public
    def _rank(n: str) -> tuple[int, str]:
        for i, pref in enumerate(("propose_", "format_", "handle_", "build_", "is_", "get_")):
            if n.startswith(pref):
                return (i, n)
        return (50, n)

    public_sorted = sorted(public, key=_rank)
    ordered = public_sorted + private
    return ordered[:limit]


def _common_path_prefix(paths: list[str]) -> str:
    """Shared directory prefix for changed paths (at most 3 segments)."""
    if not paths:
        return ""
    parts_list = [Path(p).as_posix().split("/") for p in paths]
    prefix: list[str] = []
    for bits in zip(*parts_list):
        if len(set(bits)) != 1:
            break
        prefix.append(bits[0])
    if len(paths) == 1:
        return "/".join(prefix[:-1][:3]) if len(prefix) > 1 else ""
    if prefix and "." in prefix[-1]:
        prefix = prefix[:-1]
    return "/".join(prefix[:3])


def propose_commit_message_from_status(status_out: str, diff_out: str = "") -> str:
    """Derive a concise commit message from git status and optional diff.

    Avoids weak «Update N files» — prefers area + filenames / new symbols.
    """
    files = _paths_from_git_status(status_out)
    if not files:
        files = _paths_from_git_diff(diff_out)
    if not files:
        return "Update project"

    symbols = _added_symbols_from_diff(diff_out)
    names = [Path(f).name for f in files]
    area = _common_path_prefix(files)

    docs_only = all(
        f.endswith(".md") or f.startswith("docs/") or "/docs/" in f.replace("\\", "/")
        for f in files
    )
    tests_only = all(
        "test" in Path(f).name.lower() or "/tests/" in f.replace("\\", "/")
        for f in files
    )

    if len(files) == 1:
        name = names[0]
        if symbols:
            return f"Update {name}: add {symbols[0]}"
        if docs_only:
            return f"Update docs: {name}"
        return f"Update {name}"

    heads = ", ".join(names[:3])
    more = f" (+{len(files) - 3})" if len(files) > 3 else ""

    if symbols:
        sym = symbols[0]
        if area:
            return f"Update {area}: add {sym}"
        return f"Add {sym} ({heads}{more})"

    if docs_only:
        return f"Update docs ({heads}{more})"
    if tests_only:
        return f"Update tests ({heads}{more})"
    if area:
        return f"Update {area} ({heads}{more})"
    return f"Update {heads}{more}"


def is_project_overview_request(message: str) -> bool:
    """Detect request for structured project description (not free-form LLM chat)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    markers = (
        "что за проект",
        "что за проект открыт",
        "какой проект открыт",
        "что это за проект",
        "что это за",
        "опиши проект",
        "расскажи о проекте",
        "расскажи про проект",
        "какой это проект",
        "какой проект",
        "what is this project",
        "describe the project",
        "about this project",
    )
    return any(m in msg for m in markers)


def is_file_recount_request(message: str) -> bool:
    """Detect request to recount files on disk."""
    msg = _norm_msg(message)
    if not msg:
        return False
    # Allow filler words: «сколько всего там файлов?», «сколько в проекте файлов?»
    if re.search(r"\bсколько\s+(?:\w+\s+){0,6}файл", msg):
        return True
    if re.search(r"\bсколько\s+(?:\w+\s+){0,6}модул", msg):
        return True
    if re.search(r"how\s+many\s+(?:\w+\s+){0,4}files?", msg):
        return True
    # «ты пересчитала все файлы?», «пересчитай заново файлы»
    if re.search(r"(?:пере|под|по)счита\w*\s+(?:\w+\s+){0,6}файл", msg):
        return True
    if "файл" in msg and re.search(r"(?:пере|под|по)счита\w*", msg):
        return True
    markers = (
        "пересчитай файлы",
        "пересчитай файл",
        "пересчитай",
        "пересчитать файлы",
        "подсчитай файлы",
        "подсчитай файл",
        "посчитай файлы",
        "count files",
        "recount files",
    )
    return any(m in msg for m in markers)


def is_scan_request(message: str) -> bool:
    """Detect request to run architectural scan (not file tree)."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if "дерево" in msg or "структур" in msg:
        return False
    # Skip when user is using run_command syntax that just mentions scan.
    if any(
        marker in msg
        for marker in ("выполни команд", "выполнить команд", "execute command", "run command")
    ):
        return False
    # Bare tokens (English/Russian) — common dogfood shortcuts.
    if re.match(r"^(scan|скан|сканируй)[.!?…]*$", msg):
        return True
    keywords = (
        "просканируй",
        "прогони scan",
        "запусти scan",
        "сканируй проект",
        "eurika scan",
        "run scan",
    )
    return any(k in msg for k in keywords)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def looks_like_scan_typo(message: str) -> bool:
    """Single-token near-miss for scan/скан (e.g. scsn) — suggest, don't run wrong skill."""
    raw = (message or "").strip()
    if not raw or len(raw) > 24 or " " in raw or "\n" in raw:
        return False
    msg = _norm_msg(raw)
    if not msg or is_scan_request(msg):
        return False
    # Strip trailing punctuation for distance check.
    token = re.sub(r"[.!?…]+$", "", msg)
    if len(token) < 3 or len(token) > 12:
        return False
    for canon in ("scan", "скан"):
        dist = _levenshtein(token, canon)
        if 1 <= dist <= 2 and abs(len(token) - len(canon)) <= 2:
            return True
    return False


def is_tree_request(message: str) -> bool:
    """Detect request for actual directory structure."""
    msg = _norm_msg(message)
    if not msg:
        return False
    if any(marker in msg for marker in ("цель:", "границы:", "задачи:", "задача:")):
        return False
    explicit = (
        "покажи структ",
        "покажи дерево",
        "какая структура",
        "структуру проекта",
        "фактическую структуру",
        "дерево проекта",
        "дерево файлов",
        "tree",
        "project structure",
        "folder structure",
        "project tree",
    )
    if any(k in msg for k in explicit):
        return True
    if "дерево" in msg and any(k in msg for k in ("покажи", "просканируй", "сканируй", "выведи", "показать", "все")):
        return True
    has_structure_word = re.search(r"\bструктур\w*\b", msg) is not None
    has_question_marker = any(k in msg for k in ("?", "какая", "покажи", "фактическ", "полную"))
    return has_structure_word and has_question_marker


def is_saved_file_path_request(message: str) -> bool:
    """Detect explicit request for full path of recently saved file."""
    msg = _norm_msg(message)
    if not msg:
        return False
    full_path_markers = ("полный путь", "full path", "absolute path")
    file_markers = ("файл", "file", ".py")
    show_markers = ("покажи", "show", "дай", "where")
    return any(m in msg for m in full_path_markers) and (
        any(m in msg for m in file_markers) or any(m in msg for m in show_markers)
    )
