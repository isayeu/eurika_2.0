"""Smell-to-knowledge topic mapping (ROADMAP 2.9.3, R1 layer discipline).

Domain constant shared by doctor, planner, chat. Lives in knowledge layer
to avoid L3/L6 upward imports (planner -> cli).
"""

from __future__ import annotations

SMELL_TO_KNOWLEDGE_TOPICS: dict[str, list[str]] = {
    "god_module": ["architecture_refactor", "module_structure"],
    "bottleneck": ["architecture_refactor"],
    "hub": ["architecture_refactor", "module_structure"],
    "cyclic_dependency": ["cyclic_imports"],
    # Learning from GitHub (ROADMAP 3.0.5): OSSPatternProvider serves long_function/deep_nesting from pattern_library
    "long_function": ["long_function", "pep_8"],
    "deep_nesting": ["deep_nesting", "pep_8"],
}
