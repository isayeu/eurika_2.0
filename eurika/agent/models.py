"""Data models for native Eurika agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

AgentMode = Literal["assist", "hybrid", "auto"]
AgentStage = Literal["observe", "reason", "propose", "apply", "verify", "learn"]


class AgentRuntimeState(str, Enum):
    """Formal runtime state model for one agent cycle."""

    IDLE = "idle"
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"


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
    state: AgentRuntimeState = AgentRuntimeState.IDLE
    state_history: list[AgentRuntimeState] = field(
        default_factory=lambda: [AgentRuntimeState.IDLE]
    )
    stages: list[AgentStage] = field(default_factory=list)
    stage_outputs: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
