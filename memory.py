"""
Memory module v0.1

Dumb, append-only memory.
No intelligence. No summarization. No mutation.

Record types: event, decision, result (bundled in MemoryRecord).
TTL/pruning: max_records and optional max_age_seconds.
"""

import time
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class MemoryRecord:
    """Single step: event + decision + result."""
    event: Any
    decision: Optional[Any]
    result: Any

    @property
    def event_type(self) -> str:
        return self.event.type

    @property
    def event_payload(self) -> Any:
        return self.event.payload


class SimpleMemory:
    def __init__(
        self,
        max_records: int = 1000,
        max_age_seconds: Optional[float] = None,
    ):
        self._records: List[MemoryRecord] = []
        self.max_records = max_records
        self.max_age_seconds = max_age_seconds

    def snapshot(self) -> List[MemoryRecord]:
        """
        Returns a shallow copy of memory records.
        Core and reasoner must treat this as read-only.
        """
        self._prune()
        return list(self._records)

    def record(
        self,
        event: Any,
        decision: Optional[Any],
        result: Any,
    ):
        """Append a new record. Prunes after append if limits exceeded."""
        self._records.append(
            MemoryRecord(
                event=event,
                decision=decision,
                result=result,
            )
        )
        self._prune()

    def _prune(self):
        """Remove oldest records when over max_records or max_age."""
        if self.max_age_seconds is not None:
            now = time.time()
            self._records = [
                r for r in self._records
                if (now - r.event.timestamp) <= self.max_age_seconds
            ]
        while len(self._records) > self.max_records:
            self._records.pop(0)

    def __len__(self):
        return len(self._records)


"""
End of memory.py v0.1
"""
