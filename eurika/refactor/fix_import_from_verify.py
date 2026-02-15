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

    # ImportError: cannot import name 'Y' from 'X'
    m = _IMPORT_ERROR.search(text)
    if m:
        symbol = m.group(1).strip()
        module = m.group(2).strip()
        failing_file = _find_failing_file(text)
        return {
            "error_type": "ImportError",
            "missing_module": module,
            "requested_symbols": [symbol],
            "failing_file": failing_file,
        }

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


def _find_failing_file(text: str) -> Optional[str]:
    """Extract the .py file that failed (closest to the error line)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "ModuleNotFoundError" in line or "ImportError" in line or "NameError" in line:
            # For ImportError/ModuleNotFoundError: ERROR collecting or first .py in traceback
            if "ModuleNotFoundError" in line or "ImportError" in line:
                m = re.search(r"ERROR collecting (\S+\.py)", text)
                if m:
                    return m.group(1).strip()
            # Last .py before error is where it occurred (e.g. goals_goalsystemextracted.py:10)
            for j in range(i - 1, -1, -1):
                mm = re.search(r"^(\S+\.py):\d+:\s+in\s+", lines[j])
                if mm:
                    return mm.group(1).strip()
                mm = _TRACEBACK_LINE.match(lines[j])
                if mm:
                    path = mm.group(1)
                    if path.endswith(".py"):
                        return Path(path).name
            for j in range(max(0, i - 8), i):
                m = re.search(r"(\S+\.py)", lines[j])
                if m:
                    return m.group(1)
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


def _search_symbol_in_project(root: Path, symbol: str, exclude_module: str) -> Optional[str]:
    """
    Search for def/class named 'symbol' in .py files. Return module path (e.g. 'goals') if found.
    """
    skip_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".eurika_backups"}
    for py_path in root.rglob("*.py"):
        if any(s in py_path.parts for s in skip_dirs):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        module_stem = py_path.stem
        if module_stem == exclude_module:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol:
                rel = py_path.relative_to(root)
                mod_path = str(rel.with_suffix("")).replace("/", ".").replace("\\", ".")
                return mod_path
    return None


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
        elif "FILE" in sym and sym not in [l.strip().split("=")[0].strip() for l in lines if "=" in l]:
            lines.append(f"{sym} = Path(\"{base}.json\")")
            lines.append("")

    if not any("def " in l for l in lines) and requested_symbols:
        lines.append(f"def {requested_symbols[0]}():")
        lines.append("    return {}")
        lines.append("")

    return "\n".join(lines).strip() + "\n" if lines else None


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
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        return ast.unparse(node)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.unparse(node)
    return None


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

    # NameError: add missing constant to failing file
    if error_type == "NameError" and failing_file:
        missing_name = parsed.get("missing_name", "")
        if not missing_name:
            return []
        failing_path = root / failing_file
        if not failing_path.exists():
            return []
        const_line = _find_constant_definition(root, missing_name, failing_file)
        if const_line:
            content = failing_path.read_text(encoding="utf-8")
            # Add import for Path if const uses it and not already imported
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
        return []


    if not missing or not failing_file:
        return []

    failing_path = root / failing_file
    if not failing_path.exists():
        return []

    ops: List[Dict[str, Any]] = []

    # Strategy 1: redirect import - search for symbols elsewhere
    found_module: Optional[str] = None
    for sym in requested:
        if sym.startswith("_"):
            continue
        other = _search_symbol_in_project(root, sym, missing)
        if other:
            found_module = other
            break

    if found_module:
        # Fix import: from X import Y -> from found_module import Y
        imports = _read_imports_from_file(failing_path)
        for mod, syms in imports:
            if mod == missing and syms:
                old_line = f"from {missing} import {', '.join(syms)}"
                new_line = f"from {found_module} import {', '.join(syms)}"
                content = failing_path.read_text(encoding="utf-8")
                if old_line in content:
                    new_content = content.replace(old_line, new_line, 1)
                    ops.append({
                        "kind": "fix_import",
                        "target_file": failing_file,
                        "params": {"old_line": old_line, "new_line": new_line},
                        "diff": new_content,
                    })
                break
        if ops:
            return ops

    # Strategy 2: create stub module
    stub_path = missing.replace(".", "/") + ".py"
    if "/" in stub_path:
        full_path = root / stub_path
    else:
        full_path = root / (missing + ".py")

    if full_path.exists():
        return []

    stub_content = _create_stub_module(missing, requested)
    if stub_content:
        ops.append({
            "kind": "create_module_stub",
            "target_file": full_path.relative_to(root).as_posix(),
            "params": {"module": missing, "symbols": requested},
            "content": stub_content,
        })
    return ops
