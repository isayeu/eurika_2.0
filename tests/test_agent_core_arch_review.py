import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core import InputEvent
from agent_core_arch_review import ArchReviewAgentCore
from runtime_scan import run_scan


def test_arch_review_agent_core_on_self(tmp_path: Path) -> None:
    """
    Smoke-test for ArchReviewAgentCore on this project itself.

    - runs scan to ensure artifacts exist,
    - calls arch_review,
    - checks that result is successful and contains expected proposals.
    """
    project_root = ROOT
    assert run_scan(project_root) == 0

    agent = ArchReviewAgentCore(project_root=project_root)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(project_root), "window": 3},
        source="test",
    )

    result = agent.handle(event)

    assert result.success is True
    output = result.output
    assert output.get("type") == "arch_review"
    proposals = output.get("proposals", [])
    actions = {p["action"] for p in proposals}
    assert "explain_risk" in actions
    assert "summarize_evolution" in actions
    assert "prioritize_modules" in actions
    assert "suggest_refactor_plan" in actions

    # Check basic properties of prioritize_modules output.
    prioritize = next(p for p in proposals if p["action"] == "prioritize_modules")
    modules = prioritize["arguments"]["modules"]
    assert modules, "prioritize_modules should return at least one module"

    # Scores should be sorted descending.
    scores = [m["score"] for m in modules]
    assert scores == sorted(scores, reverse=True)

    # Top module should have at least one reason explaining its score.
    top = modules[0]
    assert top["reasons"]

    # Check that suggest_refactor_plan returns a plan dict.
    plan = next(p for p in proposals if p["action"] == "suggest_refactor_plan")
    plan_args = plan["arguments"]["plan"]
    assert "project_root" in plan_args
    assert "generated_from" in plan_args
    assert "steps" in plan_args


def test_arch_evolution_query_on_self(tmp_path: Path) -> None:
    """
    Smoke-test for arch_evolution_query scenario:
    - assumes history exists (after scan),
    - checks that summarize_evolution proposal is returned.
    """
    project_root = ROOT
    assert run_scan(project_root) == 0

    agent = ArchReviewAgentCore(project_root=project_root)
    event = InputEvent(
        type="arch_evolution_query",
        payload={"path": str(project_root), "window": 3},
        source="test",
    )

    result = agent.handle(event)

    assert result.success is True
    output = result.output
    assert output.get("type") == "arch_evolution_query"
    proposals = output.get("proposals", [])
    actions = {p["action"] for p in proposals}
    assert "summarize_evolution" in actions

