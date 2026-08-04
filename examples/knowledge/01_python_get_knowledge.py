#!/usr/bin/env python3
"""Пример: вызов get_knowledge(project_root, topic) через публичный API.

Использование:
  python examples/knowledge/01_python_get_knowledge.py <project_root> [--topic TOPIC] [--online]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Knowledge Layer by topic")
    parser.add_argument("project_root", type=Path, help="Project root (e.g. .)")
    parser.add_argument("--topic", default="python", help="Topic (e.g. cyclic_imports, typing)")
    parser.add_argument("--online", action="store_true", help="Force online fetch (bypass cache)")
    args = parser.parse_args()

    root = args.project_root.resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    from eurika.api import get_knowledge

    result = get_knowledge(root, args.topic, online=args.online)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
