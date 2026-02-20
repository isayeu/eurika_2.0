"""Tool adapter layer used by the native runtime (ROADMAP 2.7.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ToolResult

@dataclass(slots=True)
class OrchestratorToolset:
    """Minimal toolset adapter wrapping orchestrator logic. Uses ToolContract for scan."""

    path: Path
    mode: str
    cycle_runner: Callable[[], dict[str, Any]]
    contract: Any = None  # ToolContract for primitive ops (ROADMAP 2.7.2); observe keeps lightweight to avoid double scan

    def observe(self, _: dict[str, Any]) -> ToolResult:
        return ToolResult(payload={"path": str(self.path), "mode": self.mode})

    def reason(self, _: dict[str, Any]) -> ToolResult:
        return ToolResult(payload={"mode": self.mode, "strategy": "existing_orchestrator"})

    def propose(self, _: dict[str, Any]) -> ToolResult:
        return ToolResult(payload={"decision": "apply"})

    def apply(self, _: dict[str, Any]) -> ToolResult:
        return ToolResult(payload=self.cycle_runner())

    def verify(self, stage_input: dict[str, Any]) -> ToolResult:
        payload = stage_input.get("apply")
        ok = isinstance(payload, dict) and not payload.get("error")
        return ToolResult(payload={"ok": ok})

    def learn(self, stage_input: dict[str, Any]) -> ToolResult:
        return ToolResult(payload={"captured": True, "verify": stage_input.get("verify")})
