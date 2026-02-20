"""Runtime policy configuration for native agent modes (ROADMAP 2.7.3)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from .models import AgentMode

RiskLevel = Literal["low", "medium", "high"]

_RISK_ORDER: dict[RiskLevel, int] = {"low": 1, "medium": 2, "high": 3}

# Default patterns for API-breaking guard: files often re-exporting public API
_DEFAULT_API_PATTERNS: tuple[str, ...] = ("*api*.py", "*__init__.py", "api.py")


@dataclass(slots=True)
class PolicyConfig:
    mode: AgentMode
    max_ops: int
    max_files: int
    allow_test_files: bool
    auto_apply_max_risk: RiskLevel
    deny_patterns: tuple[str, ...] = ()
    api_breaking_guard: bool = False

    def allows_risk(self, risk: RiskLevel) -> bool:
        return _RISK_ORDER[risk] <= _RISK_ORDER[self.auto_apply_max_risk]

    def matches_deny_pattern(self, target_file: str) -> bool:
        """True if target_file matches any deny_pattern (glob)."""
        if not self.deny_patterns or not target_file:
            return False
        from fnmatch import fnmatch
        path = target_file.replace("\\", "/")
        return any(fnmatch(path, p) for p in self.deny_patterns)

    def is_api_surface_file(self, target_file: str) -> bool:
        """True if file is likely an API surface (for api_breaking_guard)."""
        if not target_file:
            return False
        from fnmatch import fnmatch
        path = target_file.replace("\\", "/")
        return any(fnmatch(path, p) for p in _DEFAULT_API_PATTERNS)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def suggest_policy_from_telemetry(telemetry: dict) -> dict[str, str]:
    """Suggest env overrides based on telemetry (ROADMAP 2.7.8). Returns dict of EURIKA_AGENT_* keys."""
    if not telemetry:
        return {}
    out: dict[str, str] = {}
    apply_rate = telemetry.get("apply_rate")
    rollback_rate = telemetry.get("rollback_rate")
    if isinstance(apply_rate, (int, float)) and apply_rate < 0.3:
        out["EURIKA_AGENT_MAX_OPS"] = "40"
    if isinstance(rollback_rate, (int, float)) and rollback_rate > 0.5:
        out["EURIKA_AGENT_MAX_OPS"] = str(min(int(out.get("EURIKA_AGENT_MAX_OPS", "80")), 40))
    return out


def load_policy_config(mode: AgentMode) -> PolicyConfig:
    """Load policy configuration from mode defaults and optional env overrides."""
    defaults = {
        "assist": PolicyConfig(mode="assist", max_ops=200, max_files=100, allow_test_files=False, auto_apply_max_risk="high"),
        "hybrid": PolicyConfig(mode="hybrid", max_ops=80, max_files=40, allow_test_files=False, auto_apply_max_risk="low", api_breaking_guard=True),
        "auto": PolicyConfig(mode="auto", max_ops=120, max_files=60, allow_test_files=False, auto_apply_max_risk="medium", api_breaking_guard=True),
    }
    cfg = defaults.get(mode, defaults["assist"])
    risk_env = os.environ.get("EURIKA_AGENT_MAX_RISK", cfg.auto_apply_max_risk).strip().lower()
    if risk_env not in {"low", "medium", "high"}:
        risk_env = cfg.auto_apply_max_risk
    deny_str = os.environ.get("EURIKA_AGENT_DENY_PATTERNS", "").strip()
    deny_patterns = tuple(p.strip() for p in deny_str.split(",") if p.strip()) or cfg.deny_patterns
    api_guard = os.environ.get("EURIKA_AGENT_API_BREAKING_GUARD", "").strip() or str(int(cfg.api_breaking_guard))
    api_breaking_guard = api_guard in {"1", "true", "yes"}
    return PolicyConfig(
        mode=cfg.mode,
        max_ops=max(1, _env_int("EURIKA_AGENT_MAX_OPS", cfg.max_ops)),
        max_files=max(1, _env_int("EURIKA_AGENT_MAX_FILES", cfg.max_files)),
        allow_test_files=os.environ.get("EURIKA_AGENT_ALLOW_TEST_FILES", "0").strip() in {"1", "true", "yes"},
        auto_apply_max_risk=cast(RiskLevel, risk_env),
        deny_patterns=deny_patterns,
        api_breaking_guard=api_breaking_guard,
    )
