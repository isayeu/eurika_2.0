"""R1 Domain vs Presentation: format ExplainResult for CLI/UI."""

from __future__ import annotations

from typing import Any, Callable


def _default_truncate(raw: str, max_len: int = 200) -> str:
    if len(raw) <= max_len:
        return raw
    cut = raw[:max_len].rfind(" ")
    return (raw[:cut] if cut >= 0 else raw[:max_len]) + "..."


def format_explain_result(
    data: dict[str, Any],
    truncate: Callable[[str, int], str] | None = None,
) -> str:
    """
    Presentation: format structured explain data to text (R1).
    truncate(text, max_len) for long strings; defaults to _default_truncate.
    """
    tr = truncate or _default_truncate
    lines: list[str] = []
    module = data.get("module", "?")
    fi = data.get("fan_in", 0)
    fo = data.get("fan_out", 0)
    is_central = data.get("is_central", False)
    lines.append(f"MODULE EXPLANATION: {module}")
    lines.append("")
    lines.append("Role:")
    lines.append(f"- fan-in : {fi}")
    lines.append(f"- fan-out: {fo}")
    lines.append(f"- central: {'yes' if is_central else 'no'}")
    lines.append("")
    lines.append("Smells:")
    smells = data.get("smells") or []
    if not smells:
        lines.append("- none detected for this module")
    else:
        for s in smells:
            lines.append(f"- [{s.get('type', '?')}] ({s.get('level', '?')}) severity={s.get('severity', 0):.2f} — {s.get('description', '')}")
            lines.append(f"  → {s.get('remediation', '')}")
    lines.append("")
    lines.append("Risks (from summary):")
    risks = data.get("risks") or []
    if not risks:
        lines.append("- none highlighted in summary")
    else:
        for r in risks:
            lines.append(f"- {r}")
    planned = data.get("planned_ops") or []
    if planned:
        lines.append("")
        lines.append("Planned operations (from patch-plan):")
        for op in planned:
            lines.append(f"- [{op.get('kind', '?')}] {tr(op.get('description', ''), 80)}")
    rationales = data.get("rationales") or []
    if rationales:
        lines.append("")
        lines.append("Runtime rationale (from last fix):")
        for r in rationales:
            verify_out = r.get("verify_outcome")
            verify_str = f"verify={verify_out}" if verify_out is not None else "verify=not run"
            lines.append(f"- why: {tr(r.get('why', ''), 120)}")
            lines.append(f"  risk={r.get('risk', '?')}, expected_outcome={tr(r.get('expected_outcome', ''), 80)}")
            lines.append(f"  rollback_plan={tr(r.get('rollback_plan', ''), 80)}, {verify_str}")
    return "\n".join(lines)
