"""Shared dataclasses for architecture planning layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PlanStep:
    """Single step in an architecture plan."""

    id: str
    target: str
    kind: str
    priority: int
    rationale: str
    hints: List[str]
    smell_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitecturePlan:
    """Top-level architecture plan container."""

    project_root: str
    generated_from: Dict[str, Any]
    steps: List[PlanStep]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": self.project_root,
            "generated_from": self.generated_from,
            "steps": [s.to_dict() for s in self.steps],
        }
