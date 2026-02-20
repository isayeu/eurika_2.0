"""Native agent runtime loop for Eurika."""

from __future__ import annotations

from typing import Any, Callable

from .models import AgentCycleResult, AgentMode, AgentStage, ToolResult

_STAGES: tuple[AgentStage, ...] = ("observe", "reason", "propose", "apply", "verify", "learn")


def _normalize_result(value: Any) -> ToolResult:
    if isinstance(value, ToolResult):
        return value
    return ToolResult(status="ok", payload=value)


def run_agent_cycle(
    *,
    mode: AgentMode,
    tools: Any,
) -> AgentCycleResult:
    """Execute a full runtime cycle through configured tool adapters."""
    cycle = AgentCycleResult(mode=mode)
    stage_input: dict[str, Any] = {}
    for stage in _STAGES:
        fn: Callable[..., Any] | None = getattr(tools, stage, None)
        if fn is None:
            continue
        try:
            raw = fn(stage_input)
            result = _normalize_result(raw)
        except Exception as exc:  # pragma: no cover - defensive
            result = ToolResult(status="error", message=str(exc), payload=None)
        cycle.stages.append(stage)
        cycle.stage_outputs[stage] = {
            "status": result.status,
            "message": result.message,
            "payload": result.payload,
        }
        stage_input[stage] = result.payload
        if stage == "apply":
            cycle.payload = result.payload
        if result.status == "error":
            break
    return cycle
