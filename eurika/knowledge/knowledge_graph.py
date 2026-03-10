"""
Knowledge Graph — связи test↔code (R10, KNOWLEDGE_GRAPH_DESIGN §4).

build_test_links: пары (test_file, tested_module) по импортам в тестах.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .code_graph import CodeGraph


def _module_names_from_path(path: str) -> list[str]:
    """Варианты имени модуля для пути: full (a.b.c) и stem (c)."""
    p = Path(path)
    if not path.endswith(".py"):
        return []
    stem = p.stem
    if stem == "__init__":
        # eurika/api/__init__.py → eurika.api
        parts = p.parent.parts
        full = ".".join(parts) if parts else ""
    else:
        # eurika/api/serve.py → eurika.api.serve
        parts = (*p.parent.parts, stem)
        full = ".".join(parts) if parts else stem
    names = [full] if full else []
    if stem != full:
        names.append(stem)
    return names


def _extract_imports(content: str) -> set[str]:
    """Извлечь имена импортируемых модулей из исходника (полные: a.b.c)."""
    names: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _build_name_to_path(code_graph: CodeGraph) -> dict[str, str]:
    """Сопоставление имён модулей с путями из code_graph."""
    result: dict[str, str] = {}
    for path in sorted(code_graph.nodes):
        for name in _module_names_from_path(path):
            if name:
                result[name] = path
    return result


def build_test_links(
    project_root: Path,
    code_graph: CodeGraph,
    *,
    test_dirs: tuple[str, ...] = ("tests", "test"),
    test_patterns: tuple[str, ...] = ("test_*.py", "*_test.py"),
) -> list[tuple[str, str]]:
    """
    Найти пары (test_file, tested_module) — связи тест→код по импортам.

    Обходит test_dirs, парсит AST, сопоставляет импорты с узлами code_graph.
    Возвращает список (путь_теста, путь_модуля) в POSIX.
    """
    root = Path(project_root).resolve()
    name_to_path = _build_name_to_path(code_graph)
    if not name_to_path:
        return []

    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for test_dir_name in test_dirs:
        test_dir = root / test_dir_name
        if not test_dir.is_dir():
            continue
        for pattern in test_patterns:
            for test_path in test_dir.rglob(pattern):
                if not test_path.is_file() or test_path.suffix != ".py":
                    continue
                try:
                    content = test_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                rel_test = test_path.relative_to(root).as_posix()
                for imp_name in _extract_imports(content):
                    matched = name_to_path.get(imp_name)
                    if not matched:
                        for name, path in name_to_path.items():
                            if imp_name.startswith(name + ".") or name.startswith(imp_name + "."):
                                matched = path
                                break
                    if matched and (rel_test, matched) not in seen:
                        seen.add((rel_test, matched))
                        result.append((rel_test, matched))

    return sorted(result)
