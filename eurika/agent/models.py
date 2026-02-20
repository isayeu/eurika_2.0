"""Data models for native Eurika agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AgentMode = Literal["assist", "hybrid", "auto"]
AgentStage = Literal["observe", "reason", "propose", "apply", "verify", "learn"]


@dataclass(slots=True)
class ToolResult:
    """Normalized result shape for tool adapter calls."""

    status: Literal["ok", "error"] = "ok"
    payload: Any = None
    message: str = ""


@dataclass(slots=True)
class AgentCycleResult:
    """Result of one agent runtime cycle."""

    mode: AgentMode
    stages: list[AgentStage] = field(default_factory=list)
    stage_outputs: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
