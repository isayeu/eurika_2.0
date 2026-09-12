"""DRILL_UNUSED_IMPORTS: remove_unused_import — неиспользуемые импорты, fix удалит."""
from pathlib import Path


def polygon_imports_ok() -> Path:
    """После fix остаётся только Path."""
    return Path(".")
