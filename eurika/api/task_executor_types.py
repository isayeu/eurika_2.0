"""Types for task_executor: TaskSpec, ExecutionReport, constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

RiskLevel = str  # low | medium | high
MAX_PATCH_OPS = 20
MAX_PATCH_TEXT = 20_000


@dataclass(slots=True)
class TaskSpec:
    intent: str
    target: str = ""
    message: str = ""
    steps: List[str] = field(default_factory=list)
    risk_level: RiskLevel = "low"
    requires_confirmation: bool = False
    entities: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionReport:
    ok: bool
    summary: str
    applied_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    artifacts_changed: List[str] = field(default_factory=list)
    error: Optional[str] = None


CapabilityFn = Callable[[Path, TaskSpec], ExecutionReport]
