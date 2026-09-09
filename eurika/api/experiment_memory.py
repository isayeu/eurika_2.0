"""HITL journal + Experiment Memory v0 (VISION § Master Stage 4–5).

Durable facts only:
- human approve/reject on team Approvals (``.eurika/pending_plan.json``)
- apply-approved verify outcomes
- open experiment records for parked proposals

Files under ``.eurika/``:
- ``hitl_journal.json`` — bounded decision/apply lists + aggregates
- ``experiments.json`` — bounded experiment records (hypothesis ≠ fact)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from eurika.utils.json_io import load_json_safe

JOURNAL_NAME = "hitl_journal.json"
EXPERIMENTS_NAME = "experiments.json"
JOURNAL_VERSION = 1
MAX_DECISIONS = 80
MAX_APPLIES = 40
MAX_EXPERIMENTS = 60


def journal_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / JOURNAL_NAME


def experiments_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / EXPERIMENTS_NAME


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


def _proposal_hash(op: Dict[str, Any]) -> str:
    try:
        from eurika.storage.experience_store import proposal_hash_from_op

        return str(proposal_hash_from_op(op) or "")
    except Exception:
        kind = str(op.get("kind") or "")
        target = str(op.get("target_file") or "")
        return f"{kind}|{target}"[:16]


def _norm_decision(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in {"approve", "approved", "yes"}:
        return "approve"
    if s in {"reject", "rejected", "no"}:
        return "reject"
    if s in {"pending", ""}:
        return "pending"
    return s


def _decision_from_op(op: Dict[str, Any]) -> str:
    td = _norm_decision(op.get("team_decision"))
    if td in {"approve", "reject"}:
        return td
    st = _norm_decision(op.get("approval_state"))
    if st == "approved":
        return "approve"
    if st == "rejected":
        return "reject"
    return "pending"


def _empty_journal() -> Dict[str, Any]:
    return {
        "version": JOURNAL_VERSION,
        "updated_at": _now_iso(),
        "decisions": [],
        "applies": [],
        "aggregates": {
            "approve": 0,
            "reject": 0,
            "apply_ok": 0,
            "apply_fail": 0,
        },
    }


def load_hitl_journal(project_root: str | Path) -> Dict[str, Any]:
    data = load_json_safe(journal_path(project_root))
    if not isinstance(data, dict):
        return _empty_journal()
    out = _empty_journal()
    out.update({k: data.get(k, out.get(k)) for k in out})
    if not isinstance(out.get("decisions"), list):
        out["decisions"] = []
    if not isinstance(out.get("applies"), list):
        out["applies"] = []
    ag = out.get("aggregates")
    if not isinstance(ag, dict):
        out["aggregates"] = _empty_journal()["aggregates"]
    # Preserve Stage 5 metrics block when present on disk.
    si = data.get("self_improvement")
    if isinstance(si, dict):
        out["self_improvement"] = si
    return out


def _save_journal(project_root: str | Path, journal: Dict[str, Any]) -> None:
    journal["updated_at"] = _now_iso()
    journal["version"] = JOURNAL_VERSION
    journal["decisions"] = list(journal.get("decisions") or [])[-MAX_DECISIONS:]
    journal["applies"] = list(journal.get("applies") or [])[-MAX_APPLIES:]
    # Keep self_improvement if caller already attached it; else restore from disk.
    if not isinstance(journal.get("self_improvement"), dict):
        prior = load_json_safe(journal_path(project_root))
        if isinstance(prior, dict) and isinstance(prior.get("self_improvement"), dict):
            journal["self_improvement"] = prior["self_improvement"]
    _atomic_write_json(journal_path(project_root), journal)


def load_experiments(project_root: str | Path) -> List[Dict[str, Any]]:
    data = load_json_safe(experiments_path(project_root))
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [r for r in data["records"] if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _save_experiments(
    project_root: str | Path,
    records: List[Dict[str, Any]],
    *,
    self_improvement: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "version": JOURNAL_VERSION,
        "updated_at": _now_iso(),
        "records": records[-MAX_EXPERIMENTS:],
    }
    if isinstance(self_improvement, dict) and self_improvement:
        payload["self_improvement"] = self_improvement
    else:
        # Keep prior metrics block if present
        prior = load_json_safe(experiments_path(project_root))
        if isinstance(prior, dict) and isinstance(prior.get("self_improvement"), dict):
            payload["self_improvement"] = prior["self_improvement"]
    _atomic_write_json(experiments_path(project_root), payload)


def hitl_accept_rate(project_root: str | Path) -> Dict[str, Any]:
    """Measured human approve/(approve+reject). Does not invent success."""
    journal = load_hitl_journal(project_root)
    ag = journal.get("aggregates") if isinstance(journal.get("aggregates"), dict) else {}
    approve = int(ag.get("approve") or 0)
    reject = int(ag.get("reject") or 0)
    # Prefer aggregates; fall back to counting recent decisions if aggregates empty.
    if approve + reject == 0:
        for row in journal.get("decisions") or []:
            if not isinstance(row, dict):
                continue
            d = _norm_decision(row.get("decision"))
            if d == "approve":
                approve += 1
            elif d == "reject":
                reject += 1
    n = approve + reject
    insufficient = n < 3
    rate = round(approve / n, 3) if n else 0.0
    apply_ok = int(ag.get("apply_ok") or 0)
    apply_fail = int(ag.get("apply_fail") or 0)
    apply_n = apply_ok + apply_fail
    apply_ok_rate = round(apply_ok / apply_n, 3) if apply_n else None
    return {
        "level": 0.0 if insufficient else rate,
        "accept_rate": rate if n else None,
        "approve": approve,
        "reject": reject,
        "n": n,
        "apply_ok": apply_ok,
        "apply_fail": apply_fail,
        "apply_n": apply_n,
        "apply_ok_rate": apply_ok_rate,
        "insufficient_data": insufficient,
        "evidence": (
            f"HITL decisions approve={approve} reject={reject} "
            f"(rate={rate if n else 'n/a'}); "
            f"apply_ok={apply_ok}/{apply_n if apply_n else 0}"
            + (f" (apply_ok_rate={apply_ok_rate})" if apply_ok_rate is not None else "")
        ),
        "note": "accept_rate is human decision rate, not code quality",
    }


def _median_int(values: List[int]) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return int(ordered[mid])
    return int((ordered[mid - 1] + ordered[mid]) // 2)


def compute_self_improvement_metrics(project_root: str | Path) -> Dict[str, Any]:
    """Stage 5 metrics beyond accept-rate — facts only, no self-praise."""
    root = Path(project_root).resolve()
    hitl = hitl_accept_rate(root)
    journal = load_hitl_journal(root)
    apply_ok = int(hitl.get("apply_ok") or 0)
    apply_fail = int(hitl.get("apply_fail") or 0)
    apply_n = apply_ok + apply_fail
    apply_ok_rate = hitl.get("apply_ok_rate")

    # verify success by action kind (learning records)
    by_kind: Dict[str, Dict[str, Any]] = {}
    verify_ok_total = 0
    verify_n_total = 0
    try:
        from eurika.api.learning_api import get_learning_insights

        insights = get_learning_insights(root, top_n=8)
        raw = insights.get("by_action_kind") if isinstance(insights, dict) else None
        if isinstance(raw, dict):
            for kind, stats in raw.items():
                if not isinstance(stats, dict):
                    continue
                total = int(stats.get("total") or 0)
                vs = int(stats.get("verify_success") or 0)
                vf = int(stats.get("verify_fail") or 0)
                applied = vs + vf
                if total <= 0 and applied <= 0:
                    continue
                denom = applied if applied > 0 else total
                rate = round(vs / denom, 3) if denom else None
                by_kind[str(kind)[:80]] = {
                    "total": total,
                    "verify_success": vs,
                    "verify_fail": vf,
                    "rate": rate,
                }
                verify_ok_total += vs
                verify_n_total += denom
    except Exception:
        by_kind = {}
    verify_insuff = verify_n_total < 3
    verify_overall = (
        round(verify_ok_total / verify_n_total, 3) if verify_n_total else None
    )

    # time-to-decide: experiment propose ts → decision ts (same proposal_hash)
    exp_by_hash: Dict[str, Dict[str, Any]] = {}
    for rec in load_experiments(root):
        if not isinstance(rec, dict):
            continue
        ph = str(rec.get("proposal_hash") or "").strip()
        if ph:
            exp_by_hash[ph] = rec
    lags_ms: List[int] = []
    for row in journal.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        ph = str(row.get("proposal_hash") or "").strip()
        if not ph or ph not in exp_by_hash:
            continue
        proposed = int(exp_by_hash[ph].get("ts_ms") or 0)
        decided = int(row.get("ts_ms") or 0)
        if proposed > 0 and decided >= proposed:
            lags_ms.append(decided - proposed)
    lag_insuff = len(lags_ms) < 2
    median_lag = _median_int(lags_ms)

    # supported hypotheses share
    hyp_n = 0
    hyp_supported = 0
    hyp_open = 0
    try:
        from eurika.api.hypothesis_engine import load_hypotheses

        hyps = load_hypotheses(root)
        hyp_n = len(hyps)
        for h in hyps:
            st = str(h.get("status") or "")
            if st == "supported":
                hyp_supported += 1
            elif st in {"open", "insufficient"}:
                hyp_open += 1
    except Exception:
        hyps = []
    hyp_insuff = hyp_n < 1
    hyp_share = round(hyp_supported / hyp_n, 3) if hyp_n else None

    return {
        "updated_at": _now_iso(),
        "apply_ok_rate": {
            "level": 0.0 if apply_n < 1 else float(apply_ok_rate or 0.0),
            "rate": apply_ok_rate,
            "apply_ok": apply_ok,
            "apply_fail": apply_fail,
            "n": apply_n,
            "insufficient_data": apply_n < 1,
            "evidence": f"apply_ok={apply_ok} apply_fail={apply_fail} rate={apply_ok_rate}",
            "note": "verify outcome of apply-approved, not human approve rate",
        },
        "verify_by_kind": {
            "level": 0.0 if verify_insuff else float(verify_overall or 0.0),
            "overall_rate": verify_overall,
            "ok": verify_ok_total,
            "n": verify_n_total,
            "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -int(kv[1].get("total") or 0))[:12]),
            "insufficient_data": verify_insuff,
            "evidence": (
                f"learning verify_success={verify_ok_total}/{verify_n_total}"
                + (f" overall={verify_overall}" if verify_overall is not None else "")
            ),
            "note": "from learn records by action kind; not a claim of intelligence",
        },
        "time_to_decide": {
            "level": (
                0.0
                if lag_insuff
                else round(min(1.0, 1.0 / (1.0 + (median_lag or 0) / 3_600_000)), 3)
            ),
            "median_ms": median_lag,
            "samples": len(lags_ms),
            "insufficient_data": lag_insuff,
            "evidence": (
                f"proposal→decision samples={len(lags_ms)}"
                + (f" median_ms={median_lag}" if median_lag is not None else "")
            ),
            "note": "lower median lag is faster HITL response; not code quality",
        },
        "hypotheses_supported": {
            "level": 0.0 if hyp_insuff else float(hyp_share or 0.0),
            "share": hyp_share,
            "supported": hyp_supported,
            "open": hyp_open,
            "n": hyp_n,
            "insufficient_data": hyp_insuff,
            "evidence": f"supported={hyp_supported}/{hyp_n} open={hyp_open}",
            "note": "share of evaluated hypotheses with status=supported",
        },
        "hitl_accept_rate": {
            "accept_rate": hitl.get("accept_rate"),
            "n": hitl.get("n"),
            "insufficient_data": hitl.get("insufficient_data"),
        },
    }


def _persist_self_improvement_into_stores(project_root: str | Path) -> Dict[str, Any]:
    """Refresh metrics block on hitl_journal + experiments.json (side effect)."""
    root = Path(project_root).resolve()
    metrics = compute_self_improvement_metrics(root)
    journal = load_hitl_journal(root)
    journal["self_improvement"] = metrics
    _save_journal(root, journal)
    records = load_experiments(root)
    _save_experiments(root, records, self_improvement=metrics)
    return metrics


def _patch_meta(patch_plan: Optional[Dict[str, Any]]) -> Dict[str, str]:
    plan = patch_plan if isinstance(patch_plan, dict) else {}
    return {
        "source": str(plan.get("source") or plan.get("summary") or "").strip()[:120],
        "drill": str(plan.get("drill") or "").strip()[:80],
    }


def record_proposals(
    project_root: str | Path,
    operations: List[Dict[str, Any]],
    *,
    patch_plan: Optional[Dict[str, Any]] = None,
) -> int:
    """Open experiment records when ops are parked in Approvals."""
    root = Path(project_root).resolve()
    meta = _patch_meta(patch_plan)
    records = load_experiments(root)
    by_hash = {
        str(r.get("proposal_hash") or ""): i
        for i, r in enumerate(records)
        if str(r.get("proposal_hash") or "")
    }
    created = 0
    for op in operations:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("kind") or "").strip()
        target = str(op.get("target_file") or "").strip()
        if not kind and not target:
            continue
        ph = _proposal_hash(op)
        if ph and ph in by_hash:
            continue
        drill = meta["drill"] or str(op.get("drill") or "").strip()
        source = meta["source"] or str(op.get("source") or "pending_plan").strip()
        goal = (
            f"C.14 HITL: {drill}" if drill else f"Improve via `{kind}` on `{target or '?'}`"
        )
        hyp = str(op.get("description") or "").strip()
        if not hyp:
            hyp = f"`{kind}` on `{target}` is a worthwhile improvement"
        evidence = [
            {
                "source": "pending_plan",
                "key": "kind",
                "value": kind,
                "note": "parked proposal",
            },
            {
                "source": "pending_plan",
                "key": "target_file",
                "value": target,
            },
        ]
        if drill:
            evidence.append(
                {"source": "pending_plan", "key": "drill", "value": drill}
            )
        if source:
            evidence.append(
                {"source": "pending_plan", "key": "source", "value": source[:120]}
            )
        expected = {
            "description": (
                "sandbox/smoke ok (if used); human approve; "
                "apply-approved verify ok"
            ),
            "metric": "hitl.apply_ok",
            "op": "incr_or_ok",
            "value": True,
        }
        rec = {
            "id": f"exp_{ph or _now_ms()}",
            "ts": _now_iso(),
            "ts_ms": _now_ms(),
            "status": "proposed",
            "goal": goal[:200],
            "hypothesis": hyp[:400],
            "baseline": "main tree unchanged; proposal in pending_plan",
            "change": f"{kind} → {target}"[:200],
            "expected_result": (
                "sandbox/smoke ok (if used); human approve; "
                "apply-approved verify ok"
            ),
            "expected": expected,
            "evidence": evidence,
            "actual_result": None,
            "metrics": {},
            "rollback_strategy": "fix-cycle rollback / restore backup; reject leaves main untouched",
            "conclusion": "pending",
            "kind": kind,
            "target": target,
            "proposal_hash": ph,
            "source": source[:120],
            "drill": drill,
        }
        records.append(rec)
        if ph:
            by_hash[ph] = len(records) - 1
        created += 1
    if created:
        _save_experiments(root, records)
    return created


def _update_experiment_for_hash(
    records: List[Dict[str, Any]],
    proposal_hash: str,
    *,
    status: Optional[str] = None,
    actual_result: Optional[str] = None,
    conclusion: Optional[str] = None,
    metrics_update: Optional[Dict[str, Any]] = None,
) -> bool:
    changed = False
    for rec in reversed(records):
        if str(rec.get("proposal_hash") or "") != proposal_hash:
            continue
        if status:
            rec["status"] = status
        if actual_result is not None:
            rec["actual_result"] = actual_result
        if conclusion:
            rec["conclusion"] = conclusion
        if metrics_update:
            m = rec.get("metrics") if isinstance(rec.get("metrics"), dict) else {}
            m.update(metrics_update)
            rec["metrics"] = m
        rec["updated_at"] = _now_iso()
        changed = True
        break
    return changed


def record_decision_transitions(
    project_root: str | Path,
    before_ops: List[Dict[str, Any]],
    after_ops: List[Dict[str, Any]],
    *,
    source: str = "approvals",
) -> int:
    """Append journal rows for pending→approve/reject transitions."""
    root = Path(project_root).resolve()
    n = min(len(before_ops), len(after_ops))
    if n == 0:
        return 0
    journal = load_hitl_journal(root)
    records = load_experiments(root)
    recorded = 0
    ag = journal.setdefault("aggregates", _empty_journal()["aggregates"])
    for i in range(n):
        old = before_ops[i] if isinstance(before_ops[i], dict) else {}
        new = after_ops[i] if isinstance(after_ops[i], dict) else {}
        prev = _decision_from_op(old)
        cur = _decision_from_op(new)
        if cur not in {"approve", "reject"} or cur == prev:
            continue
        ph = _proposal_hash(new) or _proposal_hash(old)
        kind = str(new.get("kind") or old.get("kind") or "")
        target = str(new.get("target_file") or old.get("target_file") or "")
        row = {
            "ts": _now_iso(),
            "ts_ms": _now_ms(),
            "decision": cur,
            "kind": kind,
            "target": target,
            "proposal_hash": ph,
            "source": str(source or "approvals")[:64],
            "approved_by": new.get("approved_by"),
        }
        journal.setdefault("decisions", []).append(row)
        ag[cur] = int(ag.get(cur) or 0) + 1
        _update_experiment_for_hash(
            records,
            ph,
            status="decided",
            actual_result=f"human {cur}",
            conclusion="accept" if cur == "approve" else "reject",
            metrics_update={"decision": cur, "decision_source": source},
        )
        recorded += 1
    if recorded:
        _save_journal(root, journal)
        _save_experiments(root, records)
        try:
            _persist_self_improvement_into_stores(root)
        except Exception:
            pass
        try:
            from eurika.api.self_model import persist_self_model

            persist_self_model(root)
        except Exception:
            pass
    return recorded


def record_apply_outcome(
    project_root: str | Path,
    operations: List[Dict[str, Any]],
    *,
    verify_ok: bool,
    exit_code: int = 0,
    source: str = "apply-approved",
) -> int:
    """Record apply-approved result and close related experiments."""
    root = Path(project_root).resolve()
    ops = [op for op in operations if isinstance(op, dict)]
    journal = load_hitl_journal(root)
    records = load_experiments(root)
    ag = journal.setdefault("aggregates", _empty_journal()["aggregates"])
    key = "apply_ok" if verify_ok else "apply_fail"
    ag[key] = int(ag.get(key) or 0) + 1
    kinds = [str(op.get("kind") or "") for op in ops]
    targets = [str(op.get("target_file") or "") for op in ops]
    apply_row = {
        "ts": _now_iso(),
        "ts_ms": _now_ms(),
        "ok": bool(verify_ok),
        "exit_code": int(exit_code),
        "n_ops": len(ops),
        "kinds": kinds[:12],
        "targets": targets[:12],
        "source": str(source or "apply-approved")[:64],
    }
    journal.setdefault("applies", []).append(apply_row)
    for op in ops:
        ph = _proposal_hash(op)
        actual = (
            "apply-approved verify ok"
            if verify_ok
            else f"apply-approved failed (exit={exit_code})"
        )
        conclusion = "accept" if verify_ok else "inconclusive"
        _update_experiment_for_hash(
            records,
            ph,
            status="applied" if verify_ok else "closed",
            actual_result=actual,
            conclusion=conclusion,
            metrics_update={
                "verify_ok": bool(verify_ok),
                "exit_code": int(exit_code),
            },
        )
    _save_journal(root, journal)
    _save_experiments(root, records)
    try:
        _persist_self_improvement_into_stores(root)
    except Exception:
        pass
    try:
        from eurika.api.self_model import persist_self_model

        persist_self_model(root)
    except Exception:
        pass
    return len(ops)


def sync_decisions_from_pending(
    project_root: str | Path,
    payload: Optional[Dict[str, Any]] = None,
    *,
    source: str = "pending_plan",
) -> int:
    """Backfill journal for approve/reject already set on pending ops (manual edit path)."""
    root = Path(project_root).resolve()
    data = payload if isinstance(payload, dict) else None
    if data is None:
        try:
            from eurika.orchestration.team_mode import load_pending_plan

            data = load_pending_plan(root)
        except Exception:
            data = None
    if not isinstance(data, dict):
        return 0
    ops = data.get("operations")
    if not isinstance(ops, list):
        return 0
    journal = load_hitl_journal(root)
    seen = {
        (
            str(row.get("proposal_hash") or ""),
            _norm_decision(row.get("decision")),
        )
        for row in (journal.get("decisions") or [])
        if isinstance(row, dict)
    }
    records = load_experiments(root)
    ag = journal.setdefault("aggregates", _empty_journal()["aggregates"])
    recorded = 0
    for op in ops:
        if not isinstance(op, dict):
            continue
        cur = _decision_from_op(op)
        if cur not in {"approve", "reject"}:
            continue
        ph = _proposal_hash(op)
        key = (ph, cur)
        if key in seen:
            continue
        journal.setdefault("decisions", []).append(
            {
                "ts": _now_iso(),
                "ts_ms": _now_ms(),
                "decision": cur,
                "kind": str(op.get("kind") or ""),
                "target": str(op.get("target_file") or ""),
                "proposal_hash": ph,
                "source": str(source or "pending_plan")[:64],
                "approved_by": op.get("approved_by"),
            }
        )
        ag[cur] = int(ag.get(cur) or 0) + 1
        seen.add(key)
        _update_experiment_for_hash(
            records,
            ph,
            status="decided",
            actual_result=f"human {cur}",
            conclusion="accept" if cur == "approve" else "reject",
            metrics_update={"decision": cur, "decision_source": source},
        )
        recorded += 1
    if recorded:
        _save_journal(root, journal)
        _save_experiments(root, records)
        try:
            _persist_self_improvement_into_stores(root)
        except Exception:
            pass
    return recorded


def recent_experiments(
    project_root: str | Path,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    recs = load_experiments(project_root)
    return list(reversed(recs[-max(1, limit) :]))


def format_experiments_brief(
    project_root: str | Path,
    *,
    limit: int = 3,
) -> List[str]:
    rows = recent_experiments(project_root, limit=limit)
    if not rows:
        return []
    lines = [f"- experiments recent={len(rows)} (showing last {min(limit, len(rows))})"]
    for r in rows[:limit]:
        lines.append(
            f"  · {r.get('conclusion') or r.get('status')}: "
            f"{r.get('change') or r.get('hypothesis') or r.get('id')}"
        )
    return lines
