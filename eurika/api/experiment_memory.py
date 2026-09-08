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
    return out


def _save_journal(project_root: str | Path, journal: Dict[str, Any]) -> None:
    journal["updated_at"] = _now_iso()
    journal["version"] = JOURNAL_VERSION
    journal["decisions"] = list(journal.get("decisions") or [])[-MAX_DECISIONS:]
    journal["applies"] = list(journal.get("applies") or [])[-MAX_APPLIES:]
    _atomic_write_json(journal_path(project_root), journal)


def load_experiments(project_root: str | Path) -> List[Dict[str, Any]]:
    data = load_json_safe(experiments_path(project_root))
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [r for r in data["records"] if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _save_experiments(project_root: str | Path, records: List[Dict[str, Any]]) -> None:
    payload = {
        "version": JOURNAL_VERSION,
        "updated_at": _now_iso(),
        "records": records[-MAX_EXPERIMENTS:],
    }
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
    return {
        "level": 0.0 if insufficient else rate,
        "accept_rate": rate if n else None,
        "approve": approve,
        "reject": reject,
        "n": n,
        "apply_ok": apply_ok,
        "apply_fail": apply_fail,
        "apply_n": apply_n,
        "insufficient_data": insufficient,
        "evidence": (
            f"HITL decisions approve={approve} reject={reject} "
            f"(rate={rate if n else 'n/a'}); "
            f"apply_ok={apply_ok}/{apply_n if apply_n else 0}"
        ),
        "note": "accept_rate is human decision rate, not code quality",
    }


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
