"""Extracted from parent module to reduce complexity."""
from dataclasses import dataclass, field
from typing import Any, List
import time

@dataclass
class InputEvent:
    type: str
    payload: dict
    source: str = 'external'
    timestamp: float = field(default_factory=time.time)

@dataclass
class Context:
    event: InputEvent
    memory_snapshot: List[Any]
    system_state: dict

@dataclass
class DecisionProposal:
    action: str
    arguments: dict
    confidence: float
    rationale: str

@dataclass
class Result:
    success: bool
    output: dict
    side_effects: List[str]