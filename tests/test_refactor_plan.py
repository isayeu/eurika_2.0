"""Tests for eurika.reasoning.refactor_plan."""
from eurika.reasoning.refactor_plan import suggest_refactor_plan

def test_suggest_plan_from_risks() -> None:
    """Plan derived from summary risks when no recommendations given."""
    summary = {'risks': ['god_module @ project_graph_api.py (severity=11.00)', 'bottleneck @ project_graph_api.py (severity=10.00)'], 'system': {}, 'maturity': 'low'}
    plan = suggest_refactor_plan(summary, recommendations=None)
    assert 'project_graph_api.py' in plan
    assert 'god_module' in plan
    assert 'bottleneck' in plan
    assert plan.strip().startswith('1.')

def test_suggest_plan_from_recommendations() -> None:
    """When recommendations provided, they are used as numbered steps."""
    summary = {'risks': [], 'system': {}}
    recs = ['project_graph_api.py: introduce facade to reduce fan-in.', 'agent_core_arch_review.py: split by domain.']
    plan = suggest_refactor_plan(summary, recommendations=recs)
    assert '1. project_graph_api.py' in plan
    assert '2. agent_core_arch_review.py' in plan

def test_suggest_plan_empty() -> None:
    """Empty summary and no recommendations yields fallback message."""
    summary = {'risks': [], 'system': {}}
    plan = suggest_refactor_plan(summary, recommendations=None)
    assert 'No refactoring steps' in plan