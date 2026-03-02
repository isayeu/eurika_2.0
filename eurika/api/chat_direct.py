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
    """Detect explicit confirmation to execute a pending action."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    markers = ("применяй", "выполняй", "это подтверждение", "apply", "go ahead", "execute")
    return any(m in msg for m in markers)


def extract_confirmation_token(message: str) -> str:
    """Extract optional confirmation token from message."""
    msg = str(message or "")
    m = re.search(r"(?:token|токен)\s*[:=]?\s*([a-fA-F0-9]{8,32})", msg)
    return str(m.group(1)) if m else ""


def is_reject_confirmation(message: str) -> bool:
    """Detect explicit rejection/cancel for pending plan."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    markers = ("отклонить", "отмена", "cancel", "reject")
    return any(m in msg for m in markers)


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


def resolve_direct_handler(root: Path, msg: str) -> tuple[Optional[str], Optional[str]]:
    """Resolve direct handler from config or legacy. Returns (handler_id, emit_cmd)."""
    from eurika.api.chat_intents_config import match_direct_intent

    matched = match_direct_intent(root, msg)
    if matched:
        return matched
    if is_identity_question(msg):
        return ("identity", None)
    if is_ls_request(msg):
        return ("project_ls", "$ ls -la")
    if is_tree_request(msg):
        return ("project_tree", "$ eurika project-tree .")
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
    if is_ritual_request(msg):
        return ("ritual", "$ eurika scan . && eurika doctor . && eurika report-snapshot .")
    if is_release_check_request(msg):
        return ("release_check", "$ ./scripts/release_check.sh")
    if is_git_commit_request(msg):
        return ("git_commit", None)
    return (None, None)


def is_identity_question(message: str) -> bool:
    """Detect direct "who are you?" questions."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    patterns = (r"^ты\s+кто\??$", r"^кто\s+ты\??$", r"^who\s+are\s+you\??$", r"^what\s+are\s+you\??$")
    return any(re.match(p, msg) for p in patterns)


def is_ls_request(message: str) -> bool:
    """Detect explicit request to run ls/list in project root."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    return (
        any(k in msg for k in (" ls ", "команду ls", "выполни ls", "run ls", "execute ls", "list root", "list files"))
        or msg == "ls"
    )


def is_show_report_request(message: str) -> bool:
    """Detect request to show scan/doctor report."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    keywords = (
        "покажи отчет",
        "покажи отчёт",
        "сформируй отчет",
        "сформируй отчёт",
        "посмотри результат",
        "покажи результат",
        "report",
        "отчет",
        "отчёт",
        "doctor report",
        "scan report",
        "результат scan",
        "результат doctor",
    )
    return any(k in msg for k in keywords)


def is_show_file_request(message: str) -> bool:
    """Detect request to show/read file contents."""
    msg = (message or "").strip()
    if not msg:
        return False
    lower = msg.lower()
    triggers = (
        "покажи файл",
        "покажи содержимое",
        "открой файл",
        "прочитай файл",
        "show file",
        "read file",
        "open file",
        "покажи ",
        "открой ",
    )
    if not any(t in lower for t in triggers):
        return False
    return "." in msg or "/" in msg


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
    msg = (message or "").strip().lower()
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
    msg = (message or "").strip().lower()
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


def is_ritual_request(message: str) -> bool:
    """Detect request to run Ritual 2.1: scan → doctor → report-snapshot."""
    msg = (message or "").strip().lower()
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


def is_git_commit_request(message: str) -> bool:
    """Detect request for git status/diff/commit."""
    msg = (message or "").strip().lower()
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
        "git status",
        "git diff",
        "покажи status",
        "покажи diff",
    )
    if any(k in msg for k in keywords):
        return True
    if re.match(r"^\s*commit\s*$", msg) or re.match(r"^\s*коммит\s*$", msg):
        return True
    return False


def extract_commit_message_from_request(message: str) -> Optional[str]:
    """Extract explicit commit message from user message."""
    msg_raw = (message or "").strip()
    patterns = [
        r'(?:в\s+сообщении\s+напиши|напиши\s+в\s+сообщении|сообщение\s+напиши)\s*[:=]\s*["\']?([^"\'\n]+)',
        r'(?:с\s+сообщением|with\s+message|message\s*[:=])\s*["\']?([^"\'\n]+)["\']?',
    ]
    for pat in patterns:
        m = re.search(pat, msg_raw, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def infer_commit_message_via_llm(
    user_message: str, status_out: str, diff_snippet: str
) -> Optional[str]:
    """Infer commit message from user intent via LLM. Fallback-safe."""
    if not user_message or not user_message.strip():
        return None
    prompt = f"""User wants to commit. Their message: "{user_message.strip()[:500]}"
Changed files (git status): {status_out[:600]}
Diff snippet: {diff_snippet[:800]}

Reply with ONLY the commit message (1-2 lines), no quotes, no explanation. Convey what the user asked for."""
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


def propose_commit_message_from_status(status_out: str) -> str:
    """Derive a simple commit message from git status output."""
    lines = [l.strip() for l in (status_out or "").splitlines() if l.strip()]
    if not lines:
        return "Update project"
    files = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            files.append(parts[-1])
    if not files:
        return "Update project"
    if len(files) == 1:
        return f"Update {Path(files[0]).name}"
    return f"Update {len(files)} files"


def is_tree_request(message: str) -> bool:
    """Detect request for actual directory structure."""
    msg = (message or "").strip().lower()
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
        "tree",
        "project structure",
        "folder structure",
    )
    if any(k in msg for k in explicit):
        return True
    has_structure_word = re.search(r"\bструктур\w*\b", msg) is not None
    has_question_marker = any(k in msg for k in ("?", "какая", "покажи", "фактическ", "полную"))
    return has_structure_word and has_question_marker


def is_saved_file_path_request(message: str) -> bool:
    """Detect explicit request for full path of recently saved file."""
    msg = (message or "").strip().lower()
    if not msg:
        return False
    full_path_markers = ("полный путь", "full path", "absolute path")
    file_markers = ("файл", "file", ".py")
    show_markers = ("покажи", "show", "дай", "where")
    return any(m in msg for m in full_path_markers) and (
        any(m in msg for m in file_markers) or any(m in msg for m in show_markers)
    )
