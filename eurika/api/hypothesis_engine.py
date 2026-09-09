"""Hypothesis Engine v0 (VISION § Master Stage 3 Reasoner).

Deterministic hypotheses from on-disk facts only — explicit evidence + expected.
Hypothesis ≠ fact ≠ experiment. Does not apply patches or invent success.

Persists to ``.eurika/hypotheses.json``.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eurika.utils.json_io import load_json_safe

HYPOTHESES_NAME = "hypotheses.json"
HYPOTHESES_VERSION = 1
MAX_HYPOTHESES = 40
VERIFY_LOW_RATE = 0.5
MAX_REJECT_PATTERN_ROWS = 5
RANKING_VERSION = 1

# Display / priority weights for multi-hypothesis ranking v0.
_STATUS_RANK_W = {
    "open": 1.0,
    "insufficient": 0.55,
    "supported": 0.35,
    "refuted": 0.1,
}
_KIND_RANK_W = {
    "reject_pattern": 1.25,
    "verify_events": 1.1,
    "idle_gap": 0.95,
    "apply_loop": 0.75,
    "hitl_volume": 0.45,
}


def hypotheses_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / HYPOTHESES_NAME


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _stable_id(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"hyp_{digest}"


def _evidence(source: str, key: str, value: Any, note: str = "") -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "source": str(source)[:80],
        "key": str(key)[:80],
        "value": value,
    }
    if note:
        row["note"] = str(note)[:200]
    return row


def _expected(
    description: str,
    metric: str,
    op: str,
    value: Any,
) -> Dict[str, Any]:
    return {
        "description": str(description)[:240],
        "metric": str(metric)[:80],
        "op": str(op)[:16],
        "value": value,
    }


def _hypothesis(
    *,
    kind: str,
    claim: str,
    evidence: List[Dict[str, Any]],
    expected: Dict[str, Any],
    confidence: float,
    status: str = "open",
    tags: Optional[List[str]] = None,
    conclusion: str = "pending",
    proposal_hash: str = "",
    experiment_id: str = "",
    claim_key: str = "",
) -> Dict[str, Any]:
    metric = str((expected or {}).get("metric") or "")
    hid = _stable_id(kind, metric, claim_key or claim[:80])
    return {
        "id": hid,
        "ts": _now_iso(),
        "ts_ms": _now_ms(),
        "status": status,
        "kind": kind,
        "claim": claim[:400],
        "evidence": evidence,
        "expected": expected,
        "actual": None,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "tags": list(tags or []),
        "conclusion": conclusion[:200],
        "proposal_hash": proposal_hash[:64],
        "experiment_id": experiment_id[:64],
        "claim_key": str(claim_key or "")[:120],
    }


def _compare(actual: Any, op: str, expected: Any) -> Optional[bool]:
    """Return True/False if comparable, None if insufficient."""
    if actual is None:
        return None
    try:
        if op in {">=", "ge"}:
            return float(actual) >= float(expected)
        if op in {">", "gt"}:
            return float(actual) > float(expected)
        if op in {"<=", "le"}:
            return float(actual) <= float(expected)
        if op in {"<", "lt"}:
            return float(actual) < float(expected)
        if op in {"==", "eq"}:
            return actual == expected
        if op in {"!=", "ne"}:
            return actual != expected
        if op == "incr":
            # expected is baseline; actual must be > baseline
            return float(actual) > float(expected)
        if op == "recorded":
            return bool(actual)
    except (TypeError, ValueError):
        return None
    return None


def _read_hitl(root: Path) -> Dict[str, Any]:
    try:
        from eurika.api.experiment_memory import hitl_accept_rate

        return hitl_accept_rate(root)
    except Exception:
        return {
            "n": 0,
            "approve": 0,
            "reject": 0,
            "apply_ok": 0,
            "apply_fail": 0,
            "insufficient_data": True,
        }


def _read_idle(root: Path) -> Tuple[Dict[str, int], int, List[str]]:
    try:
        from eurika.orchestration.idle_self_dev import (
            DETERMINISTIC_DRILLS,
            SATURATED_MIN_SUCCESS,
            load_stamp,
            _drill_ok_counts,
        )

        stamp = load_stamp(root)
        counts = _drill_ok_counts(stamp=stamp)
        return counts, int(SATURATED_MIN_SUCCESS), list(DETERMINISTIC_DRILLS)
    except Exception:
        return {}, 5, []


def _read_verify(root: Path) -> Dict[str, Any]:
    try:
        from eurika.storage.event_engine import event_engine

        store = event_engine(root)
        events = store.recent_events(limit=80, types=("patch", "verify", "learn"))
    except Exception:
        return {"ok": 0, "n": 0, "rate": None, "insufficient_data": True}
    ok = 0
    n = 0
    for ev in events:
        result = getattr(ev, "result", None)
        if result is None:
            continue
        n += 1
        if result is True or result == "ok" or result == 1:
            ok += 1
        elif isinstance(result, dict) and result.get("ok") is True:
            ok += 1
    insufficient = n < 3
    rate = (ok / n) if n else None
    return {
        "ok": ok,
        "n": n,
        "rate": rate,
        "insufficient_data": insufficient,
    }


def _reject_kind_counts(root: Path) -> Dict[str, int]:
    try:
        from eurika.api.experiment_memory import load_hitl_journal

        journal = load_hitl_journal(root)
    except Exception:
        return {}
    counts: Dict[str, int] = {}
    for row in journal.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("decision") or "").lower() != "reject":
            continue
        kind = str(row.get("kind") or "").strip() or "?"
        counts[kind] = int(counts.get(kind) or 0) + 1
    return counts


def _experiment_hashes(root: Path) -> Dict[str, str]:
    """proposal_hash → experiment id."""
    try:
        from eurika.api.experiment_memory import load_experiments

        recs = load_experiments(root)
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        ph = str(r.get("proposal_hash") or "").strip()
        eid = str(r.get("id") or "").strip()
        if ph and eid:
            out[ph] = eid
    return out


def generate_hypotheses(project_root: str | Path) -> List[Dict[str, Any]]:
    """Build hypotheses from facts. Empty evidence ⇒ no row."""
    root = Path(project_root).resolve()
    out: List[Dict[str, Any]] = []
    hitl = _read_hitl(root)
    approve = int(hitl.get("approve") or 0)
    reject = int(hitl.get("reject") or 0)
    n = int(hitl.get("n") or (approve + reject))
    apply_ok = int(hitl.get("apply_ok") or 0)
    apply_fail = int(hitl.get("apply_fail") or 0)
    insufficient = bool(hitl.get("insufficient_data"))

    # 1) HITL volume meta-hypothesis
    if n < 3:
        out.append(
            _hypothesis(
                kind="hitl_volume",
                claim=(
                    "Recording ≥3 HITL approve/reject decisions will make "
                    "accept_rate measurable (insufficient_data clears)."
                ),
                evidence=[
                    _evidence("hitl_journal", "aggregates.approve", approve),
                    _evidence("hitl_journal", "aggregates.reject", reject),
                    _evidence("hitl_journal", "n", n, note="need ≥3"),
                ],
                expected=_expected(
                    "HITL decision count reaches 3",
                    "hitl.n",
                    ">=",
                    3,
                ),
                confidence=0.4 if n else 0.2,
                status="insufficient",
                tags=["meta", "hitl"],
                conclusion="need more HITL decisions",
                claim_key="hitl_n_ge_3",
            )
        )

    # 2) apply loop — measure/learn not closed (or already closed → keep as supported)
    if approve >= 1:
        closed = apply_ok >= 1
        out.append(
            _hypothesis(
                kind="apply_loop",
                claim=(
                    "A successful `eurika fix . --apply-approved` after Approve "
                    "will raise aggregates.apply_ok to ≥1 and close the "
                    "measure/learn loop."
                    if not closed
                    else (
                        "Apply-approved verify succeeded at least once "
                        "(measure/learn loop has apply_ok≥1)."
                    )
                ),
                evidence=[
                    _evidence("hitl_journal", "aggregates.approve", approve),
                    _evidence("hitl_journal", "aggregates.apply_ok", apply_ok),
                    _evidence("hitl_journal", "aggregates.apply_fail", apply_fail),
                ],
                expected=_expected(
                    "At least one apply-approved verify ok",
                    "hitl.apply_ok",
                    ">=",
                    1,
                ),
                confidence=0.55 if approve else 0.3,
                status="supported" if closed else "open",
                tags=["c14", "apply"],
                conclusion=(
                    "expected metric satisfied by facts"
                    if closed
                    else "pending"
                ),
                claim_key="apply_ok_ge_1",
            )
        )

    # 3) Idle drill gaps
    counts, sat_min, drills = _read_idle(root)
    if counts:
        gaps = [
            (d, int(counts.get(d) or 0))
            for d in drills
            if int(counts.get(d) or 0) < sat_min
        ]
        # Prefer in-progress drills over never-attempted (count 0).
        partial = [g for g in gaps if g[1] > 0]
        pool = partial or gaps
        pool.sort(key=lambda x: x[1])
        if pool:
            drill, cur = pool[0]
            out.append(
                _hypothesis(
                    kind="idle_gap",
                    claim=(
                        f"One more successful idle/prove-cycle drill `{drill}` "
                        f"will raise drill_ok[{drill}] above {cur} "
                        f"(saturation at {sat_min})."
                    ),
                    evidence=[
                        _evidence(
                            "idle_self_dev",
                            f"drill_ok.{drill}",
                            cur,
                            note=f"sat_min={sat_min}",
                        ),
                        _evidence("idle_self_dev", "drill_ok", dict(counts)),
                    ],
                    expected=_expected(
                        f"drill_ok[{drill}] increases",
                        f"idle.drill_ok.{drill}",
                        "incr",
                        cur,
                    ),
                    confidence=0.5,
                    tags=["idle", "c14"],
                    claim_key=f"idle_incr_{drill}",
                )
            )

    # 4) Reject pattern caution
    rej = _reject_kind_counts(root)
    for kind, cnt in sorted(rej.items(), key=lambda x: -x[1]):
        if cnt < 2:
            continue
        out.append(
            _hypothesis(
                kind="reject_pattern",
                claim=(
                    f"Proposals of kind `{kind}` are frequently rejected "
                    f"({cnt}×); the next `{kind}` needs a different target "
                    f"or higher quality before Approve."
                ),
                evidence=[
                    _evidence("hitl_journal", f"decisions.reject.{kind}", cnt),
                ],
                expected=_expected(
                    f"Next HITL decision for kind={kind} is recorded",
                    f"hitl.decisions.{kind}.n",
                    ">",
                    cnt,
                ),
                confidence=min(0.7, 0.35 + 0.1 * cnt),
                tags=["caution", "hitl"],
                claim_key=f"reject_{kind}",
            )
        )
        out[-1]["action_kind"] = kind
        if sum(1 for h in out if h.get("kind") == "reject_pattern") >= MAX_REJECT_PATTERN_ROWS:
            break

    # 5) Verify events low rate
    verify = _read_verify(root)
    if not verify.get("insufficient_data") and verify.get("rate") is not None:
        rate = float(verify["rate"])
        if rate < VERIFY_LOW_RATE:
            out.append(
                _hypothesis(
                    kind="verify_events",
                    claim=(
                        "Recent patch/verify/learn ok-rate is low; the next "
                        "apply-approved should aim for verify success "
                        "(apply_ok increment) without inventing current quality."
                    ),
                    evidence=[
                        _evidence(
                            "events",
                            "verify.ok_n",
                            f"{verify.get('ok')}/{verify.get('n')}",
                        ),
                        _evidence("events", "verify.rate", round(rate, 3)),
                    ],
                    expected=_expected(
                        "Next apply-approved contributes apply_ok",
                        "hitl.apply_ok",
                        ">",
                        apply_ok,
                    ),
                    confidence=0.45,
                    tags=["verify"],
                    claim_key="verify_low_rate",
                )
            )

    # Link experiment ids when proposal_hash already present (no duplicate claims)
    exp_map = _experiment_hashes(root)
    for row in out:
        ph = str(row.get("proposal_hash") or "")
        if ph and ph in exp_map:
            row["experiment_id"] = exp_map[ph]

    # Drop rows that would duplicate an open experiment with same expected metric
    # only when we explicitly set proposal_hash (v0 generators rarely do).
    return out


def _metric_snapshot(root: Path) -> Dict[str, Any]:
    hitl = _read_hitl(root)
    counts, _, _ = _read_idle(root)
    verify = _read_verify(root)
    rej = _reject_kind_counts(root)
    snap: Dict[str, Any] = {
        "hitl.n": int(hitl.get("n") or 0),
        "hitl.apply_ok": int(hitl.get("apply_ok") or 0),
        "hitl.approve": int(hitl.get("approve") or 0),
        "hitl.reject": int(hitl.get("reject") or 0),
        "verify.rate": verify.get("rate"),
        "verify.n": verify.get("n"),
    }
    for d, v in counts.items():
        snap[f"idle.drill_ok.{d}"] = int(v)
    for kind, cnt in rej.items():
        snap[f"hitl.decisions.{kind}.n"] = int(cnt)
    return snap


def evaluate_hypotheses(
    project_root: str | Path,
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Re-read facts; set actual + status. Does not invent success."""
    root = Path(project_root).resolve()
    snap = _metric_snapshot(root)
    out: List[Dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        row = dict(rec)
        expected = row.get("expected") if isinstance(row.get("expected"), dict) else {}
        metric = str(expected.get("metric") or "")
        op = str(expected.get("op") or "")
        want = expected.get("value")
        actual_val = snap.get(metric) if metric else None
        # Special: reject_pattern uses decisions count for that kind
        if metric.startswith("hitl.decisions.") and metric.endswith(".n"):
            actual_val = snap.get(metric)

        cmp = _compare(actual_val, op, want)
        row["actual"] = {
            "metric": metric,
            "value": actual_val,
            "note": f"op={op} expected={want}",
        }
        prior = str(row.get("status") or "open")
        if prior == "insufficient" and cmp is not True:
            # stay insufficient until evidence threshold met
            if cmp is False:
                row["status"] = "refuted"
                row["conclusion"] = "expected not met yet"
            elif metric == "hitl.n" and actual_val is not None and int(actual_val) >= 3:
                row["status"] = "supported"
                row["conclusion"] = "HITL volume sufficient for accept_rate"
            else:
                row["status"] = "insufficient"
                row["conclusion"] = row.get("conclusion") or "insufficient evidence"
        elif cmp is True:
            row["status"] = "supported"
            row["conclusion"] = "expected metric satisfied by facts"
        elif cmp is False:
            # still open unless we have a hard refutation signal
            if prior in {"supported", "refuted"}:
                row["status"] = prior
            else:
                row["status"] = "open"
                row["conclusion"] = "expected not yet observed"
        else:
            if prior == "insufficient":
                row["status"] = "insufficient"
            else:
                row["status"] = "open"
                row["conclusion"] = "metric unavailable"
        out.append(row)
    return out


def load_hypotheses(project_root: str | Path) -> List[Dict[str, Any]]:
    data = load_json_safe(hypotheses_path(project_root))
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [r for r in data["records"] if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _merge_records(
    existing: List[Dict[str, Any]],
    generated: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {str(r.get("id") or ""): dict(r) for r in existing if r.get("id")}
    for gen in generated:
        gid = str(gen.get("id") or "")
        if not gid:
            continue
        if gid in by_id:
            old = by_id[gid]
            merged = dict(old)
            # refresh claim/evidence/expected from generator; keep prior conclusion if supported
            for key in (
                "claim",
                "evidence",
                "expected",
                "kind",
                "tags",
                "confidence",
                "action_kind",
                "claim_key",
            ):
                if key in gen:
                    merged[key] = gen[key]
            if str(old.get("status")) not in {"supported", "refuted"}:
                merged["status"] = gen.get("status") or old.get("status") or "open"
            if gen.get("experiment_id"):
                merged["experiment_id"] = gen["experiment_id"]
            if gen.get("proposal_hash"):
                merged["proposal_hash"] = gen["proposal_hash"]
            by_id[gid] = merged
        else:
            by_id[gid] = dict(gen)
    # Drop stale open/insufficient that are no longer generated (facts changed)
    gen_ids = {str(g.get("id") or "") for g in generated}
    kept: List[Dict[str, Any]] = []
    for hid, row in by_id.items():
        st = str(row.get("status") or "")
        if hid in gen_ids or st in {"supported", "refuted"}:
            kept.append(row)
    kept.sort(key=lambda r: int(r.get("ts_ms") or 0))
    return kept[-MAX_HYPOTHESES:]


def hypothesis_rank_score(row: Dict[str, Any]) -> float:
    """Priority score for display / soft planning (higher = more urgent)."""
    try:
        conf = float(row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    status = str(row.get("status") or "open")
    kind = str(row.get("kind") or "")
    sw = float(_STATUS_RANK_W.get(status, 0.5))
    kw = float(_KIND_RANK_W.get(kind, 0.5))
    return round(100.0 * conf * sw * kw, 3)


def rank_hypotheses(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stamp ``rank_score`` and return copies sorted highest-first."""
    out: List[Dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        row = dict(r)
        row["rank_score"] = hypothesis_rank_score(row)
        out.append(row)
    out.sort(
        key=lambda r: (
            -float(r.get("rank_score") or 0.0),
            -int(r.get("ts_ms") or 0),
        )
    )
    return out


def hypothesis_ranking_signals(project_root: str | Path) -> Dict[str, Any]:
    """Soft bug-hunt signals from ranked open hypotheses (not deny / not apply).

    - ``caution_weights``: action_kind → negative score delta (reject_pattern)
    - ``prefer_safe_delta``: boost SAFE kinds when verify_events is open
    - ``ranked``: top claim summaries for UI
    """
    root = Path(project_root).resolve()
    ranked = rank_hypotheses(generate_hypotheses(root))
    caution_weights: Dict[str, int] = {}
    prefer_safe_delta = 0
    for row in ranked:
        status = str(row.get("status") or "open")
        if status not in {"open", "insufficient"}:
            continue
        kind = str(row.get("kind") or "")
        try:
            conf = float(row.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        if kind == "reject_pattern":
            ak = str(row.get("action_kind") or "").strip()
            if not ak:
                ck = str(row.get("claim_key") or "")
                if ck.startswith("reject_"):
                    ak = ck[len("reject_") :]
            if not ak:
                continue
            penalty = -int(round(25 + 30 * conf))
            prev = caution_weights.get(ak)
            caution_weights[ak] = penalty if prev is None else min(prev, penalty)
        elif kind == "verify_events":
            prefer_safe_delta = max(prefer_safe_delta, int(round(10 + 10 * conf)))
        elif kind == "apply_loop" and status == "open":
            prefer_safe_delta = max(prefer_safe_delta, 5)
    return {
        "version": RANKING_VERSION,
        "caution_weights": caution_weights,
        "prefer_safe_delta": prefer_safe_delta,
        "ranked": [
            {
                "kind": r.get("kind"),
                "status": r.get("status"),
                "rank_score": r.get("rank_score"),
                "claim_key": r.get("claim_key"),
                "action_kind": r.get("action_kind"),
                "confidence": r.get("confidence"),
            }
            for r in ranked[:8]
        ],
    }


def refresh_hypotheses(project_root: str | Path) -> Dict[str, Any]:
    """Generate ∪ merge ∪ evaluate ∪ rank → write ``.eurika/hypotheses.json``."""
    root = Path(project_root).resolve()
    existing = load_hypotheses(root)
    generated = generate_hypotheses(root)
    merged = _merge_records(existing, generated)
    evaluated = evaluate_hypotheses(root, merged)
    ranked = rank_hypotheses(evaluated)
    payload = {
        "version": HYPOTHESES_VERSION,
        "ranking_version": RANKING_VERSION,
        "updated_at": _now_iso(),
        "records": ranked[:MAX_HYPOTHESES],
        "note": "hypothesis ≠ fact; evidence/expected required; ranked by rank_score",
    }
    _atomic_write_json(hypotheses_path(root), payload)
    return payload


def format_hypotheses_text(
    payload: Optional[Dict[str, Any]] = None,
    *,
    project_root: str | Path | None = None,
    mode: str = "full",
) -> str:
    if payload is None and project_root is not None:
        payload = refresh_hypotheses(project_root)
    if not isinstance(payload, dict):
        return "Hypothesis Engine: нет данных. Запусти `eurika hypotheses .`."
    records = rank_hypotheses(
        [r for r in (payload.get("records") or []) if isinstance(r, dict)]
    )
    lines = [
        "Hypothesis Engine v0",
        f"updated_at={payload.get('updated_at') or '-'} records={len(records)}",
        f"ranking_version={payload.get('ranking_version') or RANKING_VERSION} "
        "(higher rank_score = more urgent; hypothesis ≠ fact)",
        "",
    ]
    if not records:
        lines.append("Нет гипотез с достаточным evidence (или факты пусты).")
        return "\n".join(lines)

    by_status: Dict[str, int] = {}
    for r in records:
        st = str(r.get("status") or "open")
        by_status[st] = by_status.get(st, 0) + 1
    lines.append(
        "status: "
        + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    )
    lines.append("")

    show = records if mode == "full" else records[:5]
    for r in show:
        st = r.get("status") or "open"
        kind = r.get("kind") or "-"
        claim = r.get("claim") or ""
        rs = r.get("rank_score")
        lines.append(f"[{st}] {kind} (rank={rs}): {claim}")
        exp = r.get("expected") if isinstance(r.get("expected"), dict) else {}
        if exp:
            lines.append(
                f"  expected: {exp.get('metric')} {exp.get('op')} {exp.get('value')}"
                f" — {exp.get('description') or ''}"
            )
        if mode == "full":
            for ev in (r.get("evidence") or [])[:4]:
                if not isinstance(ev, dict):
                    continue
                lines.append(
                    f"  evidence: {ev.get('source')}.{ev.get('key')}={ev.get('value')}"
                )
            act = r.get("actual") if isinstance(r.get("actual"), dict) else None
            if act:
                lines.append(f"  actual: {act.get('metric')}={act.get('value')}")
            if r.get("conclusion"):
                lines.append(f"  conclusion: {r.get('conclusion')}")
            if r.get("experiment_id"):
                lines.append(f"  experiment_id: {r.get('experiment_id')}")
            if r.get("action_kind"):
                lines.append(f"  action_kind: {r.get('action_kind')}")
        lines.append("")
    lines.append("Chat: «гипотезы». CLI: `eurika hypotheses .`")
    return "\n".join(lines).rstrip() + "\n"


def format_hypotheses_brief(project_root: str | Path, *, limit: int = 3) -> List[str]:
    try:
        payload = refresh_hypotheses(project_root)
    except Exception:
        return []
    records = rank_hypotheses(
        [r for r in (payload.get("records") or []) if isinstance(r, dict)]
    )
    if not records:
        return []
    open_n = sum(1 for r in records if str(r.get("status")) in {"open", "insufficient"})
    lines = [
        "",
        "Hypotheses:",
        f"- open/insufficient={open_n}, total={len(records)} (ranked)",
    ]
    for r in records[:limit]:
        lines.append(
            f"  · [{r.get('status')}] {r.get('kind')} "
            f"(rank={r.get('rank_score')}): {(r.get('claim') or '')[:72]}"
        )
    return lines


def caution_action_kinds(project_root: str | Path) -> set[str]:
    """Action kinds flagged by ``reject_pattern`` (compat wrapper)."""
    signals = hypothesis_ranking_signals(project_root)
    weights = signals.get("caution_weights")
    if isinstance(weights, dict):
        return {str(k) for k in weights.keys() if k}
    return set()
