"""Serve handler (P0.4 split)."""

from __future__ import annotations

from typing import Any


def handle_serve(args: Any) -> int:
    """Run JSON API HTTP server for future UI."""
    from eurika.api.serve import run_server

    run_server(host=args.host, port=args.port, project_root=args.path)
    return 0
