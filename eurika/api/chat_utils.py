"""Chat file ops and formatting (P0.4 split from chat.py)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

def safe_write_file(root: Path, relative_path: str, content: str) -> tuple[bool, str]:
    """Write content to root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))

def safe_delete_file(root: Path, relative_path: str) -> tuple[bool, str]:
    """Delete file at root/relative_path. Prevent path traversal. Return (ok, msg)."""
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        if not path.is_file():
            return (False, 'not a file or does not exist')
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
    if not relative_path or relative_path.startswith('/'):
        return (False, 'invalid path')
    path = (root / relative_path).resolve()
    try:
        allowed_base = root.resolve().parent
        if not path.is_relative_to(allowed_base):
            return (False, 'path outside project')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
        try:
            return (True, str(path.relative_to(root)))
        except ValueError:
            return (True, str(path))
    except Exception as e:
        return (False, str(e))

def syntax_lang_for_path(rel_path: str) -> str:
    """Return language hint for code block based on file extension."""
    ext = (rel_path.split('.')[-1] or '').lower()
    return {'py': 'python', 'md': 'markdown', 'mdc': 'markdown', 'yaml': 'yaml', 'yml': 'yaml', 'json': 'json', 'toml': 'toml', 'ini': 'ini', 'cfg': 'ini', 'sh': 'bash', 'bash': 'bash'}.get(ext, 'text')

def read_file_for_chat(root: Path, rel_path: str) -> tuple[bool, str]:
    """Read file under project root. Returns (ok, content_or_error)."""
    try:
        root_res = root.resolve()
        path = (root / rel_path).resolve()
        try:
            path.relative_to(root_res)
        except ValueError:
            return (False, 'Путь выходит за пределы проекта.')
        if not path.is_file():
            return (False, f'Файл не найден: {rel_path}')
        content = path.read_text(encoding='utf-8', errors='replace')
        if len(content) > 30000:
            content = content[:30000] + '\n\n... (обрезано, файл >30k символов)'
        return (True, content)
    except Exception as e:
        return (False, f'Не удалось прочитать: {e}')

def format_execution_report(report: Dict[str, Any]) -> str:
    """Render structured execution report text for chat output."""
    ok = bool(report.get('ok'))
    summary = str(report.get('summary') or ('done' if ok else 'failed'))
    applied = list(report.get('applied_steps') or [])
    skipped = list(report.get('skipped_steps') or [])
    changed = list(report.get('artifacts_changed') or [])
    verification = report.get('verification') or {}
    error = report.get('error')
    lines = [('Готово' if ok else 'Не удалось') + f': {summary}.']
    if applied:
        lines.append('Applied steps: ' + ', '.join((str(x) for x in applied)))
    if skipped:
        lines.append('Skipped steps: ' + ', '.join((str(x) for x in skipped)))
    if changed:
        lines.append('Changed: ' + ', '.join((str(x) for x in changed)))
    if isinstance(verification, dict) and verification:
        lines.append('Verification: ' + ('OK' if verification.get('ok') else 'FAIL'))
        out = str(verification.get('output') or '').strip()
        if out:
            lines.append(out[:1200])
    if error:
        lines.append(f'Error: {error}')
    return '\n'.join(lines)

def _extracted_block_154(lines, risks):
    lines.append('- **Риски:**')
    for r in risks:
        lines.append(f'  - {r}')

def format_doctor_report_for_chat(root: Path) -> str:
    """Format eurika_doctor_report.json for chat display."""
    doctor_path = root / 'eurika_doctor_report.json'
    fix_path = root / 'eurika_fix_report.json'
    if not doctor_path.exists() and (not fix_path.exists()):
        return 'Отчёт не найден. Сначала выполни `eurika scan .` и `eurika doctor .`.'
    try:
        from report.report_snapshot import format_report_snapshot
        return format_report_snapshot(root)
    except Exception:
        pass
    if doctor_path.exists():
        try:
            doc = json.loads(doctor_path.read_text(encoding='utf-8'))
            lines: List[str] = ['## Отчёт Doctor (eurika_doctor_report.json)\n']
            summary = doc.get('summary', {}) or {}
            sys_info = summary.get('system', {}) or {}
            lines.append(f"- **Модули:** {sys_info.get('modules', '?')}")
            lines.append(f"- **Зависимости:** {sys_info.get('dependencies', '?')}")
            lines.append(f"- **Циклы:** {sys_info.get('cycles', 0)}")
            risks = summary.get('risks', [])[:8]
            if risks:
                _extracted_block_154(lines, risks)
            arch = (doc.get('architect') or '').strip()
            if arch:
                lines.append(f'\n**Architect:** {arch[:800]}' + ('...' if len(arch) > 800 else ''))
            ops = doc.get('operational_metrics') or {}
            if ops:
                lines.append(f"\n**Метрики:** apply_rate={ops.get('apply_rate')}, rollback_rate={ops.get('rollback_rate')}")
            return '\n'.join(lines)
        except Exception:
            return 'Не удалось прочитать eurika_doctor_report.json.'
    if fix_path.exists():
        try:
            fix = json.loads(fix_path.read_text(encoding='utf-8'))
            lines = ['## Отчёт Fix (eurika_fix_report.json)\n']
            mod = fix.get('modified', [])
            sk = fix.get('skipped', [])
            lines.append(f'- **Modified:** {len(mod)}')
            lines.append(f'- **Skipped:** {len(sk)}')
            v = fix.get('verify', {}) or {}
            lines.append(f"- **Verify:** {v.get('success', 'N/A')}")
            return '\n'.join(lines)
        except Exception:
            return 'Не удалось прочитать eurika_fix_report.json.'
    return 'Отчёт не найден.'

def format_root_ls(root: Path, limit: int=120) -> str:
    """Render ls-like listing for project root."""
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return f'Не удалось прочитать корень проекта: {e}'
    lines: List[str] = []
    for p in entries[:limit]:
        name = p.name
        suffix = '/' if p.is_dir() else ''
        lines.append(name + suffix)
    if len(entries) > limit:
        lines.append(f'... ещё {len(entries) - limit}')
    return '\n'.join(lines) if lines else '(пусто)'

_SKIP_DIR_NAMES = frozenset(
    {'__pycache__', '.git', '.eurika', 'node_modules', '.venv', 'venv', '.mypy_cache', '.pytest_cache'}
)
_DOC_SCAN_SKIP = _SKIP_DIR_NAMES | {
    '.dart_tool', 'build', 'dist', 'target', '.gradle', 'vendor', 'third_party',
    'site-packages', '.tox', '.eggs', '.ruff_cache', '.pytest_cache', '.mypy_cache',
    'egg-info', '.tmp', 'coverage', 'htmlcov', '.idea', '.vscode',
}
_DOC_DIR_NAMES = ('docs', 'doc', 'documentation', 'wiki', 'notes', 'design', 'spec', 'specs')
_DOC_EXTENSIONS = ('.md', '.rst', '.adoc', '.txt', '.mdc')
_DOC_ROOT_NAMES = frozenset({
    'README', 'CHANGELOG', 'CONTRIBUTING', 'LICENSE', 'NOTICE',
    'ROADMAP', 'ARCHITECTURE', 'AUTHORS', 'INSTALL', 'USAGE', 'HISTORY',
})
_INFO_ARTIFACTS = (
    'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt', 'Pipfile',
    'package.json', 'Cargo.toml', 'go.mod', 'CMakeLists.txt', 'Makefile',
    'self_map.json', 'pubspec.yaml',
)


def iter_project_files(root: Path):
    """Yield project files, skipping cache and tooling directories."""
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIR_NAMES for part in rel.parts[:-1]):
            continue
        yield path


def count_project_files(root: Path) -> Dict[str, int]:
    """Count files by extension under project root."""
    counts: Dict[str, int] = {}
    for path in iter_project_files(root):
        ext = path.suffix.lower() or '(no ext)'
        counts[ext] = counts.get(ext, 0) + 1
    return counts


def _detect_project_kind(root: Path) -> str:
    if any(root.rglob('*.kv')):
        return 'Kivy-приложение (Python + KV)'
    if (root / 'qt_app').is_dir():
        return 'Eurika/Qt-проект'
    if (root / 'pyproject.toml').exists():
        return 'Python-пакет (`pyproject.toml`)'
    if (root / 'app.py').exists() or (root / 'main.py').exists():
        return 'Python-приложение'
    return 'проект на диске'


def format_project_overview(root: Path) -> str:
    """Structured project description from filesystem + self_map."""
    from eurika.api import get_summary

    counts = count_project_files(root)
    total = sum(counts.values())
    py_files = counts.get('.py', 0)
    kind = _detect_project_kind(root)
    lines = [
        f'Проект `{root}` — {kind}.',
        '',
        f'**Файлы:** {total} всего' + (f', из них {py_files} `.py`' if py_files else ''),
    ]
    if counts:
        by_ext = ', '.join(f'{ext}: {n}' for ext, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
        lines.append(f'По типам: {by_ext}.')
    summary = get_summary(root)
    if summary and not summary.get('error'):
        sys_info = summary.get('system') or {}
        modules = sys_info.get('modules', '?')
        deps = sys_info.get('dependencies', '?')
        cycles = sys_info.get('cycles', '?')
        lines.extend(
            [
                '',
                f'**Архитектура (scan):** {modules} модулей, {deps} зависимостей, {cycles} циклов.',
            ]
        )
        maturity = summary.get('maturity')
        if maturity:
            lines.append(f'Зрелость: `{maturity}`.')
        top = summary.get('top_blast_radius') or []
        if top:
            names = [item[0] if isinstance(item, (list, tuple)) else str(item) for item in top[:5]]
            lines.append(f'Ключевые модули: {", ".join(names)}.')
        if py_files and isinstance(modules, int) and py_files != modules:
            lines.append(
                f'Примечание: на диске {py_files} `.py`-файлов, в scan — {modules} модулей '
                '(часть файлов может не входить в граф импортов).'
            )
    else:
        err = (summary or {}).get('error', 'нет self_map.json')
        lines.extend(['', f'Архитектурных данных нет ({err}). Запусти: `eurika scan .`'])
    return '\n'.join(lines)


def _path_in_skip_tree(rel_parts: tuple[str, ...]) -> bool:
    return any(part in _DOC_SCAN_SKIP for part in rel_parts[:-1])


def _is_documentation_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = path.name
    stem = path.stem.upper()
    ext = path.suffix.lower()
    if name == 'MANIFEST.in':
        return False
    if stem in _DOC_ROOT_NAMES:
        return True
    if ext in ('.md', '.rst', '.adoc', '.mdc'):
        return True
    if ext == '.txt' and (
        'readme' in name.lower()
        or 'license' in name.lower()
        or 'changelog' in name.lower()
        or 'copying' in name.lower()
    ):
        return True
    if name.lower() in ('readme', 'changelog', 'contributing', 'license', 'copying'):
        return True
    return False


def _doc_location_label(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) == 1:
        return 'root'
    if parts[0] in _DOC_DIR_NAMES:
        return parts[0]
    if parts[0] == '.eurika':
        return '.eurika'
    return 'other'


def _first_heading(path: Path) -> str:
    """Return the first non-empty heading or line for preview."""
    try:
        with path.open('r', encoding='utf-8', errors='replace') as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    return line.lstrip('# ').strip()
                return line[:80]
    except OSError:
        return ''
    return ''


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f'{num_bytes} B'
    if num_bytes < 1024 * 1024:
        return f'{num_bytes / 1024:.1f} KB'
    return f'{num_bytes / (1024 * 1024):.1f} MB'


def discover_project_docs(root: Path, *, limit: int = 80) -> tuple[dict[str, list[tuple[Path, str]]], int]:
    """Scan project tree and group documentation files by location."""
    root = root.resolve()
    grouped: dict[str, list[tuple[Path, str]]] = {
        'root': [],
        'docs': [],
        'doc': [],
        'documentation': [],
        'wiki': [],
        'notes': [],
        'design': [],
        'spec': [],
        'specs': [],
        '.eurika': [],
        'other': [],
    }
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        label = _doc_location_label(root, path)
        bucket = grouped.setdefault(label, [])
        bucket.append((path, _first_heading(path)))

    # Root-level files (fast path).
    try:
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and _is_documentation_file(p):
                _add(p)
    except OSError:
        pass

    # Known doc directories (depth-limited recursive).
    for dirname in _DOC_DIR_NAMES:
        doc_dir = root / dirname
        if not doc_dir.is_dir():
            continue
        try:
            for p in sorted(doc_dir.rglob('*')):
                if not p.is_file() or not _is_documentation_file(p):
                    continue
                rel = p.relative_to(root)
                if _path_in_skip_tree(rel.parts):
                    continue
                _add(p)
        except OSError:
            continue

    # Eurika project rules (often contain project guidance).
    rules_dir = root / '.eurika' / 'rules'
    if rules_dir.is_dir():
        try:
            for p in sorted(rules_dir.glob('*.mdc')):
                _add(p)
        except OSError:
            pass

    # Shallow project-wide scan for README/CHANGELOG and stray *.md (max depth 4).
    try:
        for p in root.rglob('*'):
            if not p.is_file() or not _is_documentation_file(p):
                continue
            rel = p.relative_to(root)
            if len(rel.parts) > 4:
                continue
            if _path_in_skip_tree(rel.parts):
                continue
            _add(p)
    except OSError:
        pass

    # Flatten into display order, respect limit.
    order = ['root', 'docs', 'doc', 'documentation', 'wiki', 'notes', 'design', 'spec', 'specs', '.eurika', 'other']
    result: dict[str, list[tuple[Path, str]]] = {}
    remaining = limit
    for key in order:
        items = grouped.get(key) or []
        if not items:
            continue
        if remaining <= 0:
            break
        take = items[:remaining]
        result[key] = take
        remaining -= len(take)
    return result, len(seen)


def _collect_info_artifacts(root: Path) -> list[tuple[str, str]]:
    """Non-markdown files that often describe the project."""
    found: list[tuple[str, str]] = []
    for name in _INFO_ARTIFACTS:
        p = root / name
        if p.is_file():
            found.append((name, _format_size(p.stat().st_size)))
    # KV/UI specs in Kivy and similar projects.
    for pattern in ('*.kv', '*.yaml', '*.yml'):
        for p in sorted(root.glob(pattern))[:3]:
            if p.is_file():
                found.append((p.name, _format_size(p.stat().st_size)))
    kv_dir = root / 'kv'
    if kv_dir.is_dir():
        for p in sorted(kv_dir.glob('*.kv'))[:3]:
            rel = p.relative_to(root)
            found.append((str(rel), _format_size(p.stat().st_size)))
    return found


def format_project_docs(root: Path) -> str:
    """List project documentation discovered automatically under project root."""
    root = root.resolve()
    discovered, total = discover_project_docs(root)
    lines: List[str] = [f'Документация проекта `{root}` (найдено {total} файлов):', '']

    section_titles = {
        'root': 'В корне',
        'docs': '`docs/`',
        'doc': '`doc/`',
        'documentation': '`documentation/`',
        'wiki': '`wiki/`',
        'notes': '`notes/`',
        'design': '`design/`',
        'spec': '`spec/`',
        'specs': '`specs/`',
        '.eurika': '`.eurika/rules/` (правила проекта)',
        'other': 'В других каталогах',
    }

    shown = 0
    for key, title in section_titles.items():
        items = discovered.get(key) or []
        if not items:
            continue
        lines.append(f'**{title} ({len(items)}):**')
        for p, heading in items[:25]:
            rel = p.relative_to(root)
            rel_s = str(rel)
            size = _format_size(p.stat().st_size) if p.exists() else '?'
            preview = f' — {heading}' if heading else ''
            lines.append(f'- `{rel_s}` ({size}){preview}')
            shown += 1
        if len(items) > 25:
            lines.append(f'- … ещё {len(items) - 25}')
        lines.append('')

    if shown == 0:
        artifacts = _collect_info_artifacts(root)
        lines.append('Markdown/RST-документации не найдено.')
        if artifacts:
            lines.append('')
            lines.append('**Информативные файлы проекта:**')
            for name, size in artifacts:
                lines.append(f'- `{name}` ({size})')
            lines.append('')
            lines.append('Спроси «покажи файл <имя>» или «что за проект?» для обзора.')
        else:
            lines.append('Попробуй «покажи дерево» или «что за проект?».')
    elif total > shown:
        lines.append(f'Показано {shown} из {total}. Уточни каталог или имя файла.')

    return '\n'.join(lines).rstrip()


def format_file_recount(root: Path) -> str:
    """Recount files on disk; cross-check with scan when available."""
    from eurika.api import get_summary

    counts = count_project_files(root)
    total = sum(counts.values())
    py_files = sorted(
        str(p.relative_to(root)) for p in iter_project_files(root) if p.suffix.lower() == '.py'
    )
    lines = [
        f'Пересчитал файлы в `{root}`:',
        '',
        f'**Всего файлов:** {total}',
    ]
    if counts:
        lines.append('**По расширениям:**')
        for ext, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f'- `{ext}`: {n}')
    if py_files:
        lines.extend(['', f'**Python-модули ({len(py_files)}):**', ', '.join(f'`{name}`' for name in py_files)])
    summary = get_summary(root)
    if summary and not summary.get('error'):
        modules = (summary.get('system') or {}).get('modules')
        if isinstance(modules, int):
            lines.append('')
            if modules == len(py_files):
                lines.append(f'Scan согласуется: {modules} модулей в `self_map.json`.')
            else:
                lines.append(
                    f'Scan: {modules} модулей в `self_map.json`, на диске {len(py_files)} `.py`-файлов.'
                )
    return '\n'.join(lines)


def format_project_tree(root: Path, max_depth: int=3, limit: int=500) -> str:
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
            branch = '└── ' if is_last else '├── '
            name = p.name + ('/' if p.is_dir() else '')
            acc.append(prefix + branch + name)
            if p.is_dir() and depth > 1:
                sub_prefix = prefix + ('    ' if is_last else '│   ')
                _walk(p, depth - 1, sub_prefix, acc)
    acc: List[str] = []
    _walk(root, max_depth, '', acc)
    return '\n'.join(acc) if acc else '(пусто)'

def brief_release_check_analysis(output: str, ok: bool) -> str:
    """Extract brief analysis from release check output for chat."""
    import re
    if ok:
        return '**Release check пройден.** Всё работает.'
    parts: list[str] = []
    failed = re.findall('FAILED\\s+(tests/[^\\s]+)', output)
    if failed:
        unique = list(dict.fromkeys(failed))[:5]
        parts.append(f"тесты: {', '.join(unique)}")
    if 'ruff' in output.lower() and ('error' in output.lower() or 'failed' in output.lower()):
        parts.append('ruff: ошибки стиля/импортов')
    if 'mypy' in output.lower() and ('error' in output.lower() or 'fail' in output.lower()):
        parts.append('mypy: нужны аннотации типов')
    if not parts:
        if output.strip():
            parts.append('См. вывод ниже.')
        else:
            parts.append('Вывод пуст.')
    return f"**Release check не прошёл.**\n\nОшибки: {'; '.join(parts)}\n\nСкажи «исправь» или «пофикси» для правок."


def _find_roadmap_path(root: Path) -> Path | None:
    """Locate ROADMAP.md for the project."""
    candidates = (
        root / "docs" / "ROADMAP.md",
        root / "ROADMAP.md",
        root / "doc" / "ROADMAP.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _slice_markdown_section(content: str, header_needle: str, *, max_chars: int = 2200) -> str:
    """Extract a markdown section starting at a header that contains header_needle."""
    lines = content.splitlines()
    out: List[str] = []
    in_section = False
    header_level = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            if not in_section:
                if header_needle.lower() in title.lower() or header_needle in line:
                    in_section = True
                    header_level = level
                    out.append(line)
                continue
            if level <= header_level:
                break
        if in_section:
            out.append(line)
    text = "\n".join(out).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n…"
    return text


def _collect_open_roadmap_items(content: str, *, limit: int = 8) -> List[str]:
    """Unchecked backlog lines `- [ ]` from ROADMAP."""
    items: List[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            items.append(stripped[5:].strip())
        if len(items) >= limit:
            break
    return items


def format_roadmap_next_steps(root: Path) -> str:
    """Summarize current focus and next steps from docs/ROADMAP.md — no LLM."""
    root = root.resolve()
    path = _find_roadmap_path(root)
    if path is None:
        return (
            f"ROADMAP.md не найден в `{root}` (искал docs/ROADMAP.md и ROADMAP.md).\n\n"
            "Спроси «какие документы по проекту?» — покажу, что есть на диске."
        )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Не удалось прочитать {path.relative_to(root)}: {exc}"

    rel = path.relative_to(root)
    lines: List[str] = [
        f"## Дальнейшее развитие (из `{rel}`)",
        "",
        "Ответ по документу на диске, без LLM.",
        "",
    ]

    principle = _slice_markdown_section(content, "1. Принцип", max_chars=900)
    if principle:
        lines.append(principle)
        lines.append("")

    focus = _slice_markdown_section(content, "4.5", max_chars=1400)
    if focus:
        lines.append(focus)
        lines.append("")

    next_steps = _slice_markdown_section(content, "4.6", max_chars=1200)
    if next_steps:
        lines.append(next_steps)
        lines.append("")

    open_items = _collect_open_roadmap_items(content)
    if open_items:
        lines.append("**Открытые пункты бэклога (`- [ ]`):**")
        for item in open_items:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(f"Полный файл: `{rel}`. Сверка фазы: «проверь фазу 2.7».")
    return "\n".join(lines).strip()


def format_capabilities_help() -> str:
    """Structured help text — no LLM."""
    return """Да. В Qt у меня есть **локальный доступ к проекту** и вкладка **Terminal**.

**Что могу по системе:**
- запускать команды в **корне текущего проекта** (через Chat → Terminal): `ls`, `eurika scan .`, скрипты репо
- читать/писать файлы проекта («покажи файл…», «сохрани в…»)
- **не** админю ОС целиком: нет произвольного root/Windows Security, нет чужих дисков вне project root

**Как попросить код:**
- «напиши функцию … и сохрани в `app.py`»
- «создай файл `tests/test_foo.py` с тестами для …»
- «покажи файл …» → опиши правку → «сохрани»

**Проект (без LLM, мгновенно):**
- «что за проект?» — обзор и архитектура
- «сколько файлов?» / «пересчитай файлы» — подсчёт с диска
- «покажи дерево» / «структуру проекта» — каталоги и файлы
- «какие документы по проекту?» — README, docs/, правила
- «что дальше по развитию?» / «просмотри roadmap» — выжимка из ROADMAP.md
- «покажи файл app.py» — содержимое файла
- «выполни ls» — список в корне

**Анализ и рефакторинг:**
- «просканируй проект» — `eurika scan .`
- «покажи отчёт» — doctor report
- «какая цель?» / «что получилось?» / «сбрось цель» — контекст агента
- «проведи ритуал» — scan → doctor → report-snapshot
- «проведи smoke test» — быстрый smoke (torch + Qt)
- «проведи self-check» — полный self-check
- «рефактори» / «eurika fix» — правки по архитектуре
- «прогони release check» — проверка перед релизом

**Git и изменения:**
- «собери коммит» → «применяй» — коммит с подтверждением
- «сохрани в …» / «создай файл …» — запись кода (с подтверждением для рискованных действий)

**Интернет (только по явной просьбе):**
- «поищи в интернете …» — веб-поиск (DuckDuckGo или Tavily/Brave из `.env`)

Спроси, например: «выполни ls» или «напиши hello в app.py и сохрани»."""


def grounded_ui_tabs_text() -> str:
    """Static text for ui_tabs response. Matches Qt main_window tab names."""
    tabs = ['Commands', 'Dashboard', 'Approvals', 'Models', 'Chat']
    return 'В текущем Qt UI есть вкладки: ' + ', '.join((f'`{name}`' for name in tabs)) + '.'

def enforce_eurika_persona(text: str) -> str:
    """Replace base model mentions with Eurika identity."""
    import re
    out = text
    for pat, repl in [('\\bQwen\\b', 'Eurika'), ('\\bLlama\\b', 'Eurika'), ('\\bOllama\\b', 'Eurika'), ('\\bOpenAI\\b', 'Eurika'), ('\\bGPT-\\d+\\b', 'Eurika')]:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out

def infer_default_save_target(message: str) -> str:
    """Infer default save target from message."""
    msg = (message or '').strip().lower()
    if 'app.py' in msg or 'main.py' in msg:
        return 'app.py' if 'app.py' in msg else 'main.py'
    return 'app.py'