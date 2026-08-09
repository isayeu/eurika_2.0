"""R5 C: Extensibility — analyzer plugins for architecture smells."""

from .protocol import AnalyzerPlugin
from .registry import load_plugins, run_plugins
from .aggregate import detect_smells_with_plugins, merge_smells_for_report
from .hooks import (
    HOOK_EVENTS,
    HookContext,
    HookExecution,
    HookRegistry,
    PostStageHook,
    dispatch_project_hooks,
    load_hook_registry,
)

__all__ = [
    "AnalyzerPlugin",
    "load_plugins",
    "run_plugins",
    "detect_smells_with_plugins",
    "merge_smells_for_report",
    "HOOK_EVENTS",
    "HookContext",
    "HookExecution",
    "HookRegistry",
    "PostStageHook",
    "dispatch_project_hooks",
    "load_hook_registry",
]
