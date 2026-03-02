"""Universal task executor for chat pipeline.

interpret -> authorize -> execute -> verify -> report
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .task_executor_executors import (
    _execute_create,
    _execute_delete,
    _execute_project_ls,
    _execute_project_tree,
    _execute_refactor,
    _execute_run_command,
    _execute_run_lint,
    _execute_run_tests,
    _execute_save,
    _execute_ui_add_empty_tab,
    _execute_ui_remove_tab,
    _execute_ui_tabs,
)
from .task_executor_patch import execute_code_edit_patch
from .task_executor_types import (
    ExecutionReport,
    TaskSpec,
)

# Re-exports for backward compatibility
from .task_executor_helpers import TASK_BACKUP_DIR, run_pytest as _run_pytest  # noqa: F401
from .task_executor_types import MAX_PATCH_OPS, MAX_PATCH_TEXT, RiskLevel  # noqa: F401

CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "ui_tabs": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_ui_tabs},
    "project_ls": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_project_ls},
    "project_tree": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_project_tree},
    "run_tests": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_run_tests},
    "run_lint": {"risk_level": "low", "requires_confirmation": False, "executor": _execute_run_lint},
    "run_command": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_run_command},
    "ui_add_empty_tab": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_ui_add_empty_tab},
    "ui_remove_tab": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_ui_remove_tab},
    "create": {"risk_level": "medium", "requires_confirmation": True, "executor": _execute_create},
    "delete": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_delete},
    "save": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_save},
    "refactor": {"risk_level": "high", "requires_confirmation": True, "executor": _execute_refactor},
    "code_edit_patch": {"risk_level": "high", "requires_confirmation": True, "executor": execute_code_edit_patch},
}


def build_task_spec(
    *,
    intent: str,
    target: str = "",
    message: str = "",
    plan_steps: Optional[List[str]] = None,
    entities: Optional[Dict[str, str]] = None,
) -> TaskSpec:
    info = CAPABILITIES.get(intent, {})
    return TaskSpec(
        intent=intent,
        target=target,
        message=message,
        steps=list(plan_steps or []),
        risk_level=str(info.get("risk_level", "medium")),
        requires_confirmation=bool(info.get("requires_confirmation", True)),
        entities=dict(entities or {}),
    )


def make_pending_plan(spec: TaskSpec, ttl_sec: int = 600) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "token": secrets.token_hex(8),
        "intent": spec.intent,
        "target": spec.target,
        "entities": dict(spec.entities),
        "risk_level": spec.risk_level,
        "requires_confirmation": spec.requires_confirmation,
        "steps": list(spec.steps),
        "created_ts": now,
        "expires_ts": now + max(ttl_sec, 60),
        "status": "pending_confirmation",
    }


def is_pending_plan_valid(plan: Dict[str, Any]) -> bool:
    if not isinstance(plan, dict):
        return False
    if str(plan.get("status") or "") != "pending_confirmation":
        return False
    expires = int(plan.get("expires_ts") or 0)
    return expires > int(time.time())


def execute_spec(root: Path, spec: TaskSpec) -> ExecutionReport:
    info = CAPABILITIES.get(spec.intent)
    if not info:
        return ExecutionReport(ok=False, summary="unknown capability", error=f"unsupported intent: {spec.intent}")
    executor = info.get("executor")
    if not callable(executor):
        return ExecutionReport(ok=False, summary="executor missing", error=f"no executor for {spec.intent}")
    return executor(root, spec)


def has_capability(intent: str) -> bool:
    """Check if intent is backed by executor registry."""
    return intent in CAPABILITIES
