"""Self + Capability + Goal Model v0 (VISION § Master).

Builds a measurable snapshot from on-disk facts — not a hand-edited brain dump.
Persists to ``.eurika/self_model.json`` (regenerated on refresh).
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from eurika.utils.json_io import load_json_safe

SNAPSHOT_NAME = "self_model.json"
SNAPSHOT_VERSION = 1


def snapshot_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / SNAPSHOT_NAME


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return str(version("eurika"))
    except Exception:
        pass
    try:
        import eurika

        return str(getattr(eurika, "__version__", "") or "unknown")
    except Exception:
        return "unknown"


def _top_modules(root: Path, *, limit: int = 24) -> List[str]:
    self_map = load_json_safe(root / "self_map.json")
    if isinstance(self_map, dict):
        nodes = self_map.get("nodes") or self_map.get("modules") or []
        names: List[str] = []
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    nid = str(node.get("id") or node.get("name") or "").strip()
                else:
                    nid = str(node).strip()
                if nid:
                    names.append(nid)
                if len(names) >= limit:
                    break
        if names:
            return names
    pkg = root / "eurika"
    if not pkg.is_dir():
        return []
    out: List[str] = []
    for child in sorted(pkg.iterdir()):
        if child.name.startswith("_"):
            continue
        if child.is_dir() and (child / "__init__.py").is_file():
            out.append(f"eurika.{child.name}")
        elif child.suffix == ".py":
            out.append(f"eurika.{child.stem}")
        if len(out) >= limit:
            break
    return out


def _chat_capabilities() -> List[Dict[str, Any]]:
    try:
        from eurika.api.task_executor import CAPABILITIES
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for intent, meta in sorted(CAPABILITIES.items()):
        if not isinstance(meta, dict):
            continue
        rows.append(
            {
                "id": intent,
                "risk_level": str(meta.get("risk_level") or "medium"),
                "requires_confirmation": bool(meta.get("requires_confirmation", True)),
            }
        )
    return rows


def _level_from_ratio(ok: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(max(0.0, min(1.0, float(ok) / float(total))), 3)


def _verify_capability(root: Path) -> Dict[str, Any]:
    """Score patch/verify outcomes from EventStore when present."""
    try:
        from eurika.storage.event_engine import event_engine

        store = event_engine(root)
        events = store.recent_events(limit=80, types=("patch", "verify", "learn"))
    except Exception:
        return {
            "level": 0.0,
            "evidence": "events unavailable",
            "ok": 0,
            "n": 0,
            "insufficient_data": True,
        }
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
    return {
        "level": 0.0 if insufficient else _level_from_ratio(ok, n),
        "evidence": f"recent patch/verify/learn with result: {ok}/{n}",
        "ok": ok,
        "n": n,
        "insufficient_data": insufficient,
    }


def _idle_capability(root: Path) -> Dict[str, Any]:
    try:
        from eurika.orchestration.idle_self_dev import (
            DETERMINISTIC_DRILLS,
            SATURATED_MIN_SUCCESS,
            load_stamp,
            _drill_ok_counts,
        )

        stamp = load_stamp(root)
        counts = _drill_ok_counts(stamp=stamp)
        saturated = sum(
            1
            for d in DETERMINISTIC_DRILLS
            if int(counts.get(d) or 0) >= int(SATURATED_MIN_SUCCESS)
        )
        total = max(1, len(DETERMINISTIC_DRILLS))
        level = _level_from_ratio(saturated, total)
        return {
            "level": level,
            "evidence": f"idle drill_ok saturated {saturated}/{total} "
            f"(min_success={SATURATED_MIN_SUCCESS}); counts={counts}",
            "drill_ok": counts,
            "last_drill": stamp.get("last_drill"),
            "last_ok": stamp.get("last_ok"),
            "insufficient_data": not bool(counts),
        }
    except Exception as exc:
        return {
            "level": 0.0,
            "evidence": f"idle stamp unavailable: {exc}",
            "insufficient_data": True,
        }


def _bug_hunt_capability(root: Path) -> Dict[str, Any]:
    try:
        from eurika.orchestration.bug_hunt import load_bug_hunt_stamp

        stamp = load_bug_hunt_stamp(root)
        recent = stamp.get("recent") if isinstance(stamp, dict) else None
        n = len(recent) if isinstance(recent, list) else 0
        hitl = {}
        try:
            from eurika.api.experiment_memory import hitl_accept_rate

            hitl = hitl_accept_rate(root)
        except Exception:
            hitl = {}
        # Prefer measured HITL accept rate when enough decisions exist.
        if isinstance(hitl, dict) and not hitl.get("insufficient_data"):
            level = float(hitl.get("level") or 0.0)
            return {
                "level": round(level, 3),
                "evidence": (
                    f"HITL accept_rate={hitl.get('accept_rate')} "
                    f"(approve={hitl.get('approve')} reject={hitl.get('reject')}); "
                    f"bug_hunt recent proposes={n}"
                ),
                "recent_n": n,
                "accept_rate": hitl.get("accept_rate"),
                "insufficient_data": False,
                "note": "level tracks human accept rate, not propose volume",
            }
        level = _level_from_ratio(min(n, 8), 8) * 0.5 if n else 0.0
        hitl_ev = ""
        if isinstance(hitl, dict) and hitl.get("evidence"):
            hitl_ev = str(hitl.get("evidence"))
        return {
            "level": round(level, 3),
            "evidence": (
                f"recent proposes remembered: {n}"
                + (f"; {hitl_ev}" if hitl_ev else "")
            ),
            "recent_n": n,
            "insufficient_data": True,
            "note": "need ≥3 HITL approve/reject decisions for accept-rate level",
        }
    except Exception as exc:
        return {
            "level": 0.0,
            "evidence": f"bug_hunt stamp unavailable: {exc}",
            "insufficient_data": True,
        }


def _hitl_capability(root: Path) -> Dict[str, Any]:
    try:
        from eurika.api.experiment_memory import hitl_accept_rate

        return hitl_accept_rate(root)
    except Exception as exc:
        return {
            "level": 0.0,
            "evidence": f"HITL journal unavailable: {exc}",
            "insufficient_data": True,
        }


def _self_improvement_scores(root: Path) -> Dict[str, Dict[str, Any]]:
    """Stage 5 Capability scores beyond accept-rate."""
    try:
        from eurika.api.experiment_memory import compute_self_improvement_metrics

        m = compute_self_improvement_metrics(root)
    except Exception as exc:
        empty = {
            "level": 0.0,
            "insufficient_data": True,
            "evidence": f"metrics unavailable: {exc}",
        }
        return {
            "apply_ok_rate": dict(empty),
            "verify_by_kind": dict(empty),
            "time_to_decide": dict(empty),
            "hypotheses_supported": dict(empty),
        }
    out: Dict[str, Dict[str, Any]] = {}
    for key in (
        "apply_ok_rate",
        "verify_by_kind",
        "time_to_decide",
        "hypotheses_supported",
    ):
        row = m.get(key) if isinstance(m.get(key), dict) else {}
        out[key] = row if isinstance(row, dict) else {
            "level": 0.0,
            "insufficient_data": True,
            "evidence": "missing",
        }
    return out


def _goal_block(root: Path) -> Dict[str, Any]:
    from eurika.api.chat_context import load_dialog_state

    state = load_dialog_state(root)
    if not isinstance(state, dict):
        state = {}
    goal = state.get("active_goal")
    last = state.get("last_execution")
    goal_dict = goal if isinstance(goal, dict) and goal else None
    last_dict = last if isinstance(last, dict) and last else None
    criteria: List[str] = []
    if goal_dict:
        intent = str(goal_dict.get("intent") or "")
        if intent in {"idle_self_dev", "polygon_propose", "bug_hunt"}:
            criteria = [
                "sandbox verify ok",
                "parked in .eurika/pending_plan.json",
                "human approve → eurika fix . --apply-approved",
            ]
        elif intent:
            criteria = ["execution ok", "verification_ok when applicable"]
    return {
        "active": goal_dict,
        "last_execution": last_dict,
        "success_criteria": criteria,
        "status": (
            "active"
            if goal_dict
            else ("post_release" if last_dict else "empty")
        ),
    }


def _experiments(root: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from eurika.orchestration.idle_self_dev import load_stamp, status

        stamp = load_stamp(root)
        st = status(root)
        out["idle_self_dev"] = {
            "last_drill": stamp.get("last_drill"),
            "last_ok": stamp.get("last_ok"),
            "due": st.get("due"),
            "idle": st.get("idle"),
            "next_drill": st.get("next_drill"),
            "pending_unresolved": st.get("pending_unresolved"),
        }
    except Exception as exc:
        out["idle_self_dev"] = {"error": str(exc), "insufficient_data": True}
    try:
        from eurika.orchestration.bug_hunt import load_bug_hunt_stamp

        bh = load_bug_hunt_stamp(root)
        recent = bh.get("recent") if isinstance(bh, dict) else []
        out["bug_hunt"] = {
            "recent_n": len(recent) if isinstance(recent, list) else 0,
            "last": (recent[-1] if isinstance(recent, list) and recent else None),
        }
    except Exception as exc:
        out["bug_hunt"] = {"error": str(exc), "insufficient_data": True}
    try:
        from eurika.orchestration.team_mode import load_pending_plan

        plan = load_pending_plan(root)
        ops = plan.get("operations") if isinstance(plan, dict) else None
        pending = 0
        if isinstance(ops, list):
            pending = sum(
                1
                for op in ops
                if isinstance(op, dict)
                and str(op.get("team_decision") or "pending").strip().lower()
                == "pending"
            )
        out["approvals_pending"] = pending
    except Exception:
        out["approvals_pending"] = None
    try:
        from eurika.api.experiment_memory import (
            hitl_accept_rate,
            load_experiments,
            recent_experiments,
        )

        rate = hitl_accept_rate(root)
        recs = load_experiments(root)
        out["hitl"] = {
            "accept_rate": rate.get("accept_rate"),
            "approve": rate.get("approve"),
            "reject": rate.get("reject"),
            "apply_ok": rate.get("apply_ok"),
            "apply_fail": rate.get("apply_fail"),
            "apply_ok_rate": rate.get("apply_ok_rate"),
            "insufficient_data": rate.get("insufficient_data"),
        }
        try:
            from eurika.api.experiment_memory import compute_self_improvement_metrics

            out["self_improvement"] = compute_self_improvement_metrics(root)
        except Exception as exc:
            out["self_improvement"] = {"error": str(exc), "insufficient_data": True}
        out["experiment_records"] = {
            "n": len(recs),
            "recent": [
                {
                    "conclusion": r.get("conclusion"),
                    "status": r.get("status"),
                    "change": r.get("change"),
                    "kind": r.get("kind"),
                    "target": r.get("target"),
                }
                for r in recent_experiments(root, limit=5)
            ],
        }
    except Exception as exc:
        out["hitl"] = {"error": str(exc), "insufficient_data": True}
        out["experiment_records"] = {"n": 0, "recent": []}
    return out


def _self_block(root: Path) -> Dict[str, Any]:
    eurika_dir = root / ".eurika"
    return {
        "package_version": _package_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "modules_top": _top_modules(root),
        "tools": [
            "scan",
            "doctor",
            "fix",
            "prove-cycle",
            "bug-hunt",
            "idle-self-dev",
            "self-model",
            "hypotheses",
            "learn-github",
        ],
        "constraints": [
            "Architecture Freeze: no silent core rewrite",
            "C.14 apply only via HITL / --apply-approved",
            "Market: paper only; ops freeze on entry/HTF/explore",
        ],
        "artifacts": {
            "self_map": (root / "self_map.json").is_file(),
            "events": (eurika_dir / "events.json").is_file(),
            "dialog_state": (eurika_dir / "chat_history" / "dialog_state.json").is_file(),
            "idle_self_dev": (eurika_dir / "idle_self_dev.json").is_file(),
            "bug_hunt": (eurika_dir / "bug_hunt.json").is_file(),
            "pending_plan": (eurika_dir / "pending_plan.json").is_file(),
            "pattern_library": (eurika_dir / "pattern_library.json").is_file(),
            "hypotheses": (eurika_dir / "hypotheses.json").is_file(),
            "hitl_journal": (eurika_dir / "hitl_journal.json").is_file(),
            "experiments": (eurika_dir / "experiments.json").is_file(),
        },
    }


def build_self_model(project_root: str | Path) -> Dict[str, Any]:
    """Rebuild snapshot from current facts (always fresh)."""
    root = Path(project_root).resolve()
    extra_scores = _self_improvement_scores(root)
    return {
        "version": SNAPSHOT_VERSION,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_ms": int(time.time() * 1000),
        "project_root": str(root),
        "self": _self_block(root),
        "capabilities": {
            "chat_intents": _chat_capabilities(),
            "scores": {
                "c14_idle_drills": _idle_capability(root),
                "hitl_accept_rate": _hitl_capability(root),
                "bug_hunt_proposes": _bug_hunt_capability(root),
                "verify_events": _verify_capability(root),
                **extra_scores,
            },
        },
        "goal": _goal_block(root),
        "experiments": _experiments(root),
        "self_improvement": {
            k: extra_scores.get(k)
            for k in (
                "apply_ok_rate",
                "verify_by_kind",
                "time_to_decide",
                "hypotheses_supported",
            )
        },
    }


def persist_self_model(
    project_root: str | Path,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write snapshot to ``.eurika/self_model.json`` (atomic)."""
    root = Path(project_root).resolve()
    snap = snapshot if isinstance(snapshot, dict) else build_self_model(root)
    _atomic_write_json(snapshot_path(root), snap)
    return snap


def load_self_model(
    project_root: str | Path,
    *,
    refresh: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Load snapshot; by default rebuild from facts and persist."""
    root = Path(project_root).resolve()
    if refresh:
        snap = build_self_model(root)
        if persist:
            persist_self_model(root, snap)
        return snap
    cached = load_json_safe(snapshot_path(root))
    if isinstance(cached, dict) and cached:
        return cached
    snap = build_self_model(root)
    if persist:
        persist_self_model(root, snap)
    return snap


def format_self_model_text(
    snapshot: Optional[Dict[str, Any]],
    *,
    mode: str = "full",
) -> str:
    """Human-readable Self / Capability / Goal block."""
    if not isinstance(snapshot, dict) or not snapshot:
        return (
            "Self Model: недостаточно данных. "
            "Запусти `eurika self-model .` или scan / idle-self-dev."
        )
    self_b = snapshot.get("self") if isinstance(snapshot.get("self"), dict) else {}
    caps = snapshot.get("capabilities") if isinstance(snapshot.get("capabilities"), dict) else {}
    scores = caps.get("scores") if isinstance(caps.get("scores"), dict) else {}
    goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
    experiments = (
        snapshot.get("experiments")
        if isinstance(snapshot.get("experiments"), dict)
        else {}
    )

    lines: List[str] = [
        f"Self Model v{snapshot.get('version', '?')} "
        f"(updated {snapshot.get('updated_at') or 'n/a'})",
        "",
        "Self:",
        f"- version={self_b.get('package_version') or '?'}, "
        f"python={self_b.get('python') or '?'}",
    ]
    arts = self_b.get("artifacts") if isinstance(self_b.get("artifacts"), dict) else {}
    if arts:
        present = [k for k, v in arts.items() if v]
        missing = [k for k, v in arts.items() if not v]
        lines.append(f"- artifacts ok: {', '.join(present) or '—'}")
        if missing and mode == "full":
            lines.append(f"- artifacts missing: {', '.join(missing)}")
    mods = self_b.get("modules_top") or []
    if isinstance(mods, list) and mods and mode == "full":
        lines.append(f"- modules (top): {', '.join(str(m) for m in mods[:12])}")
    constraints = self_b.get("constraints") or []
    if isinstance(constraints, list) and constraints and mode == "full":
        lines.append("- constraints:")
        for c in constraints[:4]:
            lines.append(f"  - {c}")

    lines.append("")
    lines.append("Capabilities (measured):")
    score_keys = (
        "c14_idle_drills",
        "hitl_accept_rate",
        "bug_hunt_proposes",
        "verify_events",
        "apply_ok_rate",
        "verify_by_kind",
        "time_to_decide",
        "hypotheses_supported",
    )
    for key in score_keys:
        row = scores.get(key) if isinstance(scores.get(key), dict) else {}
        level = row.get("level", 0.0)
        try:
            level = round(float(level), 3)
        except (TypeError, ValueError):
            pass
        insuff = bool(row.get("insufficient_data"))
        tag = "insufficient_data" if insuff else f"level={level}"
        lines.append(f"- {key}: {tag}")
        if mode == "full" and row.get("evidence"):
            lines.append(f"  evidence: {row.get('evidence')}")
        if mode == "full" and row.get("note"):
            lines.append(f"  note: {row.get('note')}")
        if mode == "full" and key == "verify_by_kind":
            by_kind = row.get("by_kind") if isinstance(row.get("by_kind"), dict) else {}
            for kind, st in list(by_kind.items())[:5]:
                if not isinstance(st, dict):
                    continue
                vs = int(st.get("verify_success") or 0)
                vf = int(st.get("verify_fail") or 0)
                lines.append(f"  · {kind}: verify={vs}/{vs + vf} rate={st.get('rate')}")
        if mode == "full" and key == "time_to_decide" and row.get("median_ms") is not None:
            lines.append(f"  median_ms={row.get('median_ms')} samples={row.get('samples')}")
        if mode == "full" and key == "apply_ok_rate" and row.get("rate") is not None:
            lines.append(f"  rate={row.get('rate')} ({row.get('apply_ok')}/{row.get('n')})")
        if mode == "full" and key == "hypotheses_supported" and row.get("share") is not None:
            lines.append(
                f"  share={row.get('share')} supported={row.get('supported')}/{row.get('n')}"
            )

    intents = caps.get("chat_intents") if isinstance(caps.get("chat_intents"), list) else []
    if intents and mode == "full":
        lines.append(f"- chat executor intents: {len(intents)} registered")

    lines.append("")
    lines.append("Goal:")
    status = goal.get("status") or "empty"
    active = goal.get("active") if isinstance(goal.get("active"), dict) else None
    last = goal.get("last_execution") if isinstance(goal.get("last_execution"), dict) else None
    if active:
        intent = active.get("intent") or "-"
        target = str(active.get("target") or "").strip()
        head = f"- status={status}, intent={intent}"
        if target:
            head += f", target={target}"
        lines.append(head)
    else:
        lines.append(f"- status={status} (нет sticky active_goal)")
    if last:
        lines.append(
            f"- last_execution: ok={last.get('ok')}, "
            f"summary={last.get('summary') or '-'}"
        )
    criteria = goal.get("success_criteria") or []
    if isinstance(criteria, list) and criteria and mode == "full":
        lines.append("- success_criteria:")
        for c in criteria[:5]:
            lines.append(f"  - {c}")

    if mode == "full":
        lines.append("")
        lines.append("Experiments:")
        idle = experiments.get("idle_self_dev")
        if isinstance(idle, dict):
            lines.append(
                f"- idle: next={idle.get('next_drill')}, due={idle.get('due')}, "
                f"last_ok={idle.get('last_ok')}"
            )
        bh = experiments.get("bug_hunt")
        if isinstance(bh, dict):
            lines.append(f"- bug_hunt recent_n={bh.get('recent_n')}")
        ap = experiments.get("approvals_pending")
        if ap is not None:
            lines.append(f"- approvals_pending={ap}")
        hitl = experiments.get("hitl") if isinstance(experiments.get("hitl"), dict) else {}
        if hitl:
            if hitl.get("insufficient_data"):
                lines.append(
                    f"- hitl: insufficient_data "
                    f"(A={hitl.get('approve')} R={hitl.get('reject')})"
                )
            else:
                lines.append(
                    f"- hitl: accept_rate={hitl.get('accept_rate')} "
                    f"(A={hitl.get('approve')} R={hitl.get('reject')}; "
                    f"apply_ok={hitl.get('apply_ok')}"
                    f", apply_ok_rate={hitl.get('apply_ok_rate')})"
                )
        si = (
            experiments.get("self_improvement")
            if isinstance(experiments.get("self_improvement"), dict)
            else {}
        )
        if si and mode == "full":
            aok = si.get("apply_ok_rate") if isinstance(si.get("apply_ok_rate"), dict) else {}
            ttd = si.get("time_to_decide") if isinstance(si.get("time_to_decide"), dict) else {}
            hs = (
                si.get("hypotheses_supported")
                if isinstance(si.get("hypotheses_supported"), dict)
                else {}
            )
            lines.append(
                f"- self_improvement: apply_ok_rate={aok.get('rate')}, "
                f"time_to_decide_median_ms={ttd.get('median_ms')}, "
                f"hyp_supported_share={hs.get('share')}"
            )
        exp = (
            experiments.get("experiment_records")
            if isinstance(experiments.get("experiment_records"), dict)
            else {}
        )
        if exp.get("n"):
            lines.append(f"- experiment_records: n={exp.get('n')}")
            for row in (exp.get("recent") or [])[:3]:
                if isinstance(row, dict):
                    lines.append(
                        f"  · {row.get('conclusion') or row.get('status')}: "
                        f"{row.get('change') or '?'}"
                    )
        try:
            from eurika.api.hypothesis_engine import load_hypotheses

            root_s = str(snapshot.get("project_root") or "").strip()
            hyps = load_hypotheses(root_s) if root_s else []
            open_n = sum(
                1 for h in hyps if str(h.get("status")) in {"open", "insufficient"}
            )
            if hyps:
                lines.append(f"- open hypotheses: {open_n}/{len(hyps)}")
        except Exception:
            pass

    if mode == "brief":
        return "\n".join(lines)

    lines.append("")
    lines.append(
        "Chat: «какая цель?» · «что получилось?» · «модель себя» · «гипотезы». "
        "CLI: `eurika self-model .` / `eurika hypotheses .`"
    )
    return "\n".join(lines)


def format_self_model_brief(project_root: str | Path) -> List[str]:
    """Compact lines for Context panel (no disk write)."""
    try:
        snap = build_self_model(project_root)
    except Exception:
        return []
    out: List[str] = ["", "Self / Capability / Goal:"]
    self_b = snap.get("self") if isinstance(snap.get("self"), dict) else {}
    out.append(
        f"- self: v={self_b.get('package_version') or '?'}, "
        f"py={self_b.get('python') or '?'}"
    )
    scores = (
        (snap.get("capabilities") or {}).get("scores")
        if isinstance(snap.get("capabilities"), dict)
        else {}
    )
    if isinstance(scores, dict):
        for key in (
            "c14_idle_drills",
            "hitl_accept_rate",
            "bug_hunt_proposes",
            "verify_events",
            "apply_ok_rate",
            "verify_by_kind",
            "time_to_decide",
            "hypotheses_supported",
        ):
            row = scores.get(key) if isinstance(scores.get(key), dict) else {}
            if not row:
                continue
            if row.get("insufficient_data"):
                out.append(f"- {key}: insufficient_data")
            else:
                level = row.get("level", 0.0)
                try:
                    level = round(float(level), 3)
                except (TypeError, ValueError):
                    pass
                extra = ""
                if key == "apply_ok_rate" and row.get("rate") is not None:
                    extra = f" rate={row.get('rate')}"
                elif key == "time_to_decide" and row.get("median_ms") is not None:
                    extra = f" median_ms={row.get('median_ms')}"
                elif key == "hypotheses_supported" and row.get("share") is not None:
                    extra = f" share={row.get('share')}"
                elif key == "verify_by_kind" and row.get("overall_rate") is not None:
                    extra = f" overall={row.get('overall_rate')}"
                out.append(f"- {key}: level={level}{extra}")
    goal = snap.get("goal") if isinstance(snap.get("goal"), dict) else {}
    out.append(f"- goal.status={goal.get('status') or 'empty'}")
    experiments = (
        snap.get("experiments")
        if isinstance(snap.get("experiments"), dict)
        else {}
    )
    hitl = experiments.get("hitl") if isinstance(experiments.get("hitl"), dict) else {}
    if hitl:
        rate = hitl.get("accept_rate")
        if rate is not None:
            aok = hitl.get("apply_ok_rate")
            aok_s = f", apply_ok_rate={aok}" if aok is not None else ""
            out.append(
                f"- hitl: accept_rate={rate} "
                f"(A={hitl.get('approve')} R={hitl.get('reject')}"
                f"{aok_s})"
            )
        elif hitl.get("insufficient_data"):
            out.append("- hitl: insufficient_data (<3 decisions)")
    exp = (
        experiments.get("experiment_records")
        if isinstance(experiments.get("experiment_records"), dict)
        else {}
    )
    if exp.get("n"):
        out.append(f"- experiments: n={exp.get('n')}")
    return out
