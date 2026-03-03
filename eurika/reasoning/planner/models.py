"""
Domain models for architecture planning (ROADMAP v3.0 Stage 2, §5.5, §5.7).

Unified types: ArchitectureModel, ArchitectureSnapshot, RefactorAction, RiskReport, SmellReport.
Replaces fragmented structures across planner/action_plan/patch_plan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph
    from eurika.analysis.metric_vector import MetricVector


@dataclass
class SmellReport:
    """
    Extended smell report with remediation and severity level.

    Wraps/extends ArchSmell for planning and reporting use.
    """

    type: str
    nodes: List[str]
    severity: float
    description: str
    remediation_hint: Optional[str] = None
    level: str = "medium"  # high | medium | low

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_arch_smell(cls, smell: Any, *, hint: Optional[str] = None) -> "SmellReport":
        """Build from eurika.smells ArchSmell."""
        level = "high" if (smell.severity or 0) >= 5 else "medium" if (smell.severity or 0) >= 2 else "low"
        return cls(
            type=getattr(smell, "type", ""),
            nodes=list(getattr(smell, "nodes", []) or []),
            severity=float(getattr(smell, "severity", 0) or 0),
            description=getattr(smell, "description", ""),
            remediation_hint=hint,
            level=level,
        )


@dataclass
class RiskProfile:
    """Risk profile for a single action or aggregate."""

    score: float  # 0..1, higher = riskier
    level: str  # high | medium | low
    factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RefactorAction:
    """
    Single refactor action with preconditions, transformation, postconditions.

    Strict Action Contract (review §4): replaces fragmented Action/PatchOperation semantics.
    """

    type: str
    target: str
    description: str
    risk_profile: RiskProfile
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    expected_benefit: float = 0.0
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.risk_profile:
            d["risk_profile"] = self.risk_profile.to_dict()
        return d

    @classmethod
    def from_action(cls, action: Any) -> "RefactorAction":
        """Build from eurika.reasoning.action_plan.Action."""
        risk = float(getattr(action, "risk", 0) or 0)
        level = "high" if risk >= 0.7 else "medium" if risk >= 0.3 else "low"
        return cls(
            type=getattr(action, "type", ""),
            target=getattr(action, "target", ""),
            description=getattr(action, "description", ""),
            risk_profile=RiskProfile(score=risk, level=level, factors=[]),
            expected_benefit=float(getattr(action, "expected_benefit", 0) or 0),
        )


@dataclass
class RiskReport:
    """
    Aggregated risk report for a plan or project.

    Used for simulation-first apply and risk-based patching.
    """

    total_risk: float
    level: str
    per_action: List[Dict[str, Any]] = field(default_factory=list)
    factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitectureSnapshot:
    """
    Unified state model: graph + MetricVector + smells (ROADMAP §5.7, review §3).

    Single source of truth for architecture state. Used by ExecutionContext, report.
    Strengthened: root, summary, history, diff — для совместимости с core/pipeline.
    """

    graph: Any  # ProjectGraph
    metrics: "MetricVector"
    smells: List[SmellReport]
    root: Optional[Path] = None
    summary: Optional[Dict[str, Any]] = None
    history: Optional[Dict[str, Any]] = None
    diff: Optional[Dict[str, Any]] = None

    @classmethod
    def from_graph_and_smells(
        cls,
        graph: "ProjectGraph",
        smells: List[Any],
        *,
        root: Optional[Path] = None,
        summary: Optional[Dict[str, Any]] = None,
        history: Optional[Dict[str, Any]] = None,
        diff: Optional[Dict[str, Any]] = None,
    ) -> "ArchitectureSnapshot":
        """Build from ProjectGraph and ArchSmell list."""
        from eurika.analysis.metric_vector import compute_metric_vector
        from eurika.smells.detector import get_remediation_hint

        metrics = compute_metric_vector(graph, smells)
        smell_reports = [
            SmellReport.from_arch_smell(s, hint=get_remediation_hint(getattr(s, "type", "")))
            for s in smells
        ]
        return cls(
            graph=graph,
            metrics=metrics,
            smells=smell_reports,
            root=root,
            summary=summary,
            history=history,
            diff=diff,
        )

    @classmethod
    def from_core_snapshot(cls, core_snap: Any) -> "ArchitectureSnapshot":
        """
        Build unified snapshot from core.ArchitectureSnapshot (pipeline output).

        Bridge for pipeline → planner/report. Avoids dict/loosely-coupled passing (review §3).
        """
        return cls.from_graph_and_smells(
            core_snap.graph,
            core_snap.smells,
            root=getattr(core_snap, "root", None),
            summary=getattr(core_snap, "summary", None),
            history=getattr(core_snap, "history", None),
            diff=getattr(core_snap, "diff", None),
        )


@dataclass
class RefactorCandidate:
    """Candidate action with estimated ΔEnergy and risk (review 2026 II)."""

    action: RefactorAction
    estimated_delta: float
    risk_score: float


@dataclass
class ArchitectureModel:
    """
    Snapshot of project architecture state (ROADMAP v3.0 Stage 2).

    Unifies graph, topology, smells, and metrics into a single domain model.
    """

    project_root: str
    smells: List[SmellReport]
    cohesion: float = 0.0  # 0..1
    coupling: float = 0.0  # 0..1
    complexity: float = 0.0  # 0..1
    modularity: float = 0.0  # 0..1
    health_score: int = 0  # 0..100
    health_level: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_graph_and_smells(
        cls,
        project_root: str,
        graph: Any,
        smells: List[Any],
        health: Optional[Dict[str, Any]] = None,
    ) -> "ArchitectureModel":
        """
        Build ArchitectureModel from ProjectGraph and ArchSmell list.

        Uses eurika.analysis.scoring for cohesion/coupling/complexity/modularity.
        """
        from eurika.analysis.scoring import compute_architecture_scores
        from eurika.smells.detector import get_remediation_hint

        scores = compute_architecture_scores(graph, smells)
        smell_reports = [
            SmellReport.from_arch_smell(s, hint=get_remediation_hint(getattr(s, "type", "")))
            for s in smells
        ]
        health = health or {}
        return cls(
            project_root=project_root,
            smells=smell_reports,
            cohesion=scores.get("cohesion", 0),
            coupling=scores.get("coupling", 0),
            complexity=scores.get("complexity", 0),
            modularity=scores.get("modularity", 0),
            health_score=int(health.get("score", 0)),
            health_level=str(health.get("level", "medium")),
            metadata={"factors": health.get("factors", [])},
        )


@dataclass
class SimulationResult:
    """
    Result of simulate_patch (ROADMAP v3.0 Stage 2).

    Type-safe wrapper for patch_engine.simulate_patch output.
    """

    would_modify: List[str]
    would_skip: List[str]
    skipped_reasons: Dict[str, str]
    errors: List[str]
    operations_count: int

    @classmethod
    def from_simulate_dict(cls, d: Dict[str, Any]) -> "SimulationResult":
        """Build from patch_engine.simulate_patch return value."""
        return cls(
            would_modify=list(d.get("would_modify") or []),
            would_skip=list(d.get("would_skip") or []),
            skipped_reasons=dict(d.get("skipped_reasons") or {}),
            errors=list(d.get("errors") or []),
            operations_count=int(d.get("operations_count", 0)),
        )


# Risk scores by kind (ROADMAP v3.0 Stage 3 — risk-based patching).
# Aligned with eurika.agent.policy._estimate_risk.
_KIND_RISK_SCORE: Dict[str, float] = {
    "remove_unused_import": 0.2,
    "remove_cyclic_import": 0.2,
    "fix_import": 0.2,
    "create_module_stub": 0.2,
    "split_module": 0.8,
    "extract_class": 0.8,
    "extract_block_to_helper": 0.8,
    "refactor_module": 0.8,
    "refactor_code_smell": 0.6,
    "introduce_facade": 0.7,
    "llm_extract_block": 0.9,
}


def risk_report_from_plan(plan: Dict[str, Any]) -> RiskReport:
    """
    Build RiskReport from patch plan (ROADMAP v3.0 Stage 3).

    Aggregates per-operation risk for risk-based patching decisions.
    """
    ops = plan.get("operations") or []
    if not ops:
        return RiskReport(total_risk=0.0, level="low", per_action=[], factors=[], recommendations=[])

    per_action: List[Dict[str, Any]] = []
    total = 0.0
    high_count = 0
    for op in ops:
        kind = str(op.get("kind") or "")
        score = _KIND_RISK_SCORE.get(kind, 0.5)
        total += score
        per_action.append({"target_file": op.get("target_file"), "kind": kind, "risk_score": score})
        if score >= 0.7:
            high_count += 1

    avg = total / len(ops)
    level = "high" if avg >= 0.7 or high_count >= 2 else "medium" if avg >= 0.4 else "low"
    factors: List[str] = []
    if high_count:
        factors.append(f"{high_count} high-risk operation(s)")
    if avg >= 0.6:
        factors.append("aggregate risk above threshold")
    recommendations: List[str] = []
    if level == "high":
        recommendations.append("Run simulate_patch before apply. Consider hybrid approval.")
    return RiskReport(
        total_risk=round(avg, 4),
        level=level,
        per_action=per_action,
        factors=factors,
        recommendations=recommendations,
    )
