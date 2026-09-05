"""Serializable product panels shared by Desktop, Qt, and remote adapters."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from eurika.api.diff_api import preview_operation
from eurika.api.team_api import get_pending_plan, save_approvals
from eurika.ml.root import resolve_market_root

from .protocol import ERR_APPROVAL_REQUIRED, ERR_INVALID_PARAMS, RpcError
from .workspace import EventSink, WorkspaceTools


COMMANDS = (
    "scan",
    "doctor",
    "fix",
    "cycle",
    "explain",
    "report-snapshot",
    "learning-kpi",
    "self-check",
)


class PanelService:
    def __init__(self, tools: WorkspaceTools) -> None:
        self.tools = tools

    def state(self, panel: Any) -> dict[str, Any]:
        if panel == "approvals":
            return {"panel": panel, "data": get_pending_plan(self.tools.root)}
        if panel == "commands":
            return {
                "panel": panel,
                "commands": [
                    {
                        "id": command,
                        "requiresApproval": command not in {"report-snapshot", "learning-kpi"},
                    }
                    for command in COMMANDS
                ],
            }
        if panel == "market":
            return {"panel": panel, "data": self._market_state()}
        if panel == "context":
            return self._context_state()
        raise RpcError(ERR_INVALID_PARAMS, f"Unknown panel: {panel}")

    def approval_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        operation = params.get("operation")
        if not isinstance(operation, dict):
            raise RpcError(ERR_INVALID_PARAMS, "operation must be an object")
        return preview_operation(self.tools.root, operation)

    def approval_save(self, params: dict[str, Any]) -> dict[str, Any]:
        self._approved(params, "approval decisions")
        operations = params.get("operations")
        if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
            raise RpcError(ERR_INVALID_PARAMS, "operations must be an array of objects")
        return save_approvals(self.tools.root, operations)

    def command_run(
        self,
        params: dict[str, Any],
        *,
        cancel: threading.Event,
        emit: EventSink,
    ) -> dict[str, Any]:
        command = params.get("command")
        if command not in COMMANDS:
            raise RpcError(ERR_INVALID_PARAMS, f"Unsupported command: {command}")
        if command not in {"report-snapshot", "learning-kpi"}:
            self._approved(params, f"command {command}")
        extra = params.get("args", [])
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            raise RpcError(ERR_INVALID_PARAMS, "args must be a string array")
        argv = [sys.executable, "-m", "eurika_cli", str(command)]
        if command == "explain":
            module = params.get("module")
            if not isinstance(module, str) or not module:
                raise RpcError(ERR_INVALID_PARAMS, "explain requires module")
            argv.extend([module, str(self.tools.root)])
        else:
            argv.append(str(self.tools.root))
        argv.extend(extra)
        return self.tools._run_process(
            argv,
            cwd=self.tools.root,
            timeout_ms=max(1, min(int(params.get("timeoutMs", 900_000)), 3_600_000)),
            cancel=cancel,
            emit=emit,
        )

    @staticmethod
    def _approved(params: dict[str, Any], operation: str) -> None:
        if params.get("approval") is not True:
            raise RpcError(
                ERR_APPROVAL_REQUIRED,
                f"Explicit approval is required for {operation}",
                {"operation": operation, "requiresApproval": True},
            )

    def _market_state(self) -> dict[str, Any]:
        root = resolve_market_root() / ".eurika" / "ml"
        portfolio = self._read_json(root / "paper_portfolio.json", {})
        opens = self._read_json(root / "open_paper.json", {})
        shadows = self._read_json(root / "shadow_open.json", {})
        pending = self._read_json(root / "pending_orders.json", [])
        gate = self._read_json(root / "weights" / "entry_cost_gate.json", {})
        events: list[dict[str, Any]] = []
        journal = root / "market_journal.jsonl"
        try:
            lines = journal.read_text(encoding="utf-8").splitlines()[-100:]
        except OSError:
            lines = []
        for line in lines:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return {
            "portfolio": portfolio,
            "openPositions": self._items(opens, "positions"),
            "shadowPositions": self._items(shadows, "positions"),
            "pendingOrders": pending if isinstance(pending, list) else [],
            "costGate": gate,
            "events": events,
        }

    def _context_state(self) -> dict[str, Any]:
        """Qt-parity Agent «Контекст» text from dialog_state.json."""
        from eurika.api.chat_context import format_agent_context_panel
        from eurika.api.learning_api import get_chat_dialog_state
        from eurika.api.task_executor import is_pending_plan_valid

        state = get_chat_dialog_state(self.tools.root)
        pending = state.get("pending_plan") if isinstance(state, dict) else {}
        plan_valid = bool(isinstance(pending, dict) and pending and is_pending_plan_valid(pending))
        plan_stale = bool(isinstance(pending, dict) and pending and not plan_valid)
        text = format_agent_context_panel(
            state, plan_valid=plan_valid, plan_stale=plan_stale
        )
        return {
            "panel": "context",
            "text": text,
            "data": state,
            "planValid": plan_valid,
            "planStale": plan_stale,
        }

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    @staticmethod
    def _items(value: Any, key: str) -> list[Any]:
        if isinstance(value, dict) and isinstance(value.get(key), list):
            return value[key]
        return []
