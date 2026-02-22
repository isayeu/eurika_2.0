"""Architectural checks (ROADMAP 3.1-arch.3)."""

from .dependency_firewall import collect_dependency_violations
from .file_size import check_file_size_limits

__all__ = ["check_file_size_limits", "collect_dependency_violations"]
