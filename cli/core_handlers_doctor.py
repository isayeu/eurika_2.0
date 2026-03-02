"""Doctor handler (P0.4 split)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .core_handlers_common import (
    _aggregate_multi_repo_reports,
    _check_path,
    _clog,
    _err,
    _paths_from_args,
)


def handle_doctor(args: Any) -> int:
    """Diagnostics only: report + architect (no patches). Saves to eurika_doctor_report.json."""
    paths = _paths_from_args(args)
    exit_code = 0
    project_reports: list[dict[str, Any]] = []
    from cli.orchestrator import run_cycle
    from eurika.smells.rules import summary_to_text

    for i, path in enumerate(paths):
        if len(paths) > 1:
            _clog().info("\n--- Project %s/%s: %s ---\n", i + 1, len(paths), path)
        if _check_path(path) != 0:
            exit_code = 1
            continue
        no_llm = getattr(args, "no_llm", False)
        _clog().info("eurika: doctor — step 1/4: loading summary, history, architect...")
        if not no_llm:
            _clog().info("eurika: doctor — step 2/4: architect will use LLM (Ollama/OpenAI) — may take 30s–3min")
        use_rich = False
        try:
            from rich.console import Console

            _rich_console = Console(file=sys.stderr)
            use_rich = sys.stderr.isatty()
        except ImportError:
            _rich_console = None
        quiet_doc = getattr(args, "quiet", False)
        if use_rich and _rich_console and not no_llm:
            with _rich_console.status("[bold green]Loading architect...", spinner="dots"):
                data = run_cycle(
                    path,
                    mode="doctor",
                    runtime_mode=getattr(args, "runtime_mode", "assist"),
                    window=getattr(args, "window", 5),
                    no_llm=no_llm,
                    online=getattr(args, "online", False),
                    quiet=quiet_doc,
                )
        else:
            data = run_cycle(
                path,
                mode="doctor",
                runtime_mode=getattr(args, "runtime_mode", "assist"),
                window=getattr(args, "window", 5),
                no_llm=no_llm,
                online=getattr(args, "online", False),
                quiet=quiet_doc,
            )
        if data.get("error"):
            _err(data["error"])
            exit_code = 1
            continue
        _clog().info("eurika: doctor — step 4/4: rendering report")
        summary = data["summary"]
        history = data["history"]
        patch_plan = data["patch_plan"]
        architect_text = data["architect_text"]
        suggested_policy = data.get("suggested_policy") or {}
        context_sources = data.get("context_sources") or {}
        campaign_checkpoint = data.get("campaign_checkpoint") or {}
        print(summary_to_text(summary))
        print()
        print(history.get("evolution_report", ""))
        print()
        print(architect_text)
        if context_sources:
            vfail = len(context_sources.get("recent_verify_fail_targets") or [])
            crej = len(context_sources.get("campaign_rejected_targets") or [])
            recent = len(context_sources.get("recent_patch_modified") or [])
            targets = len(context_sources.get("by_target") or {})
            print()
            print("Context sources (ROADMAP 3.6.3):")
            print(f"  targets={targets}, recent_verify_fail={vfail}, campaign_rejected={crej}, recent_patch_modified={recent}")
        ops_metrics = data.get("operational_metrics") or {}
        if ops_metrics:
            ar = ops_metrics.get("apply_rate", "N/A")
            rr = ops_metrics.get("rollback_rate", "N/A")
            med = ops_metrics.get("median_verify_time_ms")
            med_str = f"{med} ms" if med is not None else "N/A"
            print()
            print("Operational metrics (last 10 fix runs):")
            print(f"  apply_rate={ar}, rollback_rate={rr}, median_verify_time={med_str}")
        if campaign_checkpoint:
            cp_id = campaign_checkpoint.get("checkpoint_id", "N/A")
            cp_status = campaign_checkpoint.get("status", "unknown")
            cp_runs = len(campaign_checkpoint.get("run_ids") or [])
            print()
            print("Campaign checkpoint (ROADMAP 3.6.4):")
            print(f"  checkpoint_id={cp_id}, status={cp_status}, run_ids={cp_runs}")
        if suggested_policy.get("suggested"):
            sugg = suggested_policy["suggested"]
            telemetry = suggested_policy.get("telemetry") or {}
            apply_rate = telemetry.get("apply_rate", "N/A")
            rollback_rate = telemetry.get("rollback_rate", "N/A")
            print()
            print("Suggested policy (ROADMAP 2.9.4):")
            print(f"  (apply_rate={apply_rate}, rollback_rate={rollback_rate})")
            for k, v in sugg.items():
                print(f"  export {k}={v}")
            print("  # Or run fix/cycle with --apply-suggested-policy")
        learning_kpi: dict[str, Any] = {}
        try:
            from eurika.api import get_learning_insights

            insights = get_learning_insights(path, top_n=5)
            by_smell = insights.get("by_smell_action") or {}
            if by_smell:
                print()
                print("KPI verify_success_rate (by smell|action):")
                for k, s in list(
                    sorted(
                        by_smell.items(),
                        key=lambda x: -float(x[1].get("verify_success", 0) or 0) / max(x[1].get("total", 1) or 1, 1),
                    )
                )[:6]:
                    total = int(s.get("total") or 0)
                    vs = int(s.get("verify_success") or 0)
                    rate = f"{100 * vs / total:.0f}%" if total else "N/A"
                    print(f"  {k}: total={total}, verify_success={vs}, rate={rate}")
                learning_kpi = {"by_smell_action": by_smell}
        except Exception:
            pass
        report = {"summary": summary, "history": history, "architect": architect_text, "patch_plan": patch_plan}
        if context_sources:
            report["context_sources"] = context_sources
        if suggested_policy:
            report["suggested_policy"] = suggested_policy
        if data.get("operational_metrics"):
            report["operational_metrics"] = data["operational_metrics"]
        if campaign_checkpoint:
            report["campaign_checkpoint"] = campaign_checkpoint
        if learning_kpi:
            report["learning_kpi"] = learning_kpi
        fix_path = path / "eurika_fix_report.json"
        if fix_path.exists():
            try:
                fix = json.loads(fix_path.read_text(encoding="utf-8"))
                if fix.get("telemetry"):
                    report["last_fix_telemetry"] = fix["telemetry"]
            except Exception:
                pass
        try:
            report_path = path / "eurika_doctor_report.json"
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            _clog().info("eurika: eurika_doctor_report.json written to %s", report_path)
        except Exception:
            pass
        project_reports.append(report)
    if len(paths) > 1 and project_reports:
        agg = _aggregate_multi_repo_reports(project_reports, paths)
        out_path = paths[0] / "eurika_doctor_report_aggregated.json"
        try:
            out_path.write_text(json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8")
            _clog().info("eurika: eurika_doctor_report_aggregated.json written to %s", out_path)
        except Exception:
            pass
    return exit_code
