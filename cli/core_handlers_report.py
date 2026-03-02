"""Report and learning-kpi handlers (P0.4 split)."""

from __future__ import annotations

import json
from typing import Any

from .core_handlers_common import _check_path


def handle_report(args: Any) -> int:
    """Print architecture summary + evolution report (no rescan)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    window = getattr(args, "window", 5)
    if getattr(args, "json", False):
        from eurika.api import get_summary, get_history

        data = {"summary": get_summary(path), "history": get_history(path, window=window)}
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    from architecture_pipeline import print_arch_summary, print_arch_history

    code1 = print_arch_summary(path)
    code2 = print_arch_history(path, window=window)
    return 0 if code1 == 0 and code2 == 0 else 1


def handle_report_snapshot(args: Any) -> int:
    """Print CYCLE_REPORT-style markdown from doctor/fix artifacts (3.1-arch.5 thin)."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from report.report_snapshot import format_report_snapshot

    print(format_report_snapshot(path))
    return 0


def handle_learning_kpi(args: Any) -> int:
    """KPI verify_success_rate by smell|action|target + recommendations."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.api import get_learning_insights

    top_n = int(getattr(args, "top_n", 5) or 5)
    polygon_only = bool(getattr(args, "polygon", False))
    insights = get_learning_insights(path, top_n=top_n, polygon_only=polygon_only)
    if getattr(args, "json", False):
        print(json.dumps(insights, indent=2, ensure_ascii=False))
        return 0
    by_smell_action = insights.get("by_smell_action") or {}
    by_target = insights.get("by_target") or []
    recs = insights.get("recommendations") or {}
    whitelist = recs.get("whitelist_candidates") or []
    deny = recs.get("policy_deny_candidates") or []
    title = "## KPI verify_success_rate (ROADMAP)" + (" — polygon drills" if polygon_only else "")
    lines = [title, ""]
    if by_smell_action:
        lines.append("### by_smell_action")
        lines.append("")
        for key, s in sorted(
            by_smell_action.items(),
            key=lambda x: -float(x[1].get("verify_success", 0) / max(x[1].get("total", 1), 1)),
        ):
            total = int(s.get("total", 0) or 0)
            vs = int(s.get("verify_success", 0) or 0)
            vf = int(s.get("verify_fail", 0) or 0)
            rate = round(100 * vs / total, 1) if total else 0
            lines.append(f"- **{key}** total={total}, verify_success={vs}, verify_fail={vf}, rate={rate}%")
        lines.append("")
    polygon_targets = [t for t in by_target if str(t.get("target_file", "")).startswith("eurika/polygon/")]
    if by_target and (polygon_only or polygon_targets):
        lines.append("### Polygon (eurika/polygon/)")
        lines.append("")
        for r in polygon_targets[:top_n]:
            tf = r.get("target_file", "?")
            pair = f"{r.get('smell_type', '?')}|{r.get('action_kind', '?')}"
            rate = float(r.get("verify_success_rate", 0) or 0) * 100
            total = int(r.get("total", 0) or 0)
            vs = int(r.get("verify_success", 0) or 0)
            lines.append(f"- {pair} @ {tf} total={total} success={vs} rate={rate:.1f}%")
        lines.append("")
    if whitelist:
        lines.append("### Promote (whitelist candidates)")
        lines.append("")
        for r in whitelist[:top_n]:
            tf = r.get("target_file", "?")
            pair = f"{r.get('smell_type', '?')}|{r.get('action_kind', '?')}"
            rate = float(r.get("verify_success_rate", 0) or 0) * 100
            lines.append(f"- {pair} @ {tf} (rate={rate:.1f}%)")
        lines.append("")
    if deny:
        lines.append("### Deprioritize (policy deny candidates)")
        lines.append("")
        for r in deny[:top_n]:
            tf = r.get("target_file", "?")
            pair = f"{r.get('smell_type', '?')}|{r.get('action_kind', '?')}"
            rate = float(r.get("verify_success_rate", 0) or 0) * 100
            lines.append(f"- {pair} @ {tf} (rate={rate:.1f}%)")
        lines.append("")
    lines.append("### Next steps (D)")
    lines.append("")
    rui = next((s for k, s in by_smell_action.items() if "remove_unused_import" in k), None)
    if rui and int(rui.get("total", 0) or 0) >= 5:
        rate = 100 * int(rui.get("verify_success", 0) or 0) / max(int(rui.get("total", 1) or 1), 1)
        lines.append(f"- remove_unused_import rate={rate:.1f}%: try `eurika fix . --no-code-smells --allow-low-risk-campaign`")
    if polygon_targets:
        low = [
            t
            for t in polygon_targets
            if float(t.get("verify_success_rate", 0) or 0) < 0.5 and int(t.get("total", 0) or 0) >= 1
        ]
        if low:
            lines.append("- eurika/polygon/: run `eurika fix . --allow-low-risk-campaign` to accumulate verify_success for drills")
    lines.append("- To promote: run fix, accumulate 2+ verify_success per target, then `eurika whitelist-draft .`")
    lines.append("- Use `--apply-suggested-policy` when doctor suggests EURIKA_CAMPAIGN_ALLOW_LOW_RISK")
    lines.append("")
    print("\n".join(lines) if lines else "No learning data yet. Run eurika fix to accumulate.")
    return 0
