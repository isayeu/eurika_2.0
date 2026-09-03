"""Chat file ops and formatting (P0.4 split from chat.py)."""
from __future__ import annotations
import ast
import json
import re
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


_OVERVIEW_DOC_NAMES = (
    'README.md',
    'README.rst',
    'README.txt',
    'README',
    'PROMPT.md',
    'ABOUT.md',
    'docs/README.md',
    'doc/README.md',
)
_OVERVIEW_ENTRY_FILES = ('main.py', 'app.py', '__main__.py', 'src/main.py', 'src/app.py')
_LAYOUT_SKIP = _SKIP_DIR_NAMES | {'.vscode', '.idea', '.git', '.cursor'}


def _read_text_head(path: Path, *, max_chars: int = 8000) -> str | None:
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    return raw[:max_chars] if raw else None


def _pyproject_blurb(root: Path) -> dict[str, str]:
    path = root / 'pyproject.toml'
    if not path.is_file():
        return {}
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    project = data.get('project') if isinstance(data, dict) else None
    if not isinstance(project, dict):
        return {}
    out: dict[str, str] = {}
    for key in ('name', 'description', 'version'):
        val = project.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def _extract_markdown_purpose(text: str, *, max_paras: int = 3) -> list[str]:
    """First substantive paragraphs from markdown — quoted facts, not guesses."""
    paras: list[str] = []
    buf: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or stripped == '---':
            if buf:
                paras.append(' '.join(buf))
                buf = []
            if len(paras) >= max_paras:
                break
            continue
        if stripped.startswith('#'):
            if buf:
                paras.append(' '.join(buf))
                buf = []
            if len(paras) >= max_paras:
                break
            continue
        if stripped.startswith('|'):
            continue
        if stripped.startswith('- '):
            buf.append(stripped[2:].strip())
        else:
            buf.append(stripped)
        if len(' '.join(buf)) > 500:
            paras.append(' '.join(buf))
            buf = []
            if len(paras) >= max_paras:
                break
    if buf and len(paras) < max_paras:
        paras.append(' '.join(buf))
    cleaned: list[str] = []
    skip_re = re.compile(
        r"(?i)(скопируй блок|связанный бот|не трогать|не импортировать|вставить в новый)"
    )
    for p in paras:
        p = re.sub(r'\s+', ' ', p).strip()
        if len(p) < 12:
            continue
        if skip_re.search(p):
            continue
        cleaned.append(p[:520] + ('…' if len(p) > 520 else ''))
    return cleaned[:max_paras]


def _purpose_from_docs(root: Path) -> list[tuple[str, list[str]]]:
    found: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    candidates: list[Path] = []
    for name in _OVERVIEW_DOC_NAMES:
        p = root / name
        if p.is_file():
            candidates.append(p)
    try:
        discovered, _total = discover_project_docs(root, limit=8)
        for items in discovered.values():
            for path, _heading in items:
                if path.name.upper().startswith('README') or path.name == 'PROMPT.md':
                    candidates.append(path)
    except Exception:
        pass
    for path in candidates:
        rel = str(path.relative_to(root))
        if rel in seen:
            continue
        text = _read_text_head(path)
        if not text:
            continue
        paras = _extract_markdown_purpose(text)
        if paras:
            seen.add(rel)
            found.append((rel, paras))
        if len(found) >= 2:
            break
    return found


def _module_docstring(path: Path) -> str | None:
    text = _read_text_head(path, max_chars=16000)
    if not text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    doc = ast.get_docstring(tree)
    if isinstance(doc, str) and doc.strip():
        one = re.sub(r'\s+', ' ', doc.strip())
        return one[:400] + ('…' if len(one) > 400 else '')
    return None


def _argparse_description(path: Path) -> str | None:
    text = _read_text_head(path, max_chars=16000)
    if not text:
        return None
    m = re.search(
        r'ArgumentParser\s*\([^)]*description\s*=\s*(["\'])(.+?)\1',
        text,
        re.DOTALL,
    )
    if not m:
        return None
    desc = re.sub(r'\s+', ' ', m.group(2).strip())
    return desc[:400] + ('…' if len(desc) > 400 else '')


def _entry_point_summary(root: Path) -> tuple[str, str] | None:
    for rel in _OVERVIEW_ENTRY_FILES:
        path = root / rel
        if not path.is_file():
            continue
        desc = _argparse_description(path) or _module_docstring(path)
        if desc:
            return rel, desc
    return None


def _requirements_packages(root: Path, *, limit: int = 8) -> list[str]:
    path = root / 'requirements.txt'
    if not path.is_file():
        return []
    pkgs: list[str] = []
    try:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name = re.split(r'[<>=!~\[]', line, maxsplit=1)[0].strip()
            if name:
                pkgs.append(name)
            if len(pkgs) >= limit:
                break
    except OSError:
        return []
    return pkgs


def _top_level_layout(root: Path) -> list[str]:
    rows: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return rows
    for path in entries:
        name = path.name
        if name.startswith('.') or name in _LAYOUT_SKIP:
            continue
        if path.is_file():
            if path.suffix.lower() in ('.py', '.toml', '.json', '.sh') or name in _INFO_ARTIFACTS:
                rows.append(f'`{name}`')
            continue
        if not path.is_dir():
            continue
        py_files = sorted(p.name for p in path.glob('*.py') if p.is_file())
        if not py_files:
            continue
        shown = ', '.join(f'`{n}`' for n in py_files[:6])
        more = len(py_files) - min(len(py_files), 6)
        suffix = f' (+{more})' if more > 0 else ''
        rows.append(f'`{name}/` — {shown}{suffix}')
        if len(rows) >= 10:
            break
    return rows


def format_project_overview(root: Path) -> str:
    """Project purpose from README/docs/entry point + layout + optional scan."""
    from eurika.api import get_summary

    root = root.resolve()
    meta = _pyproject_blurb(root)
    title = meta.get('name') or root.name
    lines = [f'## {title}', f'`{root}`', '']

    purpose_bits: list[str] = []
    if meta.get('description'):
        purpose_bits.append(meta['description'])
    for rel, paras in _purpose_from_docs(root):
        for para in paras:
            purpose_bits.append(f'_{rel}:_ {para}')
    entry = _entry_point_summary(root)
    if entry:
        rel, desc = entry
        purpose_bits.append(f'Точка входа `{rel}`: {desc}')

    if purpose_bits:
        lines.append('**Что делает**')
        for bit in purpose_bits[:4]:
            lines.append(f'- {bit}')
        lines.append('')
    else:
        lines.extend(
            [
                '**Что делает**',
                '- В корне нет README/PROMPT и у точки входа нет описания — '
                'положи `README.md` или запусти `eurika scan .` для архитектуры.',
                '',
            ]
        )

    layout = _top_level_layout(root)
    if layout:
        lines.append('**Структура**')
        for row in layout:
            lines.append(f'- {row}')
        lines.append('')

    deps = _requirements_packages(root)
    if deps:
        lines.append(f"**Зависимости** (`requirements.txt`): {', '.join(deps)}")
        lines.append('')

    counts = count_project_files(root)
    total = sum(counts.values())
    py_files = counts.get('.py', 0)
    if total:
        lines.append(
            f'**Файлы на диске:** {total}'
            + (f' (`.py`: {py_files})' if py_files else '')
        )

    summary = get_summary(root)
    if summary and not summary.get('error'):
        sys_info = summary.get('system') or {}
        modules = sys_info.get('modules', '?')
        deps_n = sys_info.get('dependencies', '?')
        cycles = sys_info.get('cycles', '?')
        lines.extend(
            [
                '',
                f'**Архитектура (scan):** {modules} модулей, {deps_n} зависимостей, {cycles} циклов.',
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
                f'На диске {py_files} `.py`, в scan — {modules} модулей '
                '(часть файлов может не входить в граф импортов).'
            )
    else:
        err = (summary or {}).get('error', 'нет self_map.json')
        lines.extend(['', f'**Scan:** архитектурных данных нет ({err}). Запусти: `eurika scan .`'])
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


def _extract_self_check_section(output: str, title: str, *, max_lines: int = 40) -> str:
    """Extract a titled section from self-check text until the next known header."""
    text = output or ""
    if not text or not title:
        return ""
    idx = text.find(title)
    if idx < 0:
        return ""
    known_headers = (
        "PYTORCH (optional ML runtime)",
        "BINANCE (read-only)",
        "LBOT (remote read-only)",
        "LAYER DISCIPLINE:",
        "FILE SIZE LIMITS",
        "SELF-GUARD (R5):",
        "ARCHITECTURE SUMMARY",
        "ARCHITECTURE METRICS",
        "ARCHITECTURE HEALTH",
        "ARCHITECTURE EVOLUTION",
        "ARCHITECTURE RECOMMENDATIONS",
        "SEMANTIC ARCHITECTURE",
        "SYSTEM TOPOLOGY",
    )
    chunk = text[idx:]
    lines = chunk.splitlines()
    out: List[str] = [lines[0]]
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and any(
            stripped.startswith(h) and not stripped.startswith(title)
            for h in known_headers
        ):
            break
        out.append(line)
        if len(out) >= max_lines:
            out.append("…")
            break
    return "\n".join(out).strip()


def format_self_check_for_chat(output: str, *, ok: bool, os_focus: bool = False) -> str:
    """Chat-friendly self-check: OS/env brief, or short status + pointer to Terminal."""
    raw = (output or "").strip()
    status = "OK" if ok else "с замечаниями"
    if not raw:
        return f"**Self-check:** {status}\n\n(вывод пуст — смотри Terminal)"

    if os_focus:
        sections = []
        for title, limit in (
            ("PYTORCH (optional ML runtime)", 16),
            ("BINANCE (read-only)", 24),
            ("LBOT (remote read-only)", 24),
            ("LAYER DISCIPLINE:", 6),
            ("SELF-GUARD (R5):", 12),
        ):
            block = _extract_self_check_section(raw, title, max_lines=limit)
            if block:
                sections.append(block)
        verdict_bits: List[str] = []
        low = raw.lower()
        if "pytorch" in low:
            if "available: yes" in low or "available:yes" in low.replace(" ", ""):
                verdict_bits.append("PyTorch доступен")
            if "cuda: no" in low or "device: cpu" in low:
                verdict_bits.append("инференс/ML на CPU (CUDA нет)")
            elif "cuda: yes" in low:
                verdict_bits.append("CUDA есть")
        if "binance" in low and "ready: yes" in low:
            verdict_bits.append("Binance read-only готов")
        if "lbot" in low and ("ok: yes" in low or "running: yes" in low):
            verdict_bits.append("LBOT remote жив")
        if "LAYER DISCIPLINE: OK" in raw:
            verdict_bits.append("layer discipline OK")

        head = f"**Операционка / окружение (self-check): {status}**"
        if verdict_bits:
            head += "\n\n" + "; ".join(verdict_bits) + "."
        if sections:
            body = "\n\n".join(sections)
            return (
                f"{head}\n\n```\n{body}\n```\n\n"
                "Полный лог (архитектура/smells) — во вкладке **Terminal**. "
                "God-module в отчёте — про код, не про настройку ОС."
            )
        return (
            f"{head}\n\n"
            "Ключевые блоки PYTORCH/BINANCE/LBOT в выводе не найдены — "
            "смотри полный self-check в **Terminal**."
        )

    # Generic self-check: avoid dumping 8k of architecture mid-cut.
    tail = raw[-2500:] if len(raw) > 2500 else raw
    if len(raw) > 2500:
        tail = "…[начало в Terminal]\n" + tail
    return (
        f"**Self-check:** {status}\n\n```\n{tail}\n```\n\n"
        "Полный вывод — во вкладке **Terminal**."
    )


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
    """Summarize next steps — prefer docs/VISION.md backlog, else ROADMAP.md."""
    root = root.resolve()
    vision = root / "docs" / "VISION.md"
    if vision.is_file():
        try:
            content = vision.read_text(encoding="utf-8")
        except OSError as exc:
            return f"Не удалось прочитать docs/VISION.md: {exc}"
        backlog = _slice_markdown_section(content, "Backlog после окна", max_chars=3500)
        now = _slice_markdown_section(content, "Сейчас (прибыль", max_chars=1200)
        lines: List[str] = [
            "## Дальше по бэклогу (из `docs/VISION.md`)",
            "",
            "Ответ по документу на диске, без LLM. Market — только наблюдение journal.",
            "",
        ]
        if now:
            lines.append(now)
            lines.append("")
        if backlog:
            lines.append(backlog)
            lines.append("")
        lines.append(
            "Практический следующий шаг: мелкий chat UX / goals polish (A1); "
            "Market entry/HTF/explore не трогать без разбора journal."
        )
        lines.append("Полный файл: `docs/VISION.md`. Аудит: «аудит документации».")
        return "\n".join(lines).strip()

    path = _find_roadmap_path(root)
    if path is None:
        return (
            f"VISION.md / ROADMAP.md не найдены в `{root}`.\n\n"
            "Спроси «какие документы по проекту?» — покажу, что есть на диске."
        )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Не удалось прочитать {path.relative_to(root)}: {exc}"

    rel = path.relative_to(root)
    lines = [
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


def format_continue_dev_brief(root: Path) -> str:
    """Compact «приступай» reply: next VISION step, not a full doc dump."""
    root = root.resolve()
    vision = root / "docs" / "VISION.md"
    has_vision = vision.is_file()
    lines: List[str] = [
        "**Приступаю** к следующему шагу бэклога (VISION A1).",
        "",
        "**Сейчас (non-Market):** мелкий chat UX / goals polish.",
        "- intents: «приступай» / «продолжай» → этот план (не toggle ML/vector)",
        "- soft ML/vector не трогает env-флаги и `ls`",
        "- `verification_ok=n/a` для skills без verify-патча",
        "",
        "**Не трогаем:** Market entry / HTF / explore / live-ордера — только journal.",
        "",
        "Дальше по желанию: «аудит документации», «что дальше по бэклогу?», "
        "«какая цель?» / конкретная правка в Chat.",
    ]
    if has_vision:
        lines.append("")
        lines.append("Источник: `docs/VISION.md` § Backlog после окна.")
    return "\n".join(lines)


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
    """Replace base-model identity claims with Eurika.

    Do not rewrite runtime names (Ollama/Groq): rate-limit footers and ops notes
    must stay accurate about which backend answered.
    """
    import re

    out = text
    for pat, repl in [
        (r"\bQwen\b", "Eurika"),
        (r"\bLlama\b", "Eurika"),
        (r"\bOpenAI\b", "Eurika"),
        (r"\bGPT-\d+\b", "Eurika"),
    ]:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    return out

def infer_default_save_target(message: str) -> str:
    """Infer default save target from message."""
    msg = (message or '').strip().lower()
    if 'app.py' in msg or 'main.py' in msg:
        return 'app.py' if 'app.py' in msg else 'main.py'
    return 'app.py'