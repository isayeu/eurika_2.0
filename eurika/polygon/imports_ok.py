"""DRILL_UNUSED_IMPORTS: remove_unused_import — добавить неиспользуемые импорты, fix удалит."""
import os
import re
import json
from pathlib import Path


def polygon_imports_ok() -> Path:
    """После fix остаётся только Path."""
    return Path(".")
