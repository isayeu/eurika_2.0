"""Formal A/B v0+ (VISION Stage 4 Experimenter).

Compare baseline (main) vs treatment (sandbox) on fixed metrics after C.14
propose+sandbox. Does not auto-apply or invent success.

Metrics (from self_map / graph when present):
  core — energy, risk_score, total_smells, cycles, smoke_ok
  suite — modules, dependency_density, max_blast_radius, layer_violations
  (layer_violations increase is a hard regression; others are recorded deltas)

Sandbox rescan (``EURIKA_AB_RESCAN``):
  off/0 — never; on/1/force — always; auto (default) — only when
  architecture metrics look stable (history swing small) and self_map was
  seeded into the worktree (otherwise treatment would always tie).

Persists to ``.eurika/ab_trials.json`` and experiment ``metrics.ab_v0``.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eurika.utils.json_io import as_dict, load_json_safe

AB_TRIALS_NAME = "ab_trials.json"
AB_VERSION = 2
MAX_TRIALS = 40
CORE_METRIC_KEYS = ("energy", "score", "risk_score", "total_smells", "cycles")
SUITE_METRIC_KEYS = (
    "modules",
    "dependency_density",
    "max_blast_radius",
    "layer_violations",
)
STABILITY_WINDOW = 5
STABILITY_MAX_SMELL_SWING = 3
STABILITY_MAX_MODULE_SWING = 8


def ab_trials_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / AB_TRIALS_NAME


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


def snapshot_ab_metrics(project_root: str | Path) -> Dict[str, Any]:
    """Fixed metric snapshot from ``self_map.json`` (no Market ML)."""
    root = Path(project_root).resolve()
    self_map = root / "self_map.json"
    if not self_map.is_file():
        return {
            "ok": False,
            "insufficient_data": True,
            "error": "self_map.json missing",
            "energy": None,
            "score": None,
            "risk_score": None,
            "total_smells": None,
            "cycles": None,
            "modules": None,
            "dependency_density": None,
            "max_blast_radius": None,
            "layer_violations": None,
        }
    try:
        from eurika.analysis.metrics import dependency_density, top_blast_radius
        from eurika.analysis.self_map import build_graph_from_self_map
        from eurika.reasoning.graph_ops import metrics_from_graph
        from eurika.smells.detector import detect_architecture_smells

        graph = build_graph_from_self_map(self_map)
        smells = detect_architecture_smells(graph)
        metrics = metrics_from_graph(graph, smells, {})
        cycles = graph.find_cycles()
        smell_n = len(smells) if isinstance(smells, list) else 0
        blast = top_blast_radius(graph, n=1)
        max_br = int(blast[0][1]) if blast else 0
        layer_n = None
        try:
            from eurika.checks.dependency_firewall import collect_layer_violations

            layer_n = len(collect_layer_violations(root))
        except Exception:
            layer_n = None
        return {
            "ok": True,
            "insufficient_data": False,
            "energy": metrics.get("energy"),
            "score": metrics.get("score"),
            "risk_score": metrics.get("risk_score"),
            "total_smells": smell_n,
            "cycles": len(cycles) if isinstance(cycles, list) else 0,
            "modules": len(getattr(graph, "nodes", []) or []),
            "dependency_density": dependency_density(graph),
            "max_blast_radius": max_br,
            "layer_violations": layer_n,
        }
    except Exception as exc:
        return {
            "ok": False,
            "insufficient_data": True,
            "error": str(exc)[:200],
            "energy": None,
            "score": None,
            "risk_score": None,
            "total_smells": None,
            "cycles": None,
            "modules": None,
            "dependency_density": None,
            "max_blast_radius": None,
            "layer_violations": None,
        }


def assess_metrics_stability(
    project_root: str | Path,
    *,
    window: int = STABILITY_WINDOW,
    max_smell_swing: int = STABILITY_MAX_SMELL_SWING,
    max_module_swing: int = STABILITY_MAX_MODULE_SWING,
) -> Dict[str, Any]:
    """True when recent architecture history swings are small enough for A/B rescan.

    Uses ``.eurika/history.json`` (last ``window`` points). Insufficient history
    ⇒ not stable (do not auto-rescan).
    """
    root = Path(project_root).resolve()
    hist_path = root / ".eurika" / "history.json"
    out: Dict[str, Any] = {
        "stable": False,
        "samples": 0,
        "window": int(window),
        "smell_swing": None,
        "module_swing": None,
        "cycles_changed": None,
        "reason": "no history",
    }
    if not hist_path.is_file():
        return out
    try:
        hdata = load_json_safe(hist_path)
        points: Any = None
        if isinstance(hdata, dict):
            points = hdata.get("history") or hdata.get("points")
        elif isinstance(hdata, list):
            points = hdata
        if not isinstance(points, list) or not points:
            out["reason"] = "empty history"
            return out
        recent = [p for p in points[-max(1, int(window)) :] if isinstance(p, dict)]
        out["samples"] = len(recent)
        if len(recent) < max(2, min(3, int(window))):
            out["reason"] = f"need>={max(2, min(3, int(window)))} history points"
            return out
        smells = [int(p.get("total_smells") or 0) for p in recent]
        modules = [int(p.get("modules") or 0) for p in recent]
        cycles = [int(p.get("cycles") or 0) for p in recent]
        smell_swing = max(smells) - min(smells)
        module_swing = max(modules) - min(modules)
        cycles_changed = max(cycles) != min(cycles)
        out["smell_swing"] = smell_swing
        out["module_swing"] = module_swing
        out["cycles_changed"] = cycles_changed
        # Relative module allowance: large graphs drift a few files without
        # meaning "unstable architecture" for A/B purposes.
        mod_cap = max(int(max_module_swing), int(0.03 * max(modules or [0])))
        out["module_swing_cap"] = mod_cap
        if smell_swing > int(max_smell_swing):
            out["reason"] = f"smell_swing={smell_swing}>{max_smell_swing}"
            return out
        if module_swing > mod_cap:
            out["reason"] = f"module_swing={module_swing}>{mod_cap}"
            return out
        if cycles_changed:
            out["reason"] = "cycles changed in window"
            return out
        out["stable"] = True
        out["reason"] = "stable"
        return out
    except Exception as exc:
        out["reason"] = f"history read failed: {exc}"[:120]
        return out


def _rescan_mode_from_env() -> str:
    """Normalize EURIKA_AB_RESCAN → off | on | auto (default auto)."""
    raw = os.environ.get("EURIKA_AB_RESCAN", "auto").strip().lower()
    if raw in {"", "auto", "stable", "when_stable"}:
        return "auto"
    if raw in {"0", "false", "no", "off", "never"}:
        return "off"
    if raw in {"1", "true", "yes", "on", "force", "always"}:
        return "on"
    return "auto"


def decide_ab_rescan(
    main_root: str | Path,
    *,
    self_map_seeded: bool,
) -> Tuple[bool, Dict[str, Any]]:
    """Whether to rescan sandbox before treatment snapshot."""
    mode = _rescan_mode_from_env()
    stability = assess_metrics_stability(main_root)
    meta: Dict[str, Any] = {
        "rescan_mode": mode,
        "metrics_stable": bool(stability.get("stable")),
        "stability": {
            k: stability.get(k)
            for k in (
                "stable",
                "samples",
                "window",
                "smell_swing",
                "module_swing",
                "cycles_changed",
                "reason",
            )
        },
        "self_map_seeded": bool(self_map_seeded),
        "should_rescan": False,
        "skip_reason": None,
    }
    if mode == "off":
        meta["skip_reason"] = "EURIKA_AB_RESCAN=off"
        return False, meta
    if mode == "on":
        meta["should_rescan"] = True
        return True, meta
    # auto: only when metrics stable AND seed would otherwise force a graph tie
    if not stability.get("stable"):
        meta["skip_reason"] = f"metrics not stable ({stability.get('reason')})"
        return False, meta
    if not self_map_seeded:
        meta["skip_reason"] = "self_map already present; auto rescan skipped"
        return False, meta
    meta["should_rescan"] = True
    return True, meta


def _run_sandbox_rescan(sandbox_root: Path) -> bool:
    """Invoke run_scan on sandbox. Returns True if call completed without raise."""
    try:
        from eurika.orchestration.deps import load_fix_cycle_deps

        deps = load_fix_cycle_deps()
        run_scan = deps.get("run_scan")
        if not callable(run_scan):
            return False
        try:
            run_scan(Path(sandbox_root).resolve(), scan_reason="ab_v0")
        except TypeError:
            run_scan(Path(sandbox_root).resolve())
        return True
    except Exception:
        return False


def _seed_self_map_for_ab(main: Path, sand: Path) -> bool:
    """Copy main ``self_map.json`` into sandbox when missing.

    Worktrees omit gitignored artifacts (``self_map.json``), so without a seed
    Formal A/B always reports insufficient. Seeding enables honest
    graph_unchanged / tie when rescan is off.
    """
    src = main / "self_map.json"
    dst = sand / "self_map.json"
    if not src.is_file() or dst.is_file():
        return False
    try:
        import shutil

        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def _delta_num(a: Any, b: Any) -> Optional[float]:
    try:
        if a is None or b is None:
            return None
        return float(b) - float(a)
    except (TypeError, ValueError):
        return None


def decide_ab_winner(
    baseline: Dict[str, Any],
    treatment: Dict[str, Any],
    *,
    smoke_ok: bool,
) -> tuple[str, str, bool]:
    """Return (winner, rule, insufficient_data).

    Winner: sandbox | baseline | tie | insufficient
    """
    if not smoke_ok:
        return (
            "baseline",
            "smoke_ok=false → treatment rejected",
            False,
        )
    if not baseline.get("ok") or not treatment.get("ok"):
        return (
            "insufficient",
            "graph metrics unavailable (need self_map); smoke_ok recorded only",
            True,
        )

    # Lower energy / smells / cycles better; higher risk_score (health) better.
    e_b, e_t = baseline.get("energy"), treatment.get("energy")
    r_b, r_t = baseline.get("risk_score"), treatment.get("risk_score")
    s_b, s_t = baseline.get("total_smells"), treatment.get("total_smells")
    c_b, c_t = baseline.get("cycles"), treatment.get("cycles")

    try:
        energy_ok = e_t is None or e_b is None or float(e_t) <= float(e_b)
        risk_ok = r_t is None or r_b is None or float(r_t) >= float(r_b)
        smells_ok = s_t is None or s_b is None or int(s_t) <= int(s_b)
        cycles_ok = c_t is None or c_b is None or int(c_t) <= int(c_b)
    except (TypeError, ValueError):
        return ("insufficient", "metric compare failed", True)

    lv_b, lv_t = baseline.get("layer_violations"), treatment.get("layer_violations")
    try:
        layers_ok = lv_t is None or lv_b is None or int(lv_t) <= int(lv_b)
    except (TypeError, ValueError):
        layers_ok = True

    rule = (
        "smoke_ok && energy_t<=energy_b && risk_t>=risk_b "
        "&& smells_t<=smells_b && cycles_t<=cycles_b"
        " && layer_violations_t<=layer_violations_b"
    )
    if not (energy_ok and risk_ok and smells_ok and cycles_ok and layers_ok):
        return ("baseline", rule + " → regression", False)

    equal = (
        (e_t is None or e_b is None or float(e_t) == float(e_b))
        and (r_t is None or r_b is None or float(r_t) == float(r_b))
        and (s_t is None or s_b is None or int(s_t) == int(s_b))
        and (c_t is None or c_b is None or int(c_t) == int(c_b))
        and (lv_t is None or lv_b is None or int(lv_t) == int(lv_b))
    )
    if equal:
        return (
            "tie",
            rule + " → equal graph metrics; smoke_ok only differentiator",
            False,
        )
    return ("sandbox", rule + " → no regression and improved", False)


def compare_ab(
    baseline: Dict[str, Any],
    treatment: Dict[str, Any],
    *,
    smoke_ok: bool,
    sandbox_mode: str = "",
    source: str = "",
    drill: str = "",
    kind: str = "",
    target: str = "",
    proposal_hash: str = "",
    rescanned: bool = False,
    self_map_seeded: bool = False,
    rescan_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    winner, rule, insuff = decide_ab_winner(baseline, treatment, smoke_ok=smoke_ok)
    keys = CORE_METRIC_KEYS + SUITE_METRIC_KEYS
    delta = {k: _delta_num(baseline.get(k), treatment.get(k)) for k in keys}
    graph_unchanged = (
        baseline.get("ok")
        and treatment.get("ok")
        and all(delta.get(k) in (0, 0.0, None) for k in keys)
        and smoke_ok
    )
    meta = rescan_meta if isinstance(rescan_meta, dict) else {}
    note = "A/B does not auto-apply; HITL still required"
    if self_map_seeded and not rescanned:
        note += "; self_map seeded from main (gitignored in worktree)"
    if meta.get("rescan_mode") == "auto" and meta.get("skip_reason"):
        note += f"; rescan skipped: {meta.get('skip_reason')}"
    if rescanned:
        note += "; sandbox rescanned before treatment snapshot"
    return {
        "version": AB_VERSION,
        "ts": _now_iso(),
        "ts_ms": _now_ms(),
        "proposal_hash": proposal_hash[:64],
        "source": str(source)[:80],
        "drill": str(drill)[:80],
        "kind": str(kind)[:80],
        "target": str(target)[:200],
        "sandbox_mode": str(sandbox_mode)[:32],
        "smoke_ok": bool(smoke_ok),
        "rescanned": bool(rescanned),
        "self_map_seeded": bool(self_map_seeded),
        "rescan_mode": str(meta.get("rescan_mode") or _rescan_mode_from_env())[:16],
        "metrics_stable": meta.get("metrics_stable"),
        "stability": meta.get("stability") if isinstance(meta.get("stability"), dict) else None,
        "rescan_skip_reason": meta.get("skip_reason"),
        "baseline": {k: baseline.get(k) for k in (*keys, "ok", "insufficient_data", "error")},
        "treatment": {
            k: treatment.get(k) for k in (*keys, "ok", "insufficient_data", "error")
        },
        "delta": delta,
        "winner": winner,
        "rule": rule,
        "insufficient_data": bool(insuff or baseline.get("insufficient_data") or treatment.get("insufficient_data")),
        "graph_unchanged": bool(graph_unchanged),
        "note": note,
    }


def load_ab_trials(project_root: str | Path) -> List[Dict[str, Any]]:
    data = load_json_safe(ab_trials_path(project_root))
    if isinstance(data, dict) and isinstance(data.get("trials"), list):
        return [t for t in data["trials"] if isinstance(t, dict)]
    if isinstance(data, list):
        return [t for t in data if isinstance(t, dict)]
    return []


def persist_ab_trial(project_root: str | Path, trial: Dict[str, Any]) -> Dict[str, Any]:
    """Append trial to ab_trials.json and experiment metrics.ab_v0."""
    root = Path(project_root).resolve()
    trials = load_ab_trials(root)
    trials.append(trial)
    payload = {
        "version": AB_VERSION,
        "updated_at": _now_iso(),
        "trials": trials[-MAX_TRIALS:],
        "note": "formal A/B v0 — baseline vs sandbox; hypothesis ≠ fact",
    }
    _atomic_write_json(ab_trials_path(root), payload)

    ph = str(trial.get("proposal_hash") or "")
    if ph:
        try:
            from eurika.api.experiment_memory import (
                _save_experiments,
                _update_experiment_for_hash,
                load_experiments,
            )

            records = load_experiments(root)
            _update_experiment_for_hash(
                records,
                ph,
                metrics_update={"ab_v0": trial},
            )
            _save_experiments(root, records)
        except Exception:
            pass
    return trial


def run_ab_compare(
    main_root: str | Path,
    sandbox_root: str | Path,
    *,
    smoke_ok: bool,
    sandbox_mode: str = "",
    operation: Optional[Dict[str, Any]] = None,
    source: str = "",
    drill: str = "",
) -> Dict[str, Any]:
    """Snapshot main vs sandbox, decide winner, persist trial."""
    main = Path(main_root).resolve()
    sand = Path(sandbox_root).resolve()
    op = operation if isinstance(operation, dict) else {}
    kind = str(op.get("kind") or "")
    target = str(op.get("target_file") or "")
    ph = _proposal_hash(op) if op else ""
    baseline = snapshot_ab_metrics(main)
    rescanned = False
    self_map_seeded = False
    rescan_meta: Dict[str, Any] = {
        "rescan_mode": _rescan_mode_from_env(),
        "metrics_stable": None,
        "stability": None,
        "skip_reason": None,
    }
    if smoke_ok:
        # Seed before optional rescan so scan can refresh an existing map.
        self_map_seeded = _seed_self_map_for_ab(main, sand)
        do_rescan, rescan_meta = decide_ab_rescan(
            main, self_map_seeded=self_map_seeded
        )
        if do_rescan:
            rescanned = _run_sandbox_rescan(sand)
            if not rescanned:
                rescan_meta["skip_reason"] = (
                    rescan_meta.get("skip_reason") or "run_scan failed"
                )
    treatment = snapshot_ab_metrics(sand) if smoke_ok else {
        "ok": False,
        "insufficient_data": True,
        "error": "smoke failed — treatment not scored",
        "energy": None,
        "score": None,
        "risk_score": None,
        "total_smells": None,
        "cycles": None,
        "modules": None,
        "dependency_density": None,
        "max_blast_radius": None,
        "layer_violations": None,
    }
    trial = compare_ab(
        baseline,
        treatment,
        smoke_ok=bool(smoke_ok),
        sandbox_mode=sandbox_mode,
        source=source,
        drill=drill or str(op.get("drill") or ""),
        kind=kind,
        target=target,
        proposal_hash=ph,
        rescanned=rescanned,
        self_map_seeded=self_map_seeded,
        rescan_meta=rescan_meta,
    )
    try:
        persist_ab_trial(main, trial)
    except Exception:
        pass
    return trial


def format_ab_text(
    project_root: str | Path,
    *,
    limit: int = 5,
    trial: Optional[Dict[str, Any]] = None,
) -> str:
    root = Path(project_root).resolve()
    rows = [trial] if isinstance(trial, dict) else load_ab_trials(root)[-limit:]
    stab = assess_metrics_stability(root)
    lines = [
        "Formal A/B v2 (baseline vs sandbox)",
        "(core: energy, risk_score, smells, cycles, smoke_ok; "
        "suite: modules, density, max_blast, layer_violations)",
        (
            f"(rescan mode={_rescan_mode_from_env()}; metrics_stable="
            f"{stab.get('stable')} reason={stab.get('reason')})"
        ),
        "",
    ]
    if not rows or rows == [None]:
        rows = load_ab_trials(root)[-limit:]
    if not rows:
        lines.append("Нет A/B trials. Нужен bug-hunt/prove-cycle с --sandbox.")
        lines.append("CLI: `eurika ab-compare .` · Chat: «a/b» / «сравни sandbox»")
        lines.append(
            "EURIKA_AB_RESCAN=auto|on|off — auto rescans sandbox when metrics stable"
        )
        return "\n".join(lines)
    for t in reversed(rows[-limit:]):
        if not isinstance(t, dict):
            continue
        lines.append(
            f"[{t.get('winner')}] {t.get('kind')} → {t.get('target')} "
            f"(smoke_ok={t.get('smoke_ok')}, mode={t.get('sandbox_mode')})"
        )
        d = as_dict(t.get("delta"))
        lines.append(
            f"  Δ energy={d.get('energy')} risk={d.get('risk_score')} "
            f"smells={d.get('total_smells')} cycles={d.get('cycles')}"
        )
        if any(d.get(k) not in (None, 0, 0.0) for k in SUITE_METRIC_KEYS):
            lines.append(
                f"  suite Δ modules={d.get('modules')} density={d.get('dependency_density')} "
                f"blast={d.get('max_blast_radius')} layers={d.get('layer_violations')}"
            )
        lines.append(
            f"  rescanned={t.get('rescanned')} rescan_mode={t.get('rescan_mode')} "
            f"metrics_stable={t.get('metrics_stable')}"
        )
        if t.get("graph_unchanged"):
            lines.append(
                "  graph_unchanged=true "
                "(EURIKA_AB_RESCAN=auto|on for sandbox rescan when stable)"
            )
        if t.get("self_map_seeded"):
            lines.append("  self_map_seeded=true (worktree lacked gitignored self_map.json)")
        if t.get("rescan_skip_reason"):
            lines.append(f"  rescan_skip: {t.get('rescan_skip_reason')}")
        if t.get("insufficient_data"):
            lines.append("  insufficient_data=true")
        lines.append(f"  rule: {t.get('rule')}")
        lines.append("")
    lines.append("Chat: «a/b». CLI: `eurika ab-compare .` — HITL apply не трогает.")
    return "\n".join(lines).rstrip() + "\n"


def format_ab_brief(project_root: str | Path, *, limit: int = 2) -> List[str]:
    rows = load_ab_trials(project_root)
    if not rows:
        return []
    lines = ["", "A/B trials:", f"- recent={min(limit, len(rows))} / total={len(rows)}"]
    for t in reversed(rows[-limit:]):
        lines.append(
            f"  · [{t.get('winner')}] {t.get('kind')}: {t.get('target')}"
        )
    return lines
