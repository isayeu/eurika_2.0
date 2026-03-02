"""Clean-imports handler (P0.4 split)."""

from __future__ import annotations

import json
import sys
from typing import Any

from .core_handlers_common import _check_path


def handle_clean_imports(args: Any) -> int:
    """Remove unused imports from Python files (3.1-arch.5 thin)."""
    from eurika.api import clean_imports_scan_apply

    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    apply_changes = getattr(args, "apply", False)
    modified = clean_imports_scan_apply(path, apply_changes=apply_changes)
    if not modified:
        print("eurika: no unused imports found.", file=sys.stderr)
        return 0
    if apply_changes:
        print(f"eurika: removed unused imports from {len(modified)} file(s).", file=sys.stderr)
    else:
        print(f"eurika: would remove unused imports from {len(modified)} file(s) (use --apply to write):", file=sys.stderr)
    for m in modified[:10]:
        print(f"  {m}", file=sys.stderr)
    if len(modified) > 10:
        print(f"  ... and {len(modified) - 10} more", file=sys.stderr)
    print(json.dumps({"modified": modified}, indent=2, ensure_ascii=False))
    return 0
