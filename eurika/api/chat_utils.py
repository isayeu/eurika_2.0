"""Chat file ops and formatting (P0.4 split from chat.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    """Write content to root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith("/"):
        return (False, "invalid path")
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, "path outside project")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))


def safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Delete file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith("/"):
        return (False, "invalid path")
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, "path outside project")
        if not path.is_file():
            return (False, "not a file or does not exist")
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        path.unlink()
        return (True, rel)
    except Exception as e:
        return (False, str(e))


def safe_create_empty_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Create empty file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith("/"):
        return (False, "invalid path")
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, "path outside project")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))


def syntax_lang_for_path(rel_path: str) -> str:
    """Return language hint for code block based on file extension."""
    ext = (rel_path.split(".")[-1] or "").lower()
    return {
        "py": "python",
        "md": "markdown",
        "mdc": "markdown",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "toml": "toml",
        "ini": "ini",
        "cfg": "ini",
        "sh": "bash",
        "bash": "bash",
    }.get(ext, "text")


def read_file_for_chat(root: Path, rel_path: str) -> tuple[bool, str]:
    """Read file under project root. Returns (ok, content_or_error)."""
    try:
        root_res = root.resolve()
        path = (root / rel_path).resolve()
        try:
            path.relative_to(root_res)
        except ValueError:
            return (False, "Путь выходит за пределы проекта.")
        if not path.is_file():
            return (False, f"Файл не найден: {rel_path}")
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 30000:
            content = content[:30000] + "\n\n... (обрезано, файл >30k символов)"
        return (True, content)
    except Exception as e:
        return (False, f"Не удалось прочитать: {e}")


def format_execution_report(report: Dict[str, Any]) -> str:
    """Render structured execution report text for chat output."""
    ok = bool(report.get("ok"))
    summary = str(report.get("summary") or ("done" if ok else "failed"))
    applied = list(report.get("applied_steps") or [])
    skipped = list(report.get("skipped_steps") or [])
    changed = list(report.get("artifacts_changed") or [])
    verification = report.get("verification") or {}
    error = report.get("error")
    lines = [("Готово" if ok else "Не удалось") + f": {summary}."]
    if applied:
        lines.append("Applied steps: " + ", ".join((str(x) for x in applied)))
    if skipped:
        lines.append("Skipped steps: " + ", ".join((str(x) for x in skipped)))
    if changed:
        lines.append("Changed: " + ", ".join((str(x) for x in changed)))
    if isinstance(verification, dict) and verification:
        lines.append("Verification: " + ("OK" if verification.get("ok") else "FAIL"))
        out = str(verification.get("output") or "").strip()
        if out:
            lines.append(out[:1200])
    if error:
        lines.append(f"Error: {error}")
    return "\n".join(lines)


def format_doctor_report_for_chat(root: Path) -> str:
    """Format eurika_doctor_report.json for chat display."""
    doctor_path = root / "eurika_doctor_report.json"
    fix_path = root / "eurika_fix_report.json"
    if not doctor_path.exists() and not fix_path.exists():
        return "Отчёт не найден. Сначала выполни `eurika scan .` и `eurika doctor .`."
    try:
        from report.report_snapshot import format_report_snapshot

        return format_report_snapshot(root)
    except Exception:
        pass
    if doctor_path.exists():
        try:
            doc = json.loads(doctor_path.read_text(encoding="utf-8"))
            lines: List[str] = ["## Отчёт Doctor (eurika_doctor_report.json)\n"]
            summary = doc.get("summary", {}) or {}
            sys_info = summary.get("system", {}) or {}
            lines.append(f"- **Модули:** {sys_info.get('modules', '?')}")
            lines.append(f"- **Зависимости:** {sys_info.get('dependencies', '?')}")
            lines.append(f"- **Циклы:** {sys_info.get('cycles', 0)}")
            risks = summary.get("risks", [])[:8]
            if risks:
                lines.append("- **Риски:**")
                for r in risks:
                    lines.append(f"  - {r}")
            arch = (doc.get("architect") or "").strip()
            if arch:
                lines.append(f"\n**Architect:** {arch[:800]}" + ("..." if len(arch) > 800 else ""))
            ops = doc.get("operational_metrics") or {}
            if ops:
                lines.append(
                    f"\n**Метрики:** apply_rate={ops.get('apply_rate')}, rollback_rate={ops.get('rollback_rate')}"
                )
            return "\n".join(lines)
        except Exception:
            return "Не удалось прочитать eurika_doctor_report.json."
    if fix_path.exists():
        try:
            fix = json.loads(fix_path.read_text(encoding="utf-8"))
            lines = ["## Отчёт Fix (eurika_fix_report.json)\n"]
            mod = fix.get("modified", [])
            sk = fix.get("skipped", [])
            lines.append(f"- **Modified:** {len(mod)}")
            lines.append(f"- **Skipped:** {len(sk)}")
            v = fix.get("verify", {}) or {}
            lines.append(f"- **Verify:** {v.get('success', 'N/A')}")
            return "\n".join(lines)
        except Exception:
            return "Не удалось прочитать eurika_fix_report.json."
    return "Отчёт не найден."


def format_root_ls(root: Path, limit: int = 120) -> str:
    """Render ls-like listing for project root."""
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return f"Не удалось прочитать корень проекта: {e}"
    lines: List[str] = []
    for p in entries[:limit]:
        name = p.name
        suffix = "/" if p.is_dir() else ""
        lines.append(name + suffix)
    if len(entries) > limit:
        lines.append(f"... ещё {len(entries) - limit}")
    return "\n".join(lines) if lines else "(пусто)"


def format_project_tree(root: Path, max_depth: int = 3, limit: int = 500) -> str:
    """Render project tree for chat."""

    def _walk(d: Path, depth: int, prefix: str, acc: List[str]) -> None:
        if depth <= 0 or len(acc) >= limit:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for i, p in enumerate(entries):
            if len(acc) >= limit:
                return
            is_last = i == len(entries) - 1
            branch = "└── " if is_last else "├── "
            name = p.name + ("/" if p.is_dir() else "")
            acc.append(prefix + branch + name)
            if p.is_dir() and depth > 1:
                sub_prefix = prefix + ("    " if is_last else "│   ")
                _walk(p, depth - 1, sub_prefix, acc)

    acc: List[str] = []
    _walk(root, max_depth, "", acc)
    return "\n".join(acc) if acc else "(пусто)"


def brief_release_check_analysis(output: str, ok: bool) -> str:
    """Extract brief analysis from release check output for chat."""
    import re

    if ok:
        return "**Release check пройден.** Всё работает."
    parts: list[str] = []
    failed = re.findall(r"FAILED\s+(tests/[^\s]+)", output)
    if failed:
        unique = list(dict.fromkeys(failed))[:5]
        parts.append(f"тесты: {', '.join(unique)}")
    if "ruff" in output.lower() and ("error" in output.lower() or "failed" in output.lower()):
        parts.append("ruff: ошибки стиля/импортов")
    if "mypy" in output.lower() and ("error" in output.lower() or "fail" in output.lower()):
        parts.append("mypy: нужны аннотации типов")
    if not parts:
        if output.strip():
            parts.append("См. вывод ниже.")
        else:
            parts.append("Вывод пуст.")
    return f"**Release check не прошёл.**\n\nОшибки: {'; '.join(parts)}\n\nСкажи «исправь» или «пофикси» для правок."


def grounded_ui_tabs_text() -> str:
    """Static text for ui_tabs response. Matches Qt main_window tab names."""
    tabs = ["Commands", "Dashboard", "Approvals", "Models", "Chat"]
    return "В текущем Qt UI есть вкладки: " + ", ".join(f"`{name}`" for name in tabs) + "."


def enforce_eurika_persona(text: str) -> str:
    """Replace base model mentions with Eurika identity."""
    import re

    out = text
    for pat, repl in [
        (r"\bQwen\b", "Eurika"),
        (r"\bLlama\b", "Eurika"),
        (r"\bOllama\b", "Eurika"),
        (r"\bOpenAI\b", "Eurika"),
        (r"\bGPT-\d+\b", "Eurika"),
    ]:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out


def infer_default_save_target(message: str) -> str:
    """Infer default save target from message."""
    msg = (message or "").strip().lower()
    if "app.py" in msg or "main.py" in msg:
        return "app.py" if "app.py" in msg else "main.py"
    return "app.py"
