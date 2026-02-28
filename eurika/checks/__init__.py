"""Architectural checks (ROADMAP 3.1-arch.3, R5)."""

from .dependency_firewall import (
    collect_dependency_violations,
    collect_layer_violations,
)
from .file_size import check_file_size_limits
from .self_guard import SelfGuardResult, collect_self_guard, format_self_guard_block, self_guard_pass

__all__ = [
    "check_file_size_limits",
    "collect_dependency_violations",
    "collect_layer_violations",
    "collect_self_guard",
    "format_self_guard_block",
    "self_guard_pass",
    "SelfGuardResult",
]
