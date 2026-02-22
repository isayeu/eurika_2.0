"""
Eurika Runtime Scan v0.1

Core orchestration for `eurika scan`.
CLI (`eurika_cli.py`) is only responsible for argument parsing and exit codes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from code_awareness import CodeAwareness
from eurika.core.pipeline import run_full_analysis
from eurika.storage import ProjectMemory
from report.architecture_report import render_full_architecture_report
from report.ux import (
    format_observation,
    format_observation_md,
    should_use_color,
)


def run_scan(
    path: Path,
    *,
    format: str = "text",
    color: Optional[bool] = None,
) -> int:
    """Scan project, print report, update architecture artifacts and memory."""
    use_color = should_use_color(color)
    analyzer = CodeAwareness(path)
    observation = analyzer.analyze_project()

    if format == "markdown":
        report = format_observation_md(observation)
    else:
        report = format_observation(observation, use_color=use_color)
    print(report)

    analyzer.write_self_map(path)
    print(f"self_map.json written to {path / 'self_map.json'}")

    # Architecture awareness pipeline (graph + smells + summary + history)
    snapshot = run_full_analysis(path)
    arch_report = render_full_architecture_report(
        snapshot,
        format=format,
        use_color=use_color,
    )
    print(arch_report)

    memory = ProjectMemory(path)
    memory.record_scan(observation)

    return 0

# TODO: Refactor runtime_scan.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: code_awareness.py.
# - Consider grouping callers: cli/core_handlers.py, cli/orchestration/deps.py, tests/test_agent_core_arch_review.py.
# - Introduce facade for callers: cli/core_handlers.py, cli/orchestration/deps.py, cli/orchestration/full_cycle.py....
# - Extract database interaction logic into `module_db`.
# - Separate user interface components into `module_ui`.
# - Isolate networking functions into `module_net`.
