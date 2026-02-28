"""Extracted from parent module to reduce complexity. R2: uses logging."""

from pathlib import Path
from typing import Optional

from cli.orchestration.logging import get_logger
from code_awareness import CodeAwareness
from eurika.core.pipeline import run_full_analysis
from eurika.storage import ProjectMemory
from report.architecture_report import render_full_architecture_report
from report.ux import format_observation, format_observation_md, should_use_color

_LOG = get_logger("scan")


def run_scan(path: Path, *, format: str = "text", color: Optional[bool] = None) -> int:
    """Scan project, log report, update architecture artifacts and memory."""
    use_color = should_use_color(color)
    analyzer = CodeAwareness(path)
    observation = analyzer.analyze_project()
    if format == "markdown":
        report = format_observation_md(observation)
    else:
        report = format_observation(observation, use_color=use_color)
    print(report)
    analyzer.write_self_map(path)
    _LOG.info("self_map.json written to %s", path / "self_map.json")
    snapshot = run_full_analysis(path)
    arch_report = render_full_architecture_report(snapshot, format=format, use_color=use_color)
    print(arch_report)
    memory = ProjectMemory(path)
    memory.record_scan(observation)
    return 0
