"""
ExecutionContext — единый контекст pipeline (ROADMAP §5.7, review 2026 II).

Только Orchestrator мутирует context. Все сервисы — чистые.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from eurika.reasoning.planner.models import (
        ArchitectureSnapshot,
        RefactorAction,
        RefactorCandidate,
        RiskReport,
    )


@dataclass
class ExecutionContext:
    """
    Unified context for fix-cycle pipeline (review 2026 II).

    Only the Orchestrator should mutate this. All services are pure.
    """

    snapshot_before: Optional["ArchitectureSnapshot"] = None
    candidates: Optional[List["RefactorCandidate"]] = None
    selected_action: Optional["RefactorAction"] = None
    simulated_snapshot: Optional["ArchitectureSnapshot"] = None
    snapshot_after: Optional["ArchitectureSnapshot"] = None
    risk_report: Optional["RiskReport"] = None
    delta_score: Optional[float] = None
