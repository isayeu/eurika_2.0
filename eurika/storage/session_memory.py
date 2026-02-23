"""Session memory for hybrid approval decisions (ROADMAP 2.7.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CAMPAIGN_VERIFY_FAIL_MAX = 20
_CAMPAIGN_REJECTED_MAX = 100


def operation_key(op: dict[str, Any]) -> str:
    """Stable key for storing approval/rejection decisions across runs."""
    target = str(op.get("target_file") or "")
    kind = str(op.get("kind") or "")
    location = str((op.get("params") or {}).get("location") or "")
    return f"{target}|{kind}|{location}"


@dataclass(slots=True)
class SessionMemory:
    """Persistent store for per-session operation decisions."""

    project_root: Path
    path: Path = Path(".")

    def __post_init__(self) -> None:
        root = Path(self.project_root).resolve()
        self.project_root = root
        self.path = root / ".eurika" / "session_memory.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"sessions": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"sessions": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def rejected_keys(self, session_id: str) -> set[str]:
        data = self._load()
        session = (data.get("sessions") or {}).get(session_id) or {}
        rejected = session.get("rejected_keys") or []
        return {str(x) for x in rejected}

    def record(
        self,
        session_id: str,
        *,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> None:
        data = self._load()
        sessions = data.setdefault("sessions", {})
        session = sessions.setdefault(session_id, {"approved_keys": [], "rejected_keys": []})
        approved_keys = set(str(x) for x in session.get("approved_keys", []))
        rejected_keys = set(str(x) for x in session.get("rejected_keys", []))
        approved_keys |= {operation_key(op) for op in approved}
        rejected_keys |= {operation_key(op) for op in rejected}
        session["approved_keys"] = sorted(approved_keys)
        session["rejected_keys"] = sorted(rejected_keys)
        campaign = data.setdefault("campaign", {"rejected_keys": [], "verify_fail_keys": []})
        campaign_rej = set(campaign.get("rejected_keys") or [])
        campaign_rej |= rejected_keys
        campaign["rejected_keys"] = sorted(campaign_rej)[-_CAMPAIGN_REJECTED_MAX:]
        self._save(data)

    def record_verify_failure(self, operations: list[dict[str, Any]]) -> None:
        """Record op keys from a run that failed verify (ROADMAP 2.7.5)."""
        data = self._load()
        campaign = data.setdefault("campaign", {"rejected_keys": [], "verify_fail_keys": []})
        fail_keys = list(campaign.get("verify_fail_keys") or [])
        for op in operations:
            fail_keys.append(operation_key(op))
        campaign["verify_fail_keys"] = fail_keys[-(_CAMPAIGN_VERIFY_FAIL_MAX):]
        self._save(data)

    def campaign_keys_to_skip(self) -> set[str]:
        """Keys to skip based on campaign memory: rejected in any session or 2+ verify failures."""
        data = self._load()
        campaign = data.get("campaign") or {}
        rej = set(campaign.get("rejected_keys") or [])
        fail_keys = campaign.get("verify_fail_keys") or []
        from collections import Counter
        counts = Counter(fail_keys)
        repeated_fail = {k for k, v in counts.items() if v >= 2}
        return rej | repeated_fail
