"""Project Creation scaffolds (VISION Stage 6 — richer templates on init).

Known ids only — not a Chat phrase-book. Default remains ``minimal``
(``.eurika/`` + stub ``self_map.json`` + README).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

SCAFFOLD_MINIMAL = "minimal"
SCAFFOLD_PYTHON = "python"
SCAFFOLD_PYTHON_CLI = "python-cli"

SCAFFOLD_IDS: tuple[str, ...] = (
    SCAFFOLD_MINIMAL,
    SCAFFOLD_PYTHON,
    SCAFFOLD_PYTHON_CLI,
)

_ALIASES = {
    "empty": SCAFFOLD_MINIMAL,
    "stub": SCAFFOLD_MINIMAL,
    "none": SCAFFOLD_MINIMAL,
    "py": SCAFFOLD_PYTHON,
    "python-lib": SCAFFOLD_PYTHON,
    "lib": SCAFFOLD_PYTHON,
    "cli": SCAFFOLD_PYTHON_CLI,
    "python_cli": SCAFFOLD_PYTHON_CLI,
}

_PKG_SAFE = re.compile(r"[^a-z0-9_]+")
_SCAFFOLD_FLAG = re.compile(
    r"(?i)\s+(?:--scaffold|--template|-t)\s+([a-z0-9_-]+)\s*$"
)
_SCAFFOLD_AS = re.compile(
    r"(?i)\s+(?:как|as|scaffold|шаблон)\s+([a-z0-9_-]+)\s*$"
)


def normalize_scaffold(raw: str | None) -> str:
    """Map user/CLI token to a known scaffold id; unknown → ValueError."""
    token = (raw or SCAFFOLD_MINIMAL).strip().lower().replace(" ", "-")
    if not token:
        return SCAFFOLD_MINIMAL
    mapped = _ALIASES.get(token, token)
    if mapped not in SCAFFOLD_IDS:
        known = ", ".join(SCAFFOLD_IDS)
        raise ValueError(f"unknown scaffold '{raw}'; expected one of: {known}")
    return mapped


def package_name_for(project_name: str) -> str:
    """PEP-ish import name from a display / directory name."""
    slug = _PKG_SAFE.sub("_", (project_name or "app").strip().lower()).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"app_{slug}" if slug else "app"
    return slug


def parse_path_and_scaffold(raw: str) -> tuple[str, str]:
    """Split «demo как python» / «demo --scaffold python-cli» into path + id.

    A lone token that happens to be a scaffold id stays the *path* (minimal).
    """
    text = (raw or "").strip().strip("\"'")
    if not text:
        return "", SCAFFOLD_MINIMAL
    scaffold = SCAFFOLD_MINIMAL
    path = text
    for pattern in (_SCAFFOLD_FLAG, _SCAFFOLD_AS):
        match = pattern.search(path)
        if match:
            try:
                scaffold = normalize_scaffold(match.group(1))
            except ValueError:
                return path, SCAFFOLD_MINIMAL
            path = path[: match.start()].strip()
            return path, scaffold
    parts = path.split()
    if len(parts) >= 2:
        try:
            scaffold = normalize_scaffold(parts[-1])
        except ValueError:
            return path, SCAFFOLD_MINIMAL
        return " ".join(parts[:-1]).strip(), scaffold
    return path, SCAFFOLD_MINIMAL


def _write_new(path: Path, body: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


def _gitignore_python() -> str:
    return (
        ".eurika/\n"
        "__pycache__/\n"
        "*.py[cod]\n"
        ".venv/\n"
        "venv/\n"
        ".mypy_cache/\n"
        ".pytest_cache/\n"
        ".ruff_cache/\n"
        "dist/\n"
        "build/\n"
        "*.egg-info/\n"
    )


def _pyproject(*, name: str, pkg: str, cli: bool) -> str:
    scripts = ""
    if cli:
        scripts = f'\n[project.scripts]\n{pkg} = "{pkg}.__main__:main"\n'
    return (
        f"[project]\n"
        f'name = "{pkg}"\n'
        f'version = "0.1.0"\n'
        f'description = "{name} — Eurika python scaffold"\n'
        f'requires-python = ">=3.11"\n'
        f"{scripts}\n"
        f"[build-system]\n"
        f'requires = ["setuptools>=69"]\n'
        f'build-backend = "setuptools.build_meta"\n'
        f"\n"
        f"[tool.setuptools.packages.find]\n"
        f'where = ["src"]\n'
    )


def _pkg_init(pkg: str) -> str:
    return f'"""Package ``{pkg}`` (Eurika python scaffold)."""\n\n__version__ = "0.1.0"\n'


def _pkg_main(pkg: str) -> str:
    return (
        f'"""CLI entry for ``{pkg}``."""\n'
        f"from __future__ import annotations\n\n"
        f"\n"
        f"def main() -> int:\n"
        f'    print("{pkg} 0.1.0")\n'
        f"    return 0\n"
        f"\n"
        f"\n"
        f'if __name__ == "__main__":\n'
        f"    raise SystemExit(main())\n"
    )


def _smoke_test(pkg: str) -> str:
    return (
        f'"""Smoke: scaffold package imports."""\n'
        f"from {pkg} import __version__\n\n"
        f"\n"
        f"def test_version() -> None:\n"
        f'    assert __version__ == "0.1.0"\n'
    )


def apply_scaffold(
    root: Path,
    *,
    scaffold: str = SCAFFOLD_MINIMAL,
    name: str | None = None,
    write_readme: bool = True,
) -> list[str]:
    """Write template files that do not already exist. Returns new artifact paths."""
    kind = normalize_scaffold(scaffold)
    title = name or root.name
    pkg = package_name_for(title)
    artifacts: list[str] = []

    def add(path: Path, body: str) -> None:
        if _write_new(path, body):
            artifacts.append(str(path))

    if write_readme:
        readme = (
            f"# {title}\n\n"
            f"Bootstrapped by Eurika Project Creation (scaffold: `{kind}`).\n"
            "Next: open in Eurika and run `eurika scan .`.\n"
        )
        if kind in {SCAFFOLD_PYTHON, SCAFFOLD_PYTHON_CLI}:
            readme += (
                f"\n```bash\n"
                f"python -m {pkg}\n"
                f"```\n"
            )
        add(root / "README.md", readme)

    if kind == SCAFFOLD_MINIMAL:
        return artifacts

    add(root / ".gitignore", _gitignore_python())
    add(root / "pyproject.toml", _pyproject(name=title, pkg=pkg, cli=(kind == SCAFFOLD_PYTHON_CLI)))
    src = root / "src" / pkg
    add(src / "__init__.py", _pkg_init(pkg))
    if kind == SCAFFOLD_PYTHON_CLI:
        add(src / "__main__.py", _pkg_main(pkg))
    add(root / "tests" / "test_smoke.py", _smoke_test(pkg))
    return artifacts


def scaffold_ids() -> Iterable[str]:
    return SCAFFOLD_IDS
