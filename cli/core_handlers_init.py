"""CLI: init — Project Creation pipeline v0 (VISION Stage 6)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core_handlers_common import _check_path


def handle_init(args: Any) -> int:
    from eurika.api.project_bootstrap import create_project, format_create_project_text

    raw = getattr(args, "path", None)
    path = Path(raw or ".").expanduser().resolve()
    # Allow creating a path that does not exist yet — skip _check_path exists check.
    parent = path.parent
    if not parent.exists():
        print(f"Parent directory does not exist: {parent}", flush=True)
        return 1
    if path.exists() and path.is_file():
        print(f"Path is a file: {path}", flush=True)
        return 1
    if path.exists() and _check_path(path) != 0:
        return 1

    result = create_project(
        path,
        name=getattr(args, "name", None) or None,
        force=bool(getattr(args, "force", False)),
        write_readme=not bool(getattr(args, "no_readme", False)),
        scaffold=getattr(args, "scaffold", None) or "minimal",
    )
    if bool(getattr(args, "json", False)) or bool(getattr(args, "quiet", False)):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_create_project_text(result))
    return 0 if result.get("ok") else 1
