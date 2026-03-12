"""
WeightStore — persistence for heuristic estimated_delta (ROADMAP §5.7 этап 7).

Медленно (learning_rate=0.02), bounded [MIN_DELTA, MAX_DELTA], с откатом:
ручной сброс — удалить .eurika/weights.json для возврата к дефолтам.
Веса per (smell_type, action_kind).

RV6: weights_version, metrics_schema_hash для миграций между релизами.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

# RV6: version for file format migrations
WEIGHTS_VERSION = 1


def _metrics_schema_hash() -> str:
    """Hash of default keys — changes when we add/remove (smell, kind) pairs."""
    keys = sorted(_DEFAULT_DELTAS.keys())
    raw = str(keys)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def metrics_schema_hash() -> str:
    """RV6: Public access for migrations. Same as internal hash."""
    return _metrics_schema_hash()


# Defaults from energy_ranking (canonical source)
_DEFAULT_DELTAS: Dict[tuple[str, str], float] = {
    ("god_module", "split_module"): 0.15,
    ("god_module", "refactor_module"): 0.10,
    ("bottleneck", "introduce_facade"): 0.12,
    ("hub", "split_module"): 0.14,
    ("hub", "refactor_module"): 0.10,
    ("cyclic_dependency", "refactor_dependencies"): 0.18,
    ("cyclic_dependency", "remove_cyclic_import"): 0.20,
    ("long_function", "extract_nested_function"): 0.08,
    ("long_function", "extract_block_to_helper"): 0.07,
    ("long_function", "refactor_code_smell"): 0.05,
    ("deep_nesting", "extract_block_to_helper"): 0.09,
    ("deep_nesting", "refactor_code_smell"): 0.05,
}

DEFAULT_DELTA = 0.05  # fallback for unknown (smell, kind)
MIN_DELTA = 0.02
MAX_DELTA = 0.25


def _weights_path(project_root: Path) -> Path:
    from eurika.storage.paths import ensure_storage_dir, storage_path

    root = Path(project_root).resolve()
    ensure_storage_dir(root)
    return storage_path(root, "weights")


def _parse_weights_dict(data: Dict[str, float]) -> Dict[tuple[str, str], float]:
    """Parse 'smell|kind' keys to (smell, kind) tuples."""
    out: Dict[tuple[str, str], float] = {}
    for k, v in (data or {}).items():
        if "|" in k and isinstance(v, (int, float)):
            parts = k.split("|", 1)
            if len(parts) == 2:
                out[(parts[0], parts[1])] = float(v)
    return out


def load_weights(project_root: Path) -> Dict[tuple[str, str], float]:
    """
    Load persisted weights; merge with defaults. Missing keys use default.
    RV6: Supports legacy (plain) and versioned format. Schema migration when hash differs.
    """
    path = _weights_path(project_root)
    if not path.exists():
        return dict(_DEFAULT_DELTAS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return dict(_DEFAULT_DELTAS)

        # New format: {version, schema_hash, weights}
        if "weights" in raw and "version" in raw:
            weights_data = raw.get("weights")
            stored = _parse_weights_dict(weights_data if isinstance(weights_data, dict) else {})
            current_hash = _metrics_schema_hash()
            stored_hash = raw.get("schema_hash", "")
            out = dict(_DEFAULT_DELTAS)
            if stored_hash == current_hash:
                for k, v in stored.items():
                    out[k] = v
            else:
                # Schema changed: keep stored for keys still in defaults, drop obsolete
                for k, v in stored.items():
                    if k in _DEFAULT_DELTAS:
                        out[k] = v
            return out

        # Legacy format: plain {"smell|kind": value}
        out = dict(_DEFAULT_DELTAS)
        for k, v in raw.items():
            if "|" in k and isinstance(v, (int, float)):
                parts = k.split("|", 1)
                if len(parts) == 2:
                    out[(parts[0], parts[1])] = float(v)
        return out
    except Exception:
        return dict(_DEFAULT_DELTAS)


def save_weights(project_root: Path, weights: Dict[tuple[str, str], float]) -> None:
    """Persist weights. RV6: versioned format with schema_hash."""
    path = _weights_path(project_root)
    serializable: Dict[str, float] = {f"{s}|{k}": v for (s, k), v in weights.items()}
    payload = {
        "version": WEIGHTS_VERSION,
        "schema_hash": _metrics_schema_hash(),
        "weights": serializable,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def freeze_weights(project_root: Path) -> Dict[tuple[str, str], float]:
    """
    Return immutable snapshot of weights for the planner cycle (ROADMAP §5.11 RV8).

    Use at cycle start; planner/energy_ranking use this snapshot so learning cannot
    change weights mid-cycle. adapt_weights_from_experience runs only after cycle.
    """
    return dict(load_weights(Path(project_root)))


def get_estimated_delta(
    project_root: Optional[Path],
    smell_type: str,
    action_kind: str,
) -> float:
    """Return estimated delta for (smell, kind). Uses stored or default."""
    if project_root is None:
        return _DEFAULT_DELTAS.get((smell_type or "", action_kind or ""), DEFAULT_DELTA)
    weights = load_weights(Path(project_root))
    return weights.get((smell_type or "", action_kind or ""), DEFAULT_DELTA)


def _adapt_weights_from_delta_energy(
    project_root: Path,
    *,
    learning_rate: float,
    min_delta: float,
    max_delta: float,
) -> bool:
    """
    R9/P6: W -= lr * delta_energy. delta_energy = after - before; negative = improvement.
    Обрабатываем только последнее событие с delta_energy (избегаем двойного применения).
    """
    from eurika.storage.experience_store import get_learn_events_with_delta_energy

    events_data = get_learn_events_with_delta_energy(project_root, limit=10)
    if not events_data:
        return False
    # Только последнее событие — иначе при каждом вызове adapt переобрабатывались бы одни и те же
    ops, delta_energy = events_data[-1]

    weights = load_weights(project_root)
    changed = False
    for op in ops:
        smell = str(op.get("smell_type") or "unknown")
        kind = str(op.get("kind") or "unknown")
        if not kind:
            continue
        tup = (smell, kind)
        current = weights.get(tup, _DEFAULT_DELTAS.get(tup, DEFAULT_DELTA))
        # W -= lr * delta: negative delta (improvement) -> W increases
        new_val = current - learning_rate * delta_energy
        new_val = max(min_delta, min(max_delta, new_val))
        if abs(new_val - current) > 0.001:
            weights[tup] = round(new_val, 4)
            changed = True

    if changed:
        save_weights(project_root, weights)
    return changed


def adapt_weights_from_experience(
    project_root: Path,
    *,
    learning_rate: float = 0.02,
    min_delta: float = MIN_DELTA,
    max_delta: float = MAX_DELTA,
    use_delta_energy: Optional[bool] = None,
) -> bool:
    """
    Медленно обновить веса (ROADMAP §5.7 этап 7, R9/P6).

    use_delta_energy: если True или EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY=1 —
        W -= lr * delta_energy из learn events (R9). Иначе success_rate heuristic.
    Bounded by [min_delta, max_delta]. Возвращает True если были изменения.
    """
    import os

    # Default: delta_energy mode (Energy-based loop, ROADMAP §5.9). Set EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY=0 for success_rate heuristic.
    if use_delta_energy is None:
        use_delta_energy = os.environ.get("EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY", "1").strip().lower() in (
            "1",
            "true",
            "yes",
        )

    if use_delta_energy:
        return _adapt_weights_from_delta_energy(
            project_root, learning_rate=learning_rate, min_delta=min_delta, max_delta=max_delta
        )

    from eurika.storage import get_statistics

    stats = get_statistics(project_root)
    if not stats:
        return False

    weights = load_weights(project_root)
    changed = False
    for key_str, rec in stats.items():
        if "|" not in key_str:
            continue
        parts = key_str.split("|", 1)
        if len(parts) != 2:
            continue
        smell, kind = parts[0], parts[1]
        total = int(rec.get("total", 0) or 0)
        success = int(rec.get("success", 0) or 0)
        if total < 2:
            continue
        rate = success / total
        tup = (smell, kind)
        current = weights.get(tup, _DEFAULT_DELTAS.get(tup, DEFAULT_DELTA))
        if rate > 0.55:
            delta_adj = learning_rate * (rate - 0.5)
            new_val = min(max_delta, current + delta_adj)
        elif rate < 0.45:
            delta_adj = learning_rate * (0.5 - rate)
            new_val = max(min_delta, current - delta_adj)
        else:
            continue
        if abs(new_val - current) > 0.001:
            weights[tup] = round(new_val, 4)
            changed = True

    if changed:
        save_weights(project_root, weights)
    return changed
