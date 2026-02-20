"""Runtime policy configuration for native agent modes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

from .models import AgentMode

RiskLevel = Literal["low", "medium", "high"]

_RISK_ORDER: dict[RiskLevel, int] = {"low": 1, "medium": 2, "high": 3}


@dataclass(slots=True)
class PolicyConfig:
    mode: AgentMode
    max_ops: int
    max_files: int
    allow_test_files: bool
    auto_apply_max_risk: RiskLevel

    def allows_risk(self, risk: RiskLevel) -> bool:
        return _RISK_ORDER[risk] <= _RISK_ORDER[self.auto_apply_max_risk]


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def load_policy_config(mode: AgentMode) -> PolicyConfig:
    """Load policy configuration from mode defaults and optional env overrides."""
    defaults = {
        "assist": PolicyConfig(mode="assist", max_ops=200, max_files=100, allow_test_files=False, auto_apply_max_risk="high"),
        "hybrid": PolicyConfig(mode="hybrid", max_ops=80, max_files=40, allow_test_files=False, auto_apply_max_risk="low"),
        "auto": PolicyConfig(mode="auto", max_ops=120, max_files=60, allow_test_files=False, auto_apply_max_risk="medium"),
    }
    cfg = defaults.get(mode, defaults["assist"])
    risk_env = os.environ.get("EURIKA_AGENT_MAX_RISK", cfg.auto_apply_max_risk).strip().lower()
    if risk_env not in {"low", "medium", "high"}:
        risk_env = cfg.auto_apply_max_risk
    return PolicyConfig(
        mode=cfg.mode,
        max_ops=max(1, _env_int("EURIKA_AGENT_MAX_OPS", cfg.max_ops)),
        max_files=max(1, _env_int("EURIKA_AGENT_MAX_FILES", cfg.max_files)),
        allow_test_files=os.environ.get("EURIKA_AGENT_ALLOW_TEST_FILES", "0").strip() in {"1", "true", "yes"},
        auto_apply_max_risk=cast(RiskLevel, risk_env),
    )
