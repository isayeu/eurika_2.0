"""Typed contracts for fix-cycle orchestration payloads.

Boundary contracts are intentionally permissive (`dict[str, Any]`) to keep
compatibility with existing dynamic payload builders while we incrementally
introduce stricter schemas.
"""

from __future__ import annotations

from typing import Any, TypedDict, TypeAlias


OperationRecord: TypeAlias = dict[str, Any]
PatchPlan: TypeAlias = dict[str, Any]


class DecisionSummary(TypedDict):
    """Compact decision gate counters for operator UX."""

    blocked_by_policy: int
    blocked_by_critic: int
    blocked_by_human: int


class TelemetryPayload(TypedDict, total=False):
    """Operational telemetry persisted to fix report."""

    operations_total: int
    modified_count: int
    skipped_count: int
    apply_rate: float
    no_op_rate: float
    rollback_rate: float
    verify_duration_ms: int
    median_verify_time_ms: int


class SafetyGatesPayload(TypedDict):
    """Safety gates outcome for verify/rollback behavior."""

    verify_required: bool
    auto_rollback_enabled: bool
    verify_ran: bool
    verify_passed: bool | None
    rollback_done: bool


FixReport: TypeAlias = dict[str, Any]
