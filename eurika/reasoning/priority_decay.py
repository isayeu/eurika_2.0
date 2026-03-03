"""
Priority decay — контролируемая деградация приоритетов (Review III decay v1.2).

effective_priority = base_priority * (1 - failure_penalty) * freshness_bonus

- failure_penalty: растёт при провалах
- freshness_bonus: падает со временем с последней попытки
- archive: тяжёлая деградация после N провалов
- Step 3 recovery: success cancels failure (плавное восстановление)
- Step 4 forgetting: старые провалы весят меньше (time-weighted)

Без meta-стратегий, без RL. Минимальная модель эволюции поведения.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

DECAY_FAILURE_PENALTY_RATE = 0.2  # penalty += 0.2 per failure
DECAY_FAILURE_PENALTY_CAP = 0.6  # max penalty
DECAY_FRESHNESS_DAYS_HALFLIFE = 14  # bonus halves every 14 days
DECAY_ARCHIVE_AFTER_FAILURES = 5  # heavy deprioritize after N failures
DECAY_ARCHIVE_FACTOR = 0.1  # multiply score by this when archived


DECAY_SUCCESS_RECOVERY_FACTOR = 1.0  # 1 success cancels 1 failure (Step 3)
DECAY_FAILURE_FORGET_DAYS_HALFLIFE = 30  # old failures weigh less (Step 4)


def _load_success_counts(project_root: Path) -> Dict[Tuple[str, str], int]:
    """(target_file, kind) -> success_count from learn events (Step 3)."""
    from eurika.storage.memory import ProjectMemory

    counts: Dict[Tuple[str, str], int] = {}
    memory = ProjectMemory(project_root)
    for e in memory.events.recent_events(limit=100, types=("learn",)):
        if getattr(e, "result", None) is not True:
            continue
        for op in (e.input or {}).get("operations", []):
            tf = str(op.get("target_file") or "")
            k = str(op.get("kind") or "")
            if tf or k:
                key = (tf, k)
                counts[key] = counts.get(key, 0) + 1
    return counts


def _load_failure_counts_and_last_attempt(
    project_root: Path,
) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], float], Dict[Tuple[str, str], List[float]]]:
    """(target_file, kind) -> failure_count; last_attempt_ts; failure_timestamps (for forgetting)."""
    from eurika.storage.memory import ProjectMemory
    from eurika.storage.paths import storage_path

    counts: Dict[Tuple[str, str], int] = {}
    last_ts: Dict[Tuple[str, str], float] = {}
    failure_timestamps: Dict[Tuple[str, str], List[float]] = {}

    path = storage_path(Path(project_root).resolve(), "failures")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for r in data.get("failures", []):
                tf = str(r.get("target_file") or "")
                k = str(r.get("kind") or "")
                ts = float(r.get("timestamp", 0))
                if tf or k:
                    key = (tf, k)
                    counts[key] = counts.get(key, 0) + 1
                    last_ts[key] = max(last_ts.get(key, 0), ts)
                    failure_timestamps.setdefault(key, []).append(ts)
        except (json.JSONDecodeError, OSError):
            pass

    memory = ProjectMemory(project_root)
    for e in memory.events.recent_events(limit=100, types=("learn",)):
        ts = getattr(e, "timestamp", 0) or 0
        for op in (e.input or {}).get("operations", []):
            tf = str(op.get("target_file") or "")
            k = str(op.get("kind") or "")
            if tf or k:
                key = (tf, k)
                last_ts[key] = max(last_ts.get(key, 0), ts)

    return counts, last_ts, failure_timestamps


def apply_decay(
    scores: Dict[str, float],
    reasons: Dict[str, list],
    node_to_kind: Callable[[str], str],
    project_root: Optional[Path],
) -> None:
    """
    Modify scores in-place: effective_score = base * (1 - failure_penalty) * freshness_bonus.

    Archive: if failure_count >= N, score *= 0.1.
    """
    if not project_root or not Path(project_root).resolve().exists():
        return
    try:
        counts, last_ts, failure_timestamps = _load_failure_counts_and_last_attempt(Path(project_root))
        success_counts = _load_success_counts(Path(project_root))
    except Exception:
        return
    now = time.time()
    for node in list(scores.keys()):
        kind = node_to_kind(node)
        key = (node, kind)
        fail_count = counts.get(key, 0)
        success_count = success_counts.get(key, 0)
        # Step 3: recovery — success cancels failures (плавное восстановление)
        effective_fail = max(
            0,
            fail_count - int(DECAY_SUCCESS_RECOVERY_FACTOR * success_count),
        )
        # Step 4: forgetting — old failures weigh less (time-weighted)
        timestamps = sorted(failure_timestamps.get(key, []))[-20:]
        weighted_fail = sum(
            0.5 ** (max(0, now - ts) / 86400 / DECAY_FAILURE_FORGET_DAYS_HALFLIFE)
            for ts in timestamps
        )
        effective_weighted = max(0.0, weighted_fail - success_count)
        last = last_ts.get(key, 0)
        failure_penalty = min(
            DECAY_FAILURE_PENALTY_CAP,
            DECAY_FAILURE_PENALTY_RATE * effective_weighted,
        )
        if effective_fail >= DECAY_ARCHIVE_AFTER_FAILURES:
            scores[node] *= DECAY_ARCHIVE_FACTOR
            continue
        days_since = (now - last) / 86400 if last else 0
        if last == 0:
            freshness_bonus = 1.0
        else:
            freshness_bonus = max(0.3, 0.5 ** (days_since / DECAY_FRESHNESS_DAYS_HALFLIFE))
        scores[node] *= (1.0 - failure_penalty) * freshness_bonus


__all__ = ["apply_decay"]
