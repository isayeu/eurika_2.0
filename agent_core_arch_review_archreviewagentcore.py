"""Extracted from parent module to reduce complexity."""

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from agent_core import DecisionProposal, InputEvent, Result
from action_plan import ActionPlan
from executor_sandbox import ExecutorSandbox
from eurika.smells.detector import ArchSmell, detect_architecture_smells
from eurika.smells.summary import build_summary
from eurika.storage import ProjectMemory
from architecture_planner import ArchitecturePlan, build_plan, build_action_plan, build_patch_plan
from eurika.analysis.self_map import build_graph_from_self_map, load_self_map

class ArchReviewAgentCore:
    """
    Minimal, domain-specific AgentCore-like layer for architecture review.

    Scope:
    - No Reasoner/Selector/Executor.
    - No code modifications, no sandbox actions.
    - Purely read-only aggregation of existing v0.1 engine artifacts.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def handle(self, event: InputEvent) -> Result:
        """
        Handle a single architecture-domain event.

        Supported:
        - event.type == "arch_review"
        - event.type == "arch_evolution_query"
        - event.type == "arch_action_dry_run"
        - event.type == "arch_action_simulate"

        event.payload may contain:
        - "path": optional project root override
        - "window": optional history window (int)
        """
        root = Path(event.payload.get('path', self.project_root))
        window = int(event.payload.get('window', 5))
        try:
            if event.type == 'arch_review':
                return self._handle_arch_review(root, window)
            if event.type == 'arch_evolution_query':
                return self._handle_arch_evolution_query(root, window)
            if event.type == 'arch_action_dry_run':
                return self._handle_arch_action_dry_run(root, window)
            if event.type == 'arch_action_simulate':
                return self._handle_arch_action_simulate(root, window)
        except Exception as exc:
            return Result(success=False, output={'error': 'arch_event_failed', 'message': str(exc)}, side_effects=['ArchReviewAgentCore: exception during arch event'])
        return Result(success=False, output={'error': 'unsupported_event_type', 'expected': ['arch_review', 'arch_evolution_query', 'arch_action_dry_run', 'arch_action_simulate'], 'actual': event.type}, side_effects=['ArchReviewAgentCore: unsupported event type'])

    def _handle_arch_review(self, root: Path, window: int) -> Result:
        summary, smells, graph = self._load_structure(root)
        history_info = self._load_history(root, window=window)
        observations_info = self._load_observations(root)
        explain = self._build_explain_risk(summary, smells)
        evolution = self._build_summarize_evolution(trends=history_info['trends'], regressions=history_info['regressions'], evolution_report=history_info['evolution_report'])
        priority = self._build_prioritize_modules(summary, smells, history_info)
        plan = self._build_plan(root=root, summary=summary, smells=smells, history_info=history_info, priority_modules=priority.arguments.get('modules', []))
        action_plan = self._build_action_plan(root=root, summary=summary, smells=smells, history_info=history_info, priority_modules=priority.arguments.get('modules', []))
        patch_plan = self._build_patch_plan(root=root, summary=summary, smells=smells, history_info=history_info, priority_modules=priority.arguments.get('modules', []), graph=graph)
        proposals = [explain, evolution, priority, plan, action_plan, patch_plan]
        return Result(success=True, output={'type': 'arch_review', 'project_root': str(root), 'summary': summary, 'history': {'trends': history_info['trends'], 'regressions': history_info['regressions'], 'evolution_report': history_info['evolution_report']}, 'observations': observations_info, 'proposals': [asdict(p) for p in proposals]}, side_effects=['ArchReviewAgentCore: read self_map.json', 'ArchReviewAgentCore: read architecture_history.json', 'ArchReviewAgentCore: read eurika_observations.json'])

    def _handle_arch_evolution_query(self, root: Path, window: int) -> Result:
        """Handle an evolution-focused query based only on architecture history."""
        history_info = self._load_history(root, window=window)
        evolution = self._build_summarize_evolution(trends=history_info['trends'], regressions=history_info['regressions'], evolution_report=history_info['evolution_report'])
        return Result(success=True, output={'type': 'arch_evolution_query', 'project_root': str(root), 'history': {'trends': history_info['trends'], 'regressions': history_info['regressions'], 'evolution_report': history_info['evolution_report']}, 'proposals': [asdict(evolution)]}, side_effects=['ArchReviewAgentCore: read architecture_history.json'])

    def _handle_arch_action_dry_run(self, root: Path, window: int) -> Result:
        """
        Build an ActionPlan from diagnostics and return it without executing.

        This keeps the layer strictly read-only; execution is delegated to
        external tools or sandboxes.
        """
        summary, smells, _ = self._load_structure(root)
        history_info = self._load_history(root, window=window)
        priority = self._build_prioritize_modules(summary, smells, history_info)
        priority_modules = priority.arguments.get('modules', [])
        action_plan: ActionPlan = build_action_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priority_modules)
        proposal = DecisionProposal(action='suggest_action_plan', arguments={'action_plan': action_plan.to_dict()}, confidence=0.7, rationale='Action plan derived from architecture plan inputs: prioritized modules, architectural smells and history trends. Execution is not performed by this AgentCore and is expected to be handled by an external sandbox.')
        return Result(success=True, output={'type': 'arch_action_dry_run', 'project_root': str(root), 'summary': summary, 'history': {'trends': history_info['trends'], 'regressions': history_info['regressions'], 'evolution_report': history_info['evolution_report']}, 'proposals': [asdict(proposal)]}, side_effects=['ArchReviewAgentCore: read self_map.json', 'ArchReviewAgentCore: read architecture_history.json'])

    def _handle_arch_action_simulate(self, root: Path, window: int) -> Result:
        """
        Build an ActionPlan from diagnostics and simulate its execution
        via ExecutorSandbox.dry_run, without modifying any code.
        """
        summary, smells, _ = self._load_structure(root)
        history_info = self._load_history(root, window=window)
        priority = self._build_prioritize_modules(summary, smells, history_info)
        priority_modules = priority.arguments.get('modules', [])
        action_plan: ActionPlan = build_action_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priority_modules)
        sandbox = ExecutorSandbox(project_root=root)
        simulation = sandbox.dry_run(action_plan)
        proposal = DecisionProposal(action='simulate_actions', arguments={'action_plan': action_plan.to_dict(), 'simulation': simulation}, confidence=0.7, rationale='Simulation performed in a read-only sandbox based on the derived ActionPlan; no code changes were applied to the target project.')
        return Result(success=True, output={'type': 'arch_action_simulate', 'project_root': str(root), 'summary': summary, 'history': {'trends': history_info['trends'], 'regressions': history_info['regressions'], 'evolution_report': history_info['evolution_report']}, 'proposals': [asdict(proposal)]}, side_effects=['ArchReviewAgentCore: read self_map.json', 'ArchReviewAgentCore: read architecture_history.json', 'ArchReviewAgentCore: sandbox dry-run executed'])

    def _load_structure(self, root: Path) -> tuple[Dict[str, Any], List[ArchSmell], 'ProjectGraph']:
        """Load self_map and derive graph, smells + summary."""
        self_map_path = root / 'self_map.json'
        if not self_map_path.exists():
            raise FileNotFoundError(f'self_map.json not found at {self_map_path}')
        load_self_map(self_map_path)
        graph = build_graph_from_self_map(self_map_path)
        smells = detect_architecture_smells(graph)
        summary = build_summary(graph, smells)
        return (summary, smells, graph)

    def _load_history(self, root: Path, window: int) -> Dict[str, Any]:
        """Load architecture history and compute trends/regressions/report."""
        memory = ProjectMemory(root)
        history = memory.history
        evolution_report = history.evolution_report(window=window)
        trends = history.trend(window=window)
        regressions = history.detect_regressions(window=window)
        return {'evolution_report': evolution_report, 'trends': trends, 'regressions': regressions}

    def _load_observations(self, root: Path) -> Dict[str, Any]:
        """Load last observation snapshot if eurika_observations.json exists."""
        memory = ProjectMemory(root)
        observations_info: Dict[str, Any] = {'available': False}
        records = memory.observations.snapshot()
        if records:
            last = records[-1]
            observations_info = {'available': True, 'count': len(records), 'last': last.to_dict()}
        return observations_info

    def _build_explain_risk(self, summary: Dict[str, Any], smells: List[ArchSmell]) -> DecisionProposal:
        """Explain main architectural risks from summary + smells."""
        central = summary.get('central_modules', [])
        risks = summary.get('risks', [])
        arguments: Dict[str, Any] = {'central_modules': central, 'top_risks': risks[:5], 'maturity': summary.get('maturity')}
        rationale_lines: List[str] = []
        if central:
            names = ', '.join((c['name'] for c in central))
            rationale_lines.append(f'Central modules with highest fan-in/out: {names}.')
        if risks:
            rationale_lines.append(f"Top structural risks detected: {', '.join(risks[:3])}.")
        rationale_lines.append('Risks are derived from import graph structure and architectural smell scores; no runtime behaviour is taken into account.')
        return DecisionProposal(action='explain_risk', arguments=arguments, confidence=0.8, rationale=' '.join(rationale_lines))

    def _build_summarize_evolution(self, trends: Dict[str, str], regressions: List[str], evolution_report: str) -> DecisionProposal:
        """Summarize architecture evolution trajectory."""
        arguments: Dict[str, Any] = {'trends': trends, 'regressions': regressions, 'evolution_report': evolution_report}
        rationale_lines: List[str] = ['Evolution trends are computed from the append-only architecture history over the last N snapshots (modules + dependencies + smells + centralization).']
        if regressions:
            rationale_lines.append('Potential regressions were detected and highlighted for manual review.')
        else:
            rationale_lines.append('No strong regressions detected in the observed window; focus can stay on guided evolution.')
        return DecisionProposal(action='summarize_evolution', arguments=arguments, confidence=0.85, rationale=' '.join(rationale_lines))

    def _score_modules_by_smells(self, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Compute per-module scores and reasons based on smells + summary + history."""
        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}
        for s in smells:
            for node in s.nodes:
                scores[node] = scores.get(node, 0.0) + float(s.severity)
                reasons.setdefault(node, []).append(f'{s.type} (severity={s.severity:.2f})')
        for risk in summary.get('risks', []):
            if '@ ' in risk:
                _, rest = risk.split('@ ', 1)
                target = rest.split(' ', 1)[0]
                scores[target] = scores.get(target, 0.0) + 1.0
                reasons.setdefault(target, []).append('mentioned_in_summary_risks')
        trends = history_info.get('trends', {})
        if trends.get('smells') == 'increasing':
            for node in scores:
                scores[node] *= 1.1
                reasons.setdefault(node, []).append('smell_trend_increasing')
        return {name: {'score': score, 'reasons': reasons.get(name, [])} for name, score in scores.items()}

    def _build_priority_list(self, scored: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert scored modules into a sorted priority list."""
        return [{'name': name, 'score': round(info['score'], 3), 'reasons': info['reasons']} for name, info in sorted(scored.items(), key=lambda kv: kv[1]['score'], reverse=True)]

    def _build_prioritize_modules(self, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any]) -> DecisionProposal:
        """
        Build a simple, explainable prioritization over modules.

        Heuristic v0.3 draft:
        - assign base score from smells severity per module;
        - boost modules mentioned in summary.risks;
        - optionally nudge score based on trends (if smells are increasing).
        """
        scored = self._score_modules_by_smells(summary, smells, history_info)
        modules = self._build_priority_list(scored)
        arguments: Dict[str, Any] = {'modules': modules}
        rationale_lines = ['Module priorities are derived from accumulated architectural smell severities, explicit risks in the architecture summary and, optionally, smell trends from history.']
        return DecisionProposal(action='prioritize_modules', arguments=arguments, confidence=0.8, rationale=' '.join(rationale_lines))

    def _build_plan(self, root: Path, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priority_modules: List[Dict[str, Any]]) -> DecisionProposal:
        """
        Build a minimal architecture plan from diagnostics.

        v0.3 draft:
        - delegates planning to architecture_planner.build_plan;
        - wraps result as a suggest_refactor_plan DecisionProposal.
        """
        plan: ArchitecturePlan = build_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priority_modules)
        arguments: Dict[str, Any] = {'plan': plan.to_dict()}
        return DecisionProposal(action='suggest_refactor_plan', arguments=arguments, confidence=0.7, rationale='High-level refactor plan derived from prioritized modules, architectural smells and history trends. v0.3 draft uses a minimal plan representation; future versions will populate concrete steps.')

    def _build_action_plan(self, root: Path, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priority_modules: List[Dict[str, Any]]) -> DecisionProposal:
        """
        Build an ActionPlan proposal from diagnostics.

        Reuses architecture_planner.build_action_plan. If architecture_learning.json
        exists, past success rates are used to nudge expected_benefit and
        learned_signals are attached to the proposal.
        """
        learning_stats: Dict[str, Any] | None = None
        learned_signals: Dict[str, Any] = {}
        try:
            memory = ProjectMemory(root)
            raw = memory.learning.aggregate_by_smell_action()
            if not raw:
                raw = memory.learning.aggregate_by_action_kind()
            if raw:
                for key, d in raw.items():
                    total = d.get('total', 0)
                    success = d.get('success', 0)
                    learned_signals[key] = dict(d, success_rate=round(success / total, 3) if total else 0.0)
                learning_stats = raw
        except Exception:
            pass
        plan: ActionPlan = build_action_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priority_modules, learning_stats=learning_stats)
        arguments: Dict[str, Any] = {'action_plan': plan.to_dict()}
        if learned_signals:
            arguments['learned_signals'] = learned_signals
        return DecisionProposal(action='suggest_action_plan', arguments=arguments, confidence=0.7, rationale='Action plan derived from prioritized modules, architectural smells and history trends. Execution remains outside this AgentCore and is expected to be handled by an external sandbox.' + (' Past success rates were used to nudge expected_benefit.' if learned_signals else ''))

    def _build_patch_plan(self, root: Path, summary: Dict[str, Any], smells: List[ArchSmell], history_info: Dict[str, Any], priority_modules: List[Dict[str, Any]], graph: Optional['ProjectGraph']=None) -> DecisionProposal:
        """
        Build a high-level PatchPlan proposal from diagnostics.

        PatchPlan is still descriptive: it encodes per-module refactor
        intents and textual diff hints, but does not apply any changes.
        When architecture_learning.json exists, operations are ordered by
        past success rate (smell_type, action_kind) so that historically
        successful pairs appear first.
        """
        learning_stats: Dict[str, Any] | None = None
        self_map: Dict[str, Any] | None = None
        try:
            memory = ProjectMemory(root)
            learning_stats = memory.learning.aggregate_by_smell_action()
            if not learning_stats:
                learning_stats = None
        except Exception:
            pass
        try:
            self_map = load_self_map(root / 'self_map.json')
        except (FileNotFoundError, OSError):
            self_map = None
        plan = build_patch_plan(project_root=str(root), summary=summary, smells=smells, history_info=history_info, priorities=priority_modules, learning_stats=learning_stats, graph=graph, self_map=self_map)
        arguments: Dict[str, Any] = {'patch_plan': plan.to_dict()}
        return DecisionProposal(action='suggest_patch_plan', arguments=arguments, confidence=0.6, rationale='Patch plan derived from prioritized modules and their smells. Intended as a human-reviewable set of patch suggestions before any automated refactoring is attempted.')
