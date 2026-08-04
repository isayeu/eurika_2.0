"""
Standalone CLI launcher for architecture diff.

Usage: python architecture_diff.py old_self_map.json new_self_map.json
Delegates to eurika arch-diff. Implementation: eurika.evolution.diff
"""

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python architecture_diff.py old_self_map.json new_self_map.json")
        sys.exit(1)
    # Delegate to eurika arch-diff (avoids wildcard re-export)
    from eurika.evolution.diff import main_cli

    main_cli(sys.argv[1], sys.argv[2])
