"""Explain API routes (ROADMAP 3.1-arch.5, R1 Domain vs Presentation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from eurika.smells.detector import get_remediation_hint, severity_to_level


def get_explain_data(project_root: Path, module_arg: str, window: int = 5) -> tuple[Dict[str, Any] | None, str | None]:
    """
    Domain: return structured explain data (R1 Domain vs Presentation).
    Returns (data_dict, error_message). Caller formats via format_explain_result.
    """
    from eurika.api import get_patch_plan
    from eurika.core.pipeline import run_full_analysis

    root = Path(project_root).resolve()
    try:
        snapshot = run_full_analysis(root, update_artifacts=False)
    except Exception as exc:
        return (None, str(exc))
    
    target, resolve_error = _resolve_module_arg(module_arg, root, list(snapshot.graph.nodes))
    if resolve_error:
        return (None, resolve_error)
    if not target:
        return (None, f"module '{module_arg}' not in graph")
    
    graph = snapshot.graph
    summary = snapshot.summary or {}
    fi, fo = _compute_fan_in_out(graph, target)
    is_central = _is_central_module(target, summary)
    module_smells = [s for s in snapshot.smells if target in s.nodes]
    module_risks = _filter_risks_by_target(summary.get("risks") or [], target)
    smells_data = _create_smells_data(module_smells)
    patch_plan = get_patch_plan(root, window=window)
    planned_ops = _extract_planned_operations(patch_plan, target)
    rationales = _load_fix_report_rationales(root)
    
    return ({
        "module": target,
        "fan_in": fi,
        "fan_out": fo,
        "is_central": is_central,
        "smells": smells_data,
        "planned_operations": planned_ops,
        "planned_ops": planned_ops,
        "rationales": rationales,
        "risks": module_risks,
    }, None)

def _compute_fan_in_out(graph, target):
    fan = graph.fan_in_out()
    return fan.get(target, (0, 0))

def _is_central_module(target, summary):
    central = {c["name"] for c in summary.get("central_modules") or []}
    return target in central

def _filter_risks_by_target(risks, target):
    return [r for r in risks if target in r]

def _create_smells_data(module_smells):
    return [
        {
            "type": s.type,
            "level": severity_to_level(s.severity),
            "severity": s.severity,
            "description": s.description,
            "remediation": get_remediation_hint(s.type),
        }
        for s in module_smells
    ]

def _extract_planned_operations(patch_plan, target):
    if patch_plan and patch_plan.get("operations"):
        return [{"kind": o.get("kind", "?"), "description": o.get("description", "")} for o in [x for x in patch_plan["operations"] if x.get("target_file") == target][:5]]
    return []

def _load_fix_report_rationales(root):
    fix_path = root / "eurika_fix_report.json"
    if fix_path.exists():
        try:
            data = json.loads(fix_path.read_text(encoding="utf-8"))
            expls = data.get("operation_explanations") or []
            policy = data.get("policy_decisions") or []
            ops = data.get("patch_plan")  # This line was incomplete in the original code
            return [{"explanation": e, "policy": p, "operations": ops} for e, p in zip(expls, policy)]
        except Exception:
            pass
    return []

def _resolve_module_arg(module_arg: str, root: Path, nodes: List[str]) -> tuple[str | None, str | None]:
    """Resolve module_arg (path or name) to graph node. Returns (target, error)."""
    if not module_arg or not module_arg.strip():
        return None, "module argument is empty"
    arg = module_arg.strip()
    norm = Path(arg).as_posix()
    if norm in nodes:
        return norm, None
    for node in nodes:
        if node == arg:
            return node, None
        if "/" in arg and node.endswith(arg):
            return node, None
        if "/" not in arg and (node.split("/")[-1] == arg or node.endswith("/" + arg)):
            return node, None
    return None, None