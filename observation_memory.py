"""
Observation Memory v0.1

Stores scan observations. No agent_core dependency.
Append-only. TTL/pruning. Optional file persistence.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ObservationRecord:
    trigger: str
    observation: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"trigger": self.trigger, "observation": self.observation, "timestamp": self.timestamp}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ObservationRecord":
        return ObservationRecord(
            trigger=d.get("trigger", ""),
            observation=d.get("observation", {}),
            timestamp=d.get("timestamp", time.time()),
        )


STORAGE_FILE = "eurika_observations.json"


class ObservationMemory:
    """Stores observations from scan/analyze. Persists to file if storage_path given."""

    def __init__(
        self,
        max_records: int = 100,
        max_age_seconds: Optional[float] = None,
        storage_path: Optional[Path] = None,
    ):
        self._records: List[ObservationRecord] = []
        self.max_records = max_records
        self.max_age_seconds = max_age_seconds
        self.storage_path = storage_path
        if storage_path:
            self._load()

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._records = [ObservationRecord.from_dict(r) for r in data.get("records", [])]
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        if not self.storage_path:
            return
        try:
            data = {"records": [r.to_dict() for r in self._records]}
            self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def record_observation(self, trigger: str, observation: Dict[str, Any]) -> None:
        """Append observation. Prunes if limits exceeded. Saves to file if configured."""
        self._records.append(
            ObservationRecord(trigger=trigger, observation=observation)
        )
        self._prune()
        self._save()

    def snapshot(self) -> List[ObservationRecord]:
        """Return read-only copy of records."""
        self._prune()
        return list(self._records)

    def _prune(self) -> None:
        if self.max_age_seconds is not None:
            now = time.time()
            self._records = [
                r for r in self._records
                if (now - r.timestamp) <= self.max_age_seconds
            ]
        while len(self._records) > self.max_records:
            self._records.pop(0)

    def __len__(self) -> int:
        return len(self._records)
