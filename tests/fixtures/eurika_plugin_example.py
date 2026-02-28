"""Example R5 plugin: minimal analyzer that returns one dummy smell.

Usage: add to .eurika/plugins.toml:
  [[plugins]]
  entry_point = "tests.fixtures.eurika_plugin_example:analyze"

Or pyproject.toml [tool.eurika.plugins]:
  example = "tests.fixtures.eurika_plugin_example:analyze"
"""

from pathlib import Path
from typing import List

from eurika.smells.detector import ArchSmell


def analyze(project_root: Path) -> List[ArchSmell]:
    """Example plugin: returns one placeholder smell if main.py exists."""
    root = Path(project_root).resolve()
    main = root / "main.py"
    if not main.exists():
        return []
    rel = str(main.relative_to(root))
    return [
        ArchSmell(
            type="example_plugin_smell",
            nodes=[rel],
            severity=1.0,
            description="Example plugin detected main.py (demo)",
        )
    ]
