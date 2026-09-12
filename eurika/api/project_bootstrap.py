"""Project Creation pipeline v0 (VISION Stage 6 — multi-project).

Create or initialize a project root with ``.eurika/`` + stub ``self_map.json``.
Does not switch Qt root by itself — Chat may return ``open_project`` for the UI.
Never touches Market / live money.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from eurika.api.project_scaffolds import (
    SCAFFOLD_MINIMAL,
    apply_scaffold,
    normalize_scaffold,
)
from eurika.storage.paths import STORAGE_DIR, ensure_storage_dir

BOOTSTRAP_VERSION = 2
STUB_SELF_MAP: Dict[str, Any] = {
    "modules": [],
    "dependencies": {},
    "summary": {"files": 0, "total_lines": 0},
    "meta": {"bootstrap": "project_creation_v0"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_create_project_path(current_root: Path | str, raw: str) -> Path:
    """Resolve user path: absolute/~ → as-is; bare name → sibling of current root."""
    text = (raw or "").strip().strip("\"'")
    if not text:
        raise ValueError("empty project path")
    current = Path(current_root).expanduser().resolve()
    expanded = Path(text).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    # Relative with separators → under current root
    if "/" in text or "\\" in text:
        return (current / expanded).resolve()
    # Bare name → sibling directory next to the active project
    return (current.parent / expanded.name).resolve()


def create_project(
    path: Path | str,
    *,
    name: Optional[str] = None,
    force: bool = False,
    write_readme: bool = True,
    scaffold: str = SCAFFOLD_MINIMAL,
) -> Dict[str, Any]:
    """Create directory (if needed) and bootstrap Eurika storage + optional scaffold.

    Returns a result dict with ``ok``, ``path``, ``created_dir``, ``initialized``,
    ``already``, ``artifacts``, ``scaffold``, and optional ``error``.
    """
    try:
        scaffold_id = normalize_scaffold(scaffold)
    except ValueError as exc:
        return {
            "ok": False,
            "version": BOOTSTRAP_VERSION,
            "path": str(Path(path).expanduser()),
            "created_dir": False,
            "initialized": False,
            "already": False,
            "artifacts": [],
            "scaffold": (scaffold or SCAFFOLD_MINIMAL),
            "error": str(exc),
        }
    root = Path(path).expanduser().resolve()
    result: Dict[str, Any] = {
        "ok": False,
        "version": BOOTSTRAP_VERSION,
        "path": str(root),
        "created_dir": False,
        "initialized": False,
        "already": False,
        "artifacts": [],
        "scaffold": scaffold_id,
        "error": None,
    }

    if root.exists() and root.is_file():
        result["error"] = f"path exists and is a file: {root}"
        return result

    created_dir = False
    if not root.exists():
        try:
            root.mkdir(parents=True, exist_ok=False)
            created_dir = True
        except OSError as exc:
            result["error"] = f"cannot create directory: {exc}"
            return result
    result["created_dir"] = created_dir

    eurika_dir = root / STORAGE_DIR
    self_map = root / "self_map.json"
    already = eurika_dir.is_dir() and self_map.is_file()
    if already and not force:
        result["ok"] = True
        result["already"] = True
        result["initialized"] = True
        result["artifacts"] = [str(eurika_dir), str(self_map)]
        return result

    try:
        ensure_storage_dir(root)
        # Empty event log so ProjectMemory / chat have a stable file
        events = eurika_dir / "events.json"
        # ``--force`` refreshes bootstrap metadata and the self-map stub, but
        # event history belongs to the project and must remain append-only.
        if not events.is_file():
            # EventStore persists an envelope, not a bare JSON array.
            events.write_text('{"events": []}\n', encoding="utf-8")
            result["artifacts"].append(str(events))

        stamp = {
            "version": BOOTSTRAP_VERSION,
            "created_at": _utc_now(),
            "pipeline": "project_creation_v0",
            "scaffold": scaffold_id,
            "name": (name or root.name),
        }
        marker = eurika_dir / "project_bootstrap.json"
        marker.write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["artifacts"].append(str(marker))

        if not self_map.is_file() or force:
            payload = dict(STUB_SELF_MAP)
            payload["meta"] = {
                **STUB_SELF_MAP["meta"],
                "project_name": name or root.name,
                "created_at": stamp["created_at"],
            }
            self_map.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["artifacts"].append(str(self_map))

        extra = apply_scaffold(
            root,
            scaffold=scaffold_id,
            name=name or root.name,
            write_readme=write_readme,
        )
        result["artifacts"].extend(extra)
    except OSError as exc:
        result["error"] = f"bootstrap failed: {exc}"
        return result

    result["ok"] = True
    result["initialized"] = True
    result["artifacts"] = sorted(set(result["artifacts"]))
    return result


def format_create_project_text(result: Dict[str, Any]) -> str:
    """Human-readable Chat/CLI summary."""
    if not result.get("ok"):
        return f"Не удалось создать проект: {result.get('error') or 'unknown error'}"
    path = result.get("path") or ""
    scaffold = result.get("scaffold") or SCAFFOLD_MINIMAL
    lines = ["Project Creation v0"]
    if result.get("already"):
        lines.append(f"Уже инициализирован: `{path}`")
    else:
        action = "Создан каталог и" if result.get("created_dir") else "Инициализирован"
        lines.append(
            f"{action} `.eurika/` + scaffold `{scaffold}`: `{path}`"
        )
    arts = result.get("artifacts") or []
    if arts:
        lines.append("Артефакты:")
        for a in arts[:12]:
            lines.append(f"- `{a}`")
    lines.append("Открой корень во вкладке workspace (rail) или New chat → этот каталог.")
    lines.append("Дальше: `eurika scan .` / Chat «что за проект?».")
    lines.append("CLI: `eurika init <path>`")
    return "\n".join(lines)
