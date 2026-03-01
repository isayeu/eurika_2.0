"""Explain API routes (ROADMAP 3.1-arch.5, R1 Domain vs Presentation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def get_explain_data(project_root: Path, module_arg: str, window: int = 5) -> tuple[Dict[str, Any] | None, str | None]:
    """
    Domain: return structured explain data (R1 Domain vs Presentation).
    Returns (data_dict, error_message). Caller formats via format_explain_result.
    """
    from eurika.api import get_patch_plan
    from eurika.core.pipeline import run_full_analysis
    from eurika.smells.detector import get_remediation_hint, severity_to_level

    root = Path(project_root).resolve()
    try:
        snapshot = run_full_analysis(root, update_artifacts=False)
    except Exception as exc:
        return (None, str(exc))
    nodes = list(snapshot.graph.nodes)
    target, resolve_error = _resolve_module_arg(module_arg, root, nodes)
    if resolve_error:
        return (None, resolve_error)
    if not target:
        return (None, f"module '{module_arg}' not in graph")
    graph = snapshot.graph
    summary = snapshot.summary or {}
    fan = graph.fan_in_out()
    fi, fo = fan.get(target, (0, 0))
    central = {c["name"] for c in summary.get("central_modules") or []}
    is_central = target in central
    module_smells = [s for s in snapshot.smells if target in s.nodes]
    risks = summary.get("risks") or []
    module_risks = [r for r in risks if target in r]
    smells_data = [
        {
            "type": s.type,
            "level": severity_to_level(s.severity),
            "severity": s.severity,
            "description": s.description,
            "remediation": get_remediation_hint(s.type),
        }
        for s in module_smells
    ]
    patch_plan = get_patch_plan(root, window=window)
    planned_ops = []
    if patch_plan and patch_plan.get("operations"):
        for o in [x for x in patch_plan["operations"] if x.get("target_file") == target][:5]:
            planned_ops.append({"kind": o.get("kind", "?"), "description": o.get("description", "")})
    rationales: List[Dict[str, Any]] = []
    fix_path = root / "eurika_fix_report.json"
    if fix_path.exists():
        try:
            data = json.loads(fix_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        else:
            expls = data.get("operation_explanations") or []
            policy = data.get("policy_decisions") or []
            ops = (data.get("patch_plan") or {}).get("operations") or []
            if policy and len(policy) == len(expls):
                pairs = list(zip([d.get("target_file") for d in policy], expls))
            elif ops and len(ops) == len(expls):
                pairs = list(zip([o.get("target_file") for o in ops], expls))
            else:
                pairs = []
            for tf, expl in [(t, e) for t, e in pairs if t == target][:5]:
                rationales.append(
                    {
                        "why": expl.get("why", ""),
                        "risk": expl.get("risk", "?"),
                        "expected_outcome": expl.get("expected_outcome", ""),
                        "rollback_plan": expl.get("rollback_plan", ""),
                        "verify_outcome": expl.get("verify_outcome"),
                    }
                )
    return (
        {
            "module": target,
            "fan_in": fi,
            "fan_out": fo,
            "is_central": is_central,
            "smells": smells_data,
            "risks": module_risks,
            "planned_ops": planned_ops,
            "rationales": rationales,
        },
        None,
    )


def _resolve_module_arg(module_arg: str, path: Path, nodes: list[str]) -> tuple[str | None, str | None]:
    """Resolve user module argument to a graph node. Returns (target, error)."""
    mod = module_arg
    m_path = Path(module_arg)
    if m_path.is_absolute():
        try:
            mod = str(m_path.relative_to(path))
        except ValueError:
            mod = m_path.name
    if mod in nodes:
        return (mod, None)
    candidates = [n for n in nodes if n.endswith("/" + mod) or n.endswith(mod)]
    if len(candidates) == 1:
        return (candidates[0], None)
    if len(candidates) > 1:
        return (None, f"ambiguous module '{module_arg}'; candidates: {', '.join(candidates)}")
    return (None, f"module '{module_arg}' not in graph (run 'eurika scan .' to refresh self_map.json)")
