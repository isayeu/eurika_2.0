"""
ExecutionContext — единый контекст pipeline (ROADMAP §5.7, review 2026 II).

Только Orchestrator мутирует context. Все сервисы — чистые.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class ExecutionContext:
    """
    Unified context for fix-cycle pipeline (review 2026 II).

    Only the Orchestrator should mutate this. All services are pure.
    """

    snapshot_before: Optional[Any] = None  # ArchitectureSnapshot
    candidates: Optional[List[Any]] = None  # RefactorCandidate[]
    selected_action: Optional[Any] = None  # RefactorAction
    simulated_snapshot: Optional[Any] = None  # ArchitectureSnapshot
    snapshot_after: Optional[Any] = None  # ArchitectureSnapshot
    risk_report: Optional[Any] = None  # RiskReport
    delta_score: Optional[float] = None
