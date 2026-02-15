"""Extracted from parent module to reduce complexity."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class FileInfo:
    path: str
    lines: int
    functions: List[str]
    classes: List[str]

@dataclass
class Smell:
    file: str
    location: str
    kind: str
    message: str
    metric: Optional[int] = None
