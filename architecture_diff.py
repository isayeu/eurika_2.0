"""
Backward-compatible re-export. Implementation lives in eurika.evolution.diff (v0.9).

CLI: python architecture_diff.py old_self_map.json new_self_map.json
"""

from eurika.evolution.diff import *  # noqa: F401,F403

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python architecture_diff.py old_self_map.json new_self_map.json")
        raise SystemExit(1)
    from eurika.evolution.diff import main_cli

    main_cli(sys.argv[1], sys.argv[2])
