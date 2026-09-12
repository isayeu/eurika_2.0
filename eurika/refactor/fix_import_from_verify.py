"""
Fix import errors inferred from verify (pytest) failure output.

When verify fails with ModuleNotFoundError or ImportError, parse the output,
infer a fix (redirect import or create minimal stub), and return patch operations.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Regex for common verify output patterns
_MODULE_NOT_FOUND = re.compile(
    r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_IMPORT_ERROR = re.compile(
    r"ImportError:\s*cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_ATTR_ERROR = re.compile(
    r"AttributeError:\s*module ['\"]([^'\"]+)['\"] has no attribute ['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_NAME_ERROR = re.compile(
    r"NameError:\s*name ['\"]([^'\"]+)['\"] is not defined",
    re.MULTILINE,
)
_FAILING_FILE = re.compile(
    r"^(\S+\.py):\d+\s+in\s+<module>",
    re.MULTILINE,
)
_FROM_IMPORT = re.compile(
    r"from\s+(\S+)\s+import\s+(.+)",
)

# For "from X import Y" in the traceback line just before the error
_TRACEBACK_LINE = re.compile(
    r'^\s+File "([^"]+)", line \d+, in .+',
    re.MULTILINE,
)


def parse_verify_import_error(verify_stdout: str, verify_stderr: str) -> Optional[Dict[str, Any]]:
    """
    Parse verify output for ModuleNotFoundError or ImportError.
    Returns dict with: missing_module, requested_symbols, failing_file, error_type.
    """
    text = (verify_stdout or "") + "\n" + (verify_stderr or "")

    # ModuleNotFoundError: No module named 'X'
    m = _MODULE_NOT_FOUND.search(text)
    if m:
        missing_module = m.group(1).strip()
        # Find the failing file - look for "File \"path\", line N" before the error
        failing_file = _find_failing_file(text)
        # Infer requested symbols from "from X import Y" in the traceback
        requested = _infer_requested_symbols(text, missing_module)
        return {
            "error_type": "ModuleNotFoundError",
            "missing_module": missing_module,
            "requested_symbols": requested or [],
            "failing_file": failing_file,
        }

    all_parsed = parse_all_verify_import_errors(text)
    if all_parsed:
        return all_parsed[0]

    # NameError: name 'X' is not defined (e.g. in extracted module missing module-level constant)
    m = _NAME_ERROR.search(text)
    if m:
        missing_name = m.group(1).strip()
        failing_file = _find_failing_file(text)
        return {
            "error_type": "NameError",
            "missing_name": missing_name,
            "requested_symbols": [missing_name],
            "failing_file": failing_file,
        }

    return None


def parse_all_verify_import_errors(text: str) -> List[Dict[str, Any]]:
    """Every ImportError / AttributeError in a pytest or release_check log."""
    if not text:
        return []
    found: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def _add(error_type: str, module: str, symbol: str, pos: int) -> None:
        failing = _find_failing_file_near(text, pos) or _find_failing_file(text)
        key = (error_type, module, symbol, failing or "")
        if key in seen:
            return
        seen.add(key)
        found.append(
            {
                "error_type": error_type,
                "missing_module": module,
                "requested_symbols": [symbol],
                "failing_file": failing,
            }
        )

    for m in _IMPORT_ERROR.finditer(text):
        _add("ImportError", m.group(2).strip(), m.group(1).strip(), m.start())
    for m in _ATTR_ERROR.finditer(text):
        _add("AttributeError", m.group(1).strip(), m.group(2).strip(), m.start())
    return found


def _find_failing_file_near(text: str, pos: int) -> Optional[str]:
    prefix = text[:pos]
    lines = prefix.split("\n")
    return _extract_file_from_traceback(lines, len(lines)) or _extract_file_from_context(
        lines, len(lines)
    )


def _extract_file_from_traceback(lines: List[str], error_idx: int) -> Optional[str]:
    """Look backwards from error line for .py file in traceback."""
    for j in range(error_idx - 1, -1, -1):
        mm = re.search(r"^(\S+\.py):\d+:\s+in\s+", lines[j])
        if mm:
            return mm.group(1).strip()
        mm = _TRACEBACK_LINE.match(lines[j])
        if mm:
            path = mm.group(1)
            if path.endswith(".py"):
                norm = path.replace("\\", "/")
                return norm if "/" in norm else Path(path).name
    return None


def _extract_file_from_context(lines: List[str], error_idx: int) -> Optional[str]:
    """Fallback: scan lines before error for any .py filename."""
    for j in range(max(0, error_idx - 8), error_idx):
        m = re.search(r"(\S+\.py)", lines[j])
        if m:
            return m.group(1)
    return None


def _find_failing_file(text: str) -> Optional[str]:
    """Extract the .py file that failed (closest to the error line)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "ModuleNotFoundError" in line or "ImportError" in line or "NameError" in line:
            if "ModuleNotFoundError" in line or "ImportError" in line:
                m = re.search(r"ERROR collecting (\S+\.py)", text)
                if m:
                    return m.group(1).strip()
            result = _extract_file_from_traceback(lines, i)
            if result:
                return result
            result = _extract_file_from_context(lines, i)
            if result:
                return result
            break
    return None


def _infer_requested_symbols(text: str, module_name: str) -> List[str]:
    """Infer what symbols the failing file imports from the missing module."""
    for line in text.split("\n"):
        m = _FROM_IMPORT.search(line)
        if m and m.group(1).strip() == module_name:
            rhs = m.group(2).strip()
            if "(" in rhs:
                continue
            return [s.strip() for s in rhs.replace("*", "").split(",") if s.strip()]
    return []


def _read_imports_from_file(path: Path) -> List[Tuple[str, List[str]]]:
    """Get (module, [symbols]) from imports in file."""
    result: List[Tuple[str, List[str]]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [a.name for a in node.names if a.name != "*"]
                result.append((node.module, names))
    except (SyntaxError, OSError):
        pass
    return result


def _module_name_for(root: Path, py_path: Path) -> str:
    rel = py_path.resolve().relative_to(Path(root).resolve())
    return str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")


def _search_symbol_in_project(root: Path, symbol: str, exclude_module: str) -> Optional[str]:
    """
    Search for def/class named 'symbol' in .py files. Return module path (e.g. 'goals') if found.
    """
    skip_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".eurika_backups"}
    hits: List[str] = []
    for py_path in root.rglob("*.py"):
        if any(s in py_path.parts for s in skip_dirs):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        mod_path = _module_name_for(root, py_path)
        if mod_path == exclude_module or py_path.stem == exclude_module:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol:
                hits.append(mod_path)
                break
    if not hits:
        return None
    prod = [h for h in hits if not h.startswith("tests.")]
    return (prod or hits)[0]


def _create_stub_module(
    module_name: str,
    requested_symbols: List[str],
) -> Optional[str]:
    """
    Create minimal stub content for a missing module.
    Handles common patterns: load_* (returns dict), *_FILE (Path constant).
    """
    lines = ['"""Minimal stub generated by Eurika (fix_import_from_verify)."""', ""]
    base = module_name.split(".")[-1]
    file_const = f"{base.upper().replace('-', '_')}_FILE"

    # Add FILE constant if test might monkeypatch it (load_* often paired with *_FILE)
    has_load = any("load" in s.lower() for s in requested_symbols)
    has_file_sym = any("FILE" in s for s in requested_symbols)
    if has_load or has_file_sym:
        lines.append("from pathlib import Path")
        lines.append("")
        lines.append(f'{file_const} = Path("{base}.json")')
        lines.append("")

    if has_load or not requested_symbols:
        lines.append("import json")
        lines.append("")

    for sym in requested_symbols:
        if "load" in sym.lower():
            lines.append(f"def {sym}():")
            lines.append(f"    if not {file_const}.exists():")
            lines.append("        return {}")
            lines.append("    try:")
            lines.append(f'        return json.loads({file_const}.read_text(encoding="utf-8"))')
            lines.append("    except (json.JSONDecodeError, OSError):")
            lines.append("        return {}")
            lines.append("")
        elif "FILE" in sym and sym not in [ln.strip().split("=")[0].strip() for ln in lines if "=" in ln]:
            lines.append(f"{sym} = Path(\"{base}.json\")")
            lines.append("")

    if not any("def " in ln for ln in lines) and requested_symbols:
        lines.append(f"def {requested_symbols[0]}():")
        lines.append("    return {}")
        lines.append("")

    return "\n".join(lines).strip() + "\n" if lines else None


def _find_name_in_ast_tree(tree: ast.AST, name: str) -> Optional[str]:
    """Find Assign/AnnAssign defining name in AST. Return unparsed line."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.unparse(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.unparse(node)
    return None


def _find_constant_definition(root: Path, name: str, exclude_file: str) -> Optional[str]:
    """Search for Assign/AnnAssign defining name in .py files. Return unparsed line."""
    skip_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".eurika_backups"}
    for py_path in root.rglob("*.py"):
        if any(s in py_path.parts for s in skip_dirs):
            continue
        if py_path.name == exclude_file:
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        result = _find_name_in_ast_tree(tree, name)
        if result:
            return result
    return None


def _handle_name_error_ops(
    root: Path,
    failing_file: str,
    failing_path: Path,
    missing_name: str,
) -> List[Dict[str, Any]]:
    """Build ops to add missing constant to failing file (NameError)."""
    const_line = _find_constant_definition(root, missing_name, failing_file)
    if not const_line:
        return []
    content = failing_path.read_text(encoding="utf-8")
    extra_imports: List[str] = []
    if "Path(" in const_line and "from pathlib import Path" not in content and "import Path" not in content:
        extra_imports.append("from pathlib import Path")
    lines = content.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            insert_idx = i + 1
        elif stripped and not stripped.startswith("#"):
            break
    to_insert = extra_imports + [const_line, ""]
    new_lines = lines[:insert_idx] + to_insert + lines[insert_idx:]
    new_content = "\n".join(new_lines)
    return [{
        "kind": "fix_import",
        "target_file": failing_file,
        "params": {"add_constant": missing_name},
        "diff": new_content,
    }]


def _rewrite_from_import(content: str, old_mod: str, new_mod: str, symbols: List[str]) -> Optional[str]:
    """Rewrite ``from old_mod import …`` that names any of ``symbols``."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    lines = content.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != old_mod:
            continue
        names = [alias.name for alias in node.names]
        if not any(sym in names for sym in symbols):
            continue
        start = node.lineno - 1
        end = (node.end_lineno or node.lineno) - 1
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        new_stmt = f"{indent}from {new_mod} import {', '.join(names)}"
        updated = lines[:start] + [new_stmt] + lines[end + 1 :]
        text = "\n".join(updated)
        if content.endswith("\n"):
            text += "\n"
        return text
    return None


def _rewrite_attr_uses(content: str, old_mod: str, new_mod: str, symbol: str) -> Optional[str]:
    """Rewrite ``alias.symbol`` after ``from pkg import alias`` when alias is the old module."""
    old_alias = old_mod.rsplit(".", 1)[-1]
    new_alias = new_mod.rsplit(".", 1)[-1]
    needle = f"{old_alias}.{symbol}"
    if needle not in content:
        return None
    updated = content.replace(needle, f"{new_alias}.{symbol}")
    parent = new_mod.rsplit(".", 1)[0] if "." in new_mod else ""
    import_line = f"from {parent} import {new_alias}" if parent else f"import {new_mod}"
    if import_line not in updated and f"import {new_mod}" not in updated:
        lines = updated.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith(("import ", "from ")):
                insert_at = i + 1
        lines.insert(insert_at, import_line)
        updated = "\n".join(lines)
        if content.endswith("\n"):
            updated += "\n"
    return updated


def _try_redirect_import_ops(
    root: Path,
    missing: str,
    requested: List[str],
    failing_file: str,
    failing_path: Path,
    error_type: str = "",
) -> List[Dict[str, Any]]:
    """Try redirecting import to another module that has the symbols."""
    found_module: Optional[str] = None
    matched_sym = ""
    for sym in requested:
        if not sym:
            continue
        other = _search_symbol_in_project(root, sym, missing)
        if other:
            found_module = other
            matched_sym = sym
            break
    if not found_module:
        return []
    content = failing_path.read_text(encoding="utf-8")
    new_content = _rewrite_from_import(content, missing, found_module, requested)
    if new_content is None and error_type == "AttributeError" and matched_sym:
        new_content = _rewrite_attr_uses(content, missing, found_module, matched_sym)
    if new_content is None or new_content == content:
        return []
    return [{
        "kind": "fix_import",
        "target_file": failing_file,
        "params": {"old_module": missing, "new_module": found_module, "symbols": requested},
        "diff": new_content,
    }]


def _try_create_stub_op(
    root: Path,
    missing: str,
    requested: List[str],
) -> Optional[Dict[str, Any]]:
    """Create stub module if it doesn't exist."""
    stub_path = missing.replace(".", "/") + ".py"
    full_path = root / stub_path if "/" in stub_path else root / (missing + ".py")
    if full_path.exists():
        return None
    stub_content = _create_stub_module(missing, requested)
    if not stub_content:
        return None
    return {
        "kind": "create_module_stub",
        "target_file": full_path.relative_to(root).as_posix(),
        "params": {"module": missing, "symbols": requested},
        "content": stub_content,
    }


def _resolve_failing_path(root: Path, failing_file: str) -> Optional[Path]:
    raw = (failing_file or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() and path.is_file():
        return path
    cand = root / raw
    if cand.is_file():
        return cand
    name = path.name
    matches = [
        item
        for item in root.rglob(name)
        if item.is_file() and not any(part in {".venv", "venv", "__pycache__"} for part in item.parts)
    ]
    return matches[0] if len(matches) == 1 else None


def suggest_fix_import_operations(
    project_root: Path,
    parsed: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Suggest patch operations to fix the import error.

    Strategy:
    1. NameError: add missing constant from another module (e.g. extracted module missing GOALS_FILE)
    2. If requested symbols exist in another module: fix import (change from X to Y)
    3. Else: create minimal stub module
    """
    root = Path(project_root).resolve()
    missing = parsed.get("missing_module", "")
    requested = parsed.get("requested_symbols") or []
    failing_file = parsed.get("failing_file")
    error_type = parsed.get("error_type", "")

    if error_type == "NameError" and failing_file:
        missing_name = parsed.get("missing_name", "")
        if missing_name:
            failing_path = _resolve_failing_path(root, str(failing_file))
            if failing_path is not None:
                rel = failing_path.relative_to(root).as_posix()
                ops = _handle_name_error_ops(root, rel, failing_path, missing_name)
                if ops:
                    return ops

    if not missing or not failing_file:
        return []
    failing_path = _resolve_failing_path(root, str(failing_file))
    if failing_path is None:
        return []
    rel = failing_path.relative_to(root).as_posix()

    ops = _try_redirect_import_ops(
        root, missing, requested, rel, failing_path, error_type=str(error_type)
    )
    if ops:
        return ops

    stub_op = _try_create_stub_op(root, missing, requested)
    return [stub_op] if stub_op else []


def suggest_fixes_from_verify_log(project_root: Path, log_text: str) -> List[Dict[str, Any]]:
    """Redirect every relocated import in a pytest/release_check log. Disk unchanged."""
    root = Path(project_root).resolve()
    originals: Dict[str, str] = {}
    current: Dict[str, str] = {}
    for parsed in parse_all_verify_import_errors(log_text):
        if parsed.get("error_type") not in {"ImportError", "AttributeError"}:
            continue
        path = _resolve_failing_path(root, str(parsed.get("failing_file") or ""))
        if path is None:
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in originals:
            originals[rel] = path.read_text(encoding="utf-8")
            current[rel] = originals[rel]
        missing = str(parsed.get("missing_module") or "")
        requested = list(parsed.get("requested_symbols") or [])
        found_module = None
        matched = ""
        for sym in requested:
            other = _search_symbol_in_project(root, sym, missing)
            if other:
                found_module = other
                matched = sym
                break
        if not found_module:
            continue
        rewritten = _rewrite_from_import(current[rel], missing, found_module, requested)
        if rewritten is None and parsed.get("error_type") == "AttributeError" and matched:
            rewritten = _rewrite_attr_uses(current[rel], missing, found_module, matched)
        if rewritten and rewritten != current[rel]:
            current[rel] = rewritten
    return [
        {
            "kind": "agent_edit",
            "target_file": rel,
            "risk": "low",
            "explainability": {"risk": "low", "source": "last-check-import-fix"},
            "params": {"new_content": text},
            "critic_verdict": "allow",
        }
        for rel, text in current.items()
        if text != originals.get(rel)
    ]
