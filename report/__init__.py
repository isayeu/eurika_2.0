"""Report formatting: text, colors, markdown."""

from report.architecture_report import render_full_architecture_report
from report.report_snapshot import format_report_snapshot
from report.ux import (
    ascii_bar,
    format_observation,
    format_observation_md,
    health_summary_enhanced,
)

__all__ = [
    "ascii_bar",
    "format_observation",
    "render_full_architecture_report",
    "format_observation_md",
    "format_report_snapshot",
    "health_summary_enhanced",
]
