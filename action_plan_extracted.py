"""Extracted from parent module to reduce complexity."""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

@dataclass
class Action:
    """
    Single planned action over the codebase.

    The semantics are intentionally generic and high-level. Concrete
    executors may choose how to interpret them (e.g. generate patches,
    run tools, etc.) but this module itself stays execution-agnostic.
    """
    type: str
    target: str
    description: str
    risk: float
    expected_benefit: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'Action':
        return Action(type=str(d.get('type', '')), target=str(d.get('target', '')), description=str(d.get('description', '')), risk=float(d.get('risk', 0)), expected_benefit=float(d.get('expected_benefit', 0)))

@dataclass
class ActionPlan:
    """
    Container for a set of planned actions.

    - actions: list of individual actions
    - priority: optional explicit ordering (indices into actions)
    - total_risk / expected_gain: coarse aggregates for quick inspection
    """
    actions: List[Action]
    priority: List[int]
    total_risk: float
    expected_gain: float

    def to_dict(self) -> Dict[str, Any]:
        return {'actions': [a.to_dict() for a in self.actions], 'priority': list(self.priority), 'total_risk': self.total_risk, 'expected_gain': self.expected_gain}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> 'ActionPlan':
        actions = [Action.from_dict(a) for a in d.get('actions', [])]
        return ActionPlan(actions=actions, priority=list(d.get('priority', [])), total_risk=float(d.get('total_risk', 0)), expected_gain=float(d.get('expected_gain', 0)))
