"""CYCLE_REPORT-style markdown formatting (ROADMAP 3.1-arch.5).

Presentation layer: formats doctor/fix artifacts for pasting into CYCLE_REPORT.md.
CLI handlers delegate here to stay thin.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _try_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load JSON file returning (data, error_message)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError:
        return None, f"invalid JSON in {path.name}"
    except OSError:
        return None, f"cannot read {path.name}"


def format_report_snapshot(path: Path) -> str:
    """
    Produce CYCLE_REPORT-style markdown from eurika_doctor_report.json and eurika_fix_report.json.

    Returns formatted string. Empty or missing artifacts yield a fallback message.
    """
    lines: list[str] = []
    fix_path = path / "eurika_fix_report.json"
    doctor_path = path / "eurika_doctor_report.json"
    load_errors: list[str] = []

    if fix_path.exists():
        fix, fix_err = _try_load_json(fix_path)
        if fix_err:
            load_errors.append(fix_err)
        if fix:
            v = fix.get("verify", {}) or {}
            mod = fix.get("modified", [])
            sk = fix.get("skipped", [])
            lines.append("## 1. Fix (`eurika fix .`)")
            lines.append("")
            lines.append("| Поле | Значение |")
            lines.append("|------|----------|")
            lines.append(f"| **modified** | {len(mod)} |")
            lines.append(f"| **skipped** | {len(sk)} |")
            lines.append(f"| **verify** | {v.get('success', 'N/A')} |")
            if fix.get("skipped_reasons"):
                lines.append("")
                lines.append("### Skipped — причины")
                for f, r in list(fix.get("skipped_reasons", {}).items())[:10]:
                    lines.append(f"- {f}: {r}")
            vm = fix.get("verify_metrics") or {}
            if vm:
                lines.append("")
                lines.append(f"### verify_metrics: before={vm.get('before_score')}, after={vm.get('after_score')}")
            telemetry = fix.get("telemetry") or {}
            if telemetry:
                lines.append("")
                lines.append("### telemetry (ROADMAP 2.7.8)")
                lines.append(
                    f"apply_rate={telemetry.get('apply_rate')}, no_op_rate={telemetry.get('no_op_rate')}, "
                    f"rollback_rate={telemetry.get('rollback_rate')}, verify_duration_ms={telemetry.get('verify_duration_ms')}, "
                    f"median_verify_time_ms={telemetry.get('median_verify_time_ms', 'N/A')}"
                )
            lines.append("")

    if doctor_path.exists():
        doc, doc_err = _try_load_json(doctor_path)
        if doc_err:
            load_errors.append(doc_err)
        if doc:
            summary = doc.get("summary", {}) or {}
            sys = summary.get("system", {}) or {}
            modules = sys.get("modules", "N/A")
            deps = sys.get("dependencies", "N/A")
            risk_score = "N/A"
            history = doc.get("history", {}) or {}
            points = history.get("points", [])
            if points:
                risk_score = points[-1].get("risk_score", "N/A")
            lines.append("## 2. Doctor (`eurika_doctor_report.json`)")
            lines.append("")
            lines.append("| Метрика | Значение |")
            lines.append("|---------|----------|")
            lines.append(f"| **Модули** | {modules} |")
            lines.append(f"| **Зависимости** | {deps} |")
            lines.append(f"| **Risk score** | {risk_score}/100 |")
            ops = doc.get("operational_metrics") or {}
            if ops:
                ar = ops.get("apply_rate", "N/A")
                rr = ops.get("rollback_rate", "N/A")
                med = ops.get("median_verify_time_ms")
                med_str = f"{med} ms" if med is not None else "N/A"
                lines.append(f"| **apply_rate** (last {ops.get('runs_count', 10)} runs) | {ar} |")
                lines.append(f"| **rollback_rate** | {rr} |")
                lines.append(f"| **median_verify_time** | {med_str} |")
            lines.append("")

    by_action: dict[str, Any] = {}
    by_smell: dict[str, Any] = {}
    try:
        from eurika.storage import ProjectMemory

        mem = ProjectMemory(path)
        by_action = mem.learning.aggregate_by_action_kind()
        by_smell = mem.learning.aggregate_by_smell_action()
    except Exception:
        pass
    if by_action or by_smell:
        lines.append("## 3. Learning")
        lines.append("")
        if by_action:
            lines.append("### by_action_kind")
            for k, v in list(by_action.items())[:8]:
                s, f = v.get("success", 0), v.get("fail", 0)
                rate = f"{100 * s / (s + f):.0f}%" if (s + f) else "N/A"
                lines.append(f"- {k}: {s} success, {f} fail ({rate})")
            lines.append("")
        if by_smell:
            lines.append("### by_smell_action")
            for k, v in list(by_smell.items())[:8]:
                lines.append(f"- {k}: total={v.get('total')}, success={v.get('success')}, fail={v.get('fail')}")

    if not lines:
        lines.append("(No eurika_doctor_report.json or eurika_fix_report.json found. Run doctor/fix first.)")
    if load_errors:
        lines.append("")
        lines.append("### Snapshot warnings")
        for e in load_errors:
            lines.append(f"- {e}")
    return "\n".join(lines)


# TODO (eurika): refactor long_function 'format_report_snapshot' — consider extracting helper
